import asyncio
import json
import pathlib
from contextlib import suppress

import pygame
import requests
import simplejson
from config import *
import datetime


class Periodic:
    def __init__(self, func, time):
        self.func = func
        self.time = time
        self.is_started = False
        self._task = None

    async def start(self):
        if not self.is_started:
            self.is_started = True
            # Start task to call func periodically:
            self._task = asyncio.ensure_future(self._run())

    async def stop(self):
        if self.is_started:
            self.is_started = False
            # Stop task and await it stopped:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _run(self):
        while True:
            await asyncio.sleep(self.time)
            await self.func


# noinspection PyPep8Naming
# @staticmethod
def setup_mixer():
    def getmixerargs():
        pygame.mixer.init()
        freq, size, chan = pygame.mixer.get_init()
        return freq, size, chan

    BUFFER = 3072  # audio buffer size, number of samples since pygame 1.8.
    FREQ, SIZE, CHAN = getmixerargs()

    pygame.mixer.init(FREQ, SIZE, CHAN, BUFFER)
    pygame.init()


#
# def play_sound(sound: str):
#     soundfile = pathlib.Path(__file__).with_name(sound)
#     # logger.debug("play sound", soundfile)
#     pygame.mixer.music.load(str(soundfile))
#     pygame.mixer.music.play()


def get_new_token():
    response = requests.post(
        "https://www.donateall.online/public/api/v1/authenticate",
        json={"username": music_login, "password": music_password},
    )

    if response.status_code == 200:
        with open("music_token.json", "w") as f:
            f.write(response.text)
    else:
        print(
            "Failed to get new music token: "
            + str(response.status_code)
            + " "
            + response.text
        )
        return None

    return response.json()


def refresh_token(token):
    response = requests.post(
        "https://www.donateall.online/public/api/v1/refresh",
        json={"refresh_token": token["refresh_token"]},
    )
    if response.status_code == 200:
        data = response.json()
        token["acess_token_expires"] = data["acess_token_expires"]
        token["acess_token"] = data["acess_token"]
        with open("music_token.json", "w") as f:
            simplejson.dump(token, f)
    else:
        print(
            "Failed to refresh music token: "
            + str(response.status_code)
            + " "
            + response.text
        )
        token = None

    return token


def load_token():
    try:
        with open("music_token.json", "r") as f:
            token = simplejson.load(f)

        return token
    except (IOError, OSError, simplejson.errors.JSONDecodeError) as e:
        print("Failed to get token: " + str(e))
        return None


def login():
    token = load_token()
    if not token:
        token = get_new_token()
    else:
        refresh_expires = datetime.datetime.fromtimestamp(
            int(token["refresh_token_expires"]) / 1000
        )
        access_expires = datetime.datetime.fromtimestamp(
            int(token["access_token_expires"]) / 1000
        )
        now = datetime.datetime.now()
        if refresh_expires < now:
            token = get_new_token()
        else:
            if access_expires < now:
                token = refresh_token(token)

    return token


async def get_current_song(token):
    response = (
        requests.get(  # "https://www.donateall.online/public/api/v1/songs/queue",
            "https://www.donateall.online/public/api/v1/songs/current",
            headers={
                "Content-Type": "application/json",
                "api_token": token["access_token"],
            },
        )
    )
    print(response.text)


def set_music(enabled: bool):
    r = requests.post(
        "https://donateall.online/api/authenticate",
        json={"username": music_login, "password": music_password, "rememberMe": True},
    )
    r.raise_for_status()
    res = r.json()
    token = res["id_token"]

    r = requests.get(
        "https://donateall.online/api/account",
        headers={"Authorization": "Bearer " + token},
    )
    r.raise_for_status()
    res = r.json()
    if res.get("login", "ERROR") == "ERROR":
        print("ERROR login failed {0}".format(res))

    r = requests.get(
        "https://donateall.online/api/user-chat-advance-settings",
        headers={"Authorization": "Bearer " + token},
    )
    r.raise_for_status()

    res = r.json()[0]
    id = res["id"]

    settings = json.loads(res["settings"])
    settings["musicSettings"]["isMusicEnabled"] = enabled

    settings_s = json.dumps(settings)

    r = requests.put(
        "https://donateall.online/api/user-chat-advance-settings",
        headers={"Authorization": "Bearer " + token},
        json={"id": id, "settings": settings_s},
    )
    r.raise_for_status()


async def main():
    # setup_mixer()
    # token = login()
    # await get_current_song(token)
    # p = Periodic(get_current_song(token), time=5)
    # await p.start()
    # await asyncio.sleep(600)
    # await p.stop()
    # play_sound('matmatmat.mp3')
    # await asyncio.sleep(600)
    set_music(False)


if __name__ == "__main__":
    asyncio.run(main())
