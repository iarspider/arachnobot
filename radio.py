import base64
import json
import time
from typing import NamedTuple

import httpx
from loguru import logger
import asyncio
import dbus
import dbus.mainloop.glib
from gi.repository import GLib
import mimetypes
from urllib.parse import urlparse, unquote
from pathlib import Path

from fake_useragent import UserAgent


class VLCTrackListener:
    def __init__(self):
        self.queue: asyncio.Queue[dict] = asyncio.Queue()

    def _on_properties_changed(self, interface, changed, invalidated):
        if "Metadata" not in changed:
            return

        metadata = changed["Metadata"]

        title = metadata.get("xesam:title", "")
        artist = ", ".join(metadata.get("xesam:artist", []))
        event = {"title": title, "artist": artist, "cover": ""}

        cover = metadata.get("mpris:artUrl", "")

        if cover:
            mime_type, _ = mimetypes.guess_type(cover)
            cover_path = Path(unquote(urlparse(cover).path))

            event["cover"] = (
                f"data:{mime_type};base64,{base64.b64encode(cover_path.read_bytes()).decode()}"
            )

        # thread-safe enqueue into asyncio loop
        asyncio.get_running_loop().call_soon_threadsafe(self.queue.put_nowait, event)

    async def run(self):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()

        # bus.add_signal_receiver(
        #     self._on_properties_changed,
        #     signal_name="PropertiesChanged",
        #     dbus_interface="org.freedesktop.DBus.Properties",
        #     path="/org/mpris/MediaPlayer2",
        #     bus_name="org.mpris.MediaPlayer2.vlc",
        # )

        bus.add_signal_receiver(
            self._on_properties_changed,
            signal_name="PropertiesChanged",
            dbus_interface="org.freedesktop.DBus.Properties",
            path="/org/mpris/MediaPlayer2",
            bus_name="org.mpris.MediaPlayer2.vlc",
            arg0="org.mpris.MediaPlayer2.Player",
        )
        loop = GLib.MainLoop()

        # run GLib loop cooperatively
        while True:
            loop.get_context().iteration(False)
            await asyncio.sleep(0.05)


TEMPLATE = "{artist} - {song}"


class PendingSong(NamedTuple):
    channel: str
    item: dict

    def __str__(self):
        return TEMPLATE.format(**self.item)


class RadioTrackListener:
    def __init__(self):
        self.queue: asyncio.Queue[dict] = asyncio.Queue()
        self.last_line: dict[int, str] = {}

        self.stations = {
            554: {
                "archive": "record_archive.txt",
                "current": "record.txt",
                "name": "rock",
            },
            557: {
                "archive": "symphony_archive.txt",
                "current": "symphony.txt",
                "name": "symphony",
            },
        }

    # noinspection PyMethodMayBeStatic
    def get_current_song(self, result: dict) -> dict | None:
        cur_t = int(time.time())
        for item in result["result"]["history"]:
            if int(item["time"]) < cur_t:
                return item
        return None

    def write_data(self, station_id: int, new_item: dict) -> None:
        new_song = TEMPLATE.format(**new_item)
        if self.last_line[station_id] == new_song:
            return

        self.last_line[station_id] = new_song
        event = {
            "station": self.stations[station_id]["name"],
            "title": new_item["song"],
            "artist": new_item["artist"],
            "cover": new_item["image600"],
        }
        if event["cover"] and not event["cover"].startswith("http"):
            event["cover"] = "https://www.radiorecord.ru/" + event["cover"].lstrip("/")

        asyncio.get_running_loop().call_soon_threadsafe(self.queue.put_nowait, event)

    async def poll_station(
        self,
        client: httpx.AsyncClient,
        station_id: int,
        station: dict,
    ) -> None:
        url = f"https://www.radiorecord.ru/api/station/history/?id={station_id}"

        try:
            r = await client.get(
                url, timeout=20, headers={"User-Agent": str(UserAgent.firefox)}
            )
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, httpx.ReadTimeout, json.JSONDecodeError) as e:
            logger.opt(exception=True).exception(
                "Radio Record API returned error!",
            )
            return

        try:
            current_song = self.get_current_song(data)

            if current_song:
                self.write_data(station_id, current_song)

        except (IndexError, TypeError, KeyError) as e:
            logger.opt(exception=True).exception(
                "Error getting current song",
            )

    async def run(self):
        for station_id, station in self.stations.items():
            self.last_line[station_id] = ""

        async with httpx.AsyncClient() as client:
            while True:
                await asyncio.sleep(10)

                await asyncio.gather(
                    *(
                        self.poll_station(client, station_id, station)
                        for station_id, station in self.stations.items()
                    )
                )
