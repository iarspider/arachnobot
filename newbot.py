#!python3
import asyncio
import datetime
import http.client as http_client
import json
import logging
import os
import pathlib
import random
import sys
import time
from collections import defaultdict
from multiprocessing import Process
from typing import Optional, List, Dict

import peewee
import socketio
import twitchio
import uvicorn
from deprecation import deprecated
from dotenv import load_dotenv
from loguru import logger
from pytils import numeral
from requests.structures import CaseInsensitiveDict
from twitchio import eventsub, Client, Chatter, Stream, HTTPException
from twitchio.ext import commands
from twitchio.ext.commands import CommandErrorPayload, CommandOnCooldown

# noinspection PyUnresolvedReferences
import nightbot_api
from aio_timer import Periodic
from config import *
from ripkey import keyboard_listener

from radio import VLCTrackListener, RadioTrackListener

CLIENT_ID: str = "..."  # The CLIENT ID from the Twitch Dev Console
CLIENT_SECRET: str = "..."  # The CLIENT SECRET from the Twitch Dev Console
BOT_ID = "..."  # The Account ID of the bot user...
OWNER_ID = "..."  # Your personal User ID...

httpclient_logger = logging.getLogger("http.client")
proc: Process
dashboard_timer: Periodic
sl_client: socketio.AsyncClient
database = peewee.SqliteDatabase(database_file)
twitch_bot: Optional["Bot"] = None


class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(logfile, debug, color, http_debug):
    loglevel = logging.DEBUG if debug else logging.INFO
    logger.remove()
    logger.add(
        sys.stderr,
        level=loglevel,
        backtrace=True,
        diagnose=False,
        colorize=color,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{"
        "line}</cyan> - <level>{message}</level>",
    )
    logger.add(
        logfile,
        level=loglevel,
        rotation="12:00",
        compression="zip",
        retention="1 week",
        backtrace=True,
        diagnose=True,
    )

    handler = InterceptHandler()
    # logging.basicConfig(handlers=[InterceptHandler()], level=0)

    if debug:
        logger.info("Debug logging is ON")

    # global logger
    # logger = logging.getLogger("arachnobot")
    # logger.propagate = False
    ws_logger = logging.getLogger("websockets.server")
    ws_logger.handlers.clear()
    ws_logger.addHandler(handler)
    uvicorn_logger = logging.getLogger("uvicorn.error")
    uvicorn_logger.handlers.clear()
    uvicorn_logger.addHandler(handler)
    obsws_logger = logging.getLogger("obswebsocket.core")
    obsws_logger.handlers.clear()
    obsws_logger.addHandler(handler)

    if not debug:
        logging.getLogger("discord").setLevel(logging.INFO)
        ws_logger.setLevel(logging.WARN)
        uvicorn_logger.setLevel(logging.WARN)
        obsws_logger.setLevel(logging.WARN)
    else:
        logger.info("Debug logging is ON")
        logging.getLogger("discord").setLevel(logging.DEBUG)
        ws_logger.setLevel(logging.DEBUG)
        uvicorn_logger.setLevel(logging.DEBUG)
        obsws_logger.setLevel(logging.DEBUG)

    if http_debug:
        http_client.HTTPConnection.debuglevel = 1


def httpclient_logging_patch(level=logging.DEBUG):
    """Enable HTTPConnection debug logging to the logging framework"""

    def httpclient_log(*args):
        httpclient_logger.log(level, " ".join(args))

    # mask the print() built-in in the http.client module to use
    # logging instead
    http_client.print = httpclient_log
    # enable debugging
    http_client.HTTPConnection.debuglevel = 1


#
# class GameConfig(peewee.Model):
#     game = peewee.CharField(primary_key=True)
#     rip_total = peewee.IntegerField(default=0)
#     rip_enabled = peewee.BooleanField(default=True)
#     music_enabled = peewee.BooleanField(default=False)
#     window = peewee.CharField(default="X")
#     infinite = peewee.BooleanField(default=False)
#     inexact = peewee.BooleanField(default=False)
#     mt = peewee.BooleanField(default=False)
#     mt_str = peewee.CharField(default="iarspider/moar__/danzio_plagius")
#     watchfile = peewee.CharField(default="")
#     rip_emoji = peewee.CharField(default="☠")
#     use_game_capture = peewee.BooleanField(default=True)
#     tags = peewee.TextField(default="")
#     window_inexact = peewee.BooleanField(default=False)
#
#     def __str__(self):
#         return self.game
#
#     class Meta:
#         database = database
# TODO: remove deprecated aliases after 5.8.0
class GameConfig(peewee.Model):
    game = peewee.CharField(primary_key=True)

    # ─── RIP / Death counter ──────────────────────────────
    rip_enabled = peewee.BooleanField(default=True)
    rip_total = peewee.IntegerField(default=0)
    rip_emoji = peewee.CharField(default="☠")

    # External source of truth (e.g. Minecraft mod)
    rip_watchfile = peewee.CharField(default="")
    rip_is_inexact = peewee.BooleanField(
        default=False, help_text="Deaths count is approximate (no reliable source)"
    )

    # ─── Stream / gameplay state ──────────────────────────
    rip_is_infinite = peewee.BooleanField(
        default=False, help_text="Streamer enabled immortality / cheats"
    )

    music_enabled = peewee.BooleanField(default=False)

    # ─── OBS capture (window mode) ────────────────────────
    obs_window = peewee.TextField(
        default="", help_text="OBS window string: id\\ntitle\\nclass"
    )
    obs_window_title_glob = peewee.BooleanField(
        default=False, help_text="Window title is glob-pattern"
    )

    # LEGACY (Windows OBS distinction)
    # use_game_capture = peewee.BooleanField(
    #     default=True,
    #     help_text="LEGACY: OBS Game Capture vs Window Capture"
    # )

    # ─── External integrations ────────────────────────────
    mt_enabled = peewee.BooleanField(default=False)
    mt_source = peewee.CharField(default="iarspider/moar__/danzio_plagius")

    # ─── Twitch metadata ──────────────────────────────────
    tags = peewee.TextField(
        default="", help_text="Twitch tags (semicolon-separated, raw)"
    )

    class Meta:
        database = database

    # ─── Derived / helper properties ──────────────────────
    @property
    @deprecated("5.6.0", "Windows legacy, do not use")
    def use_game_capture(self):
        return True

    @property
    @deprecated("5.6.0", "Use obs_window instead")
    def window(self):
        return self.obs_window

    @window.setter
    @deprecated("5.6.0", "Use obs_window instead")
    def window(self, value):
        self.obs_window = value

    @property
    @deprecated("5.6.0", "Use obs_window_title_glob instead")
    def window_inexact(self):
        return self.obs_window_title_glob

    @window_inexact.setter
    @deprecated("5.6.0", "Use obs_window_title_glob instead")
    def window_inexact(self, value):
        self.obs_window_title_glob = value

    @property
    @deprecated("5.6.0", "Use mt_enabled instead")
    def mt(self):
        return self.mt_enabled

    @mt.setter
    @deprecated("5.6.0", "Use mt_enabled instead")
    def mt(self, value):
        self.mt_enabled = value

    @property
    @deprecated("5.6.0", "Use mt_source instead")
    def mt_str(self):
        return self.mt_source

    @mt_str.setter
    @deprecated("5.6.0", "Use mt_source instead")
    def mt_str(self, value):
        self.mt_source = value

    @property
    @deprecated("5.6.0", "Use rip_watchfile instead")
    def watchfile(self):
        return self.rip_watchfile

    @watchfile.setter
    @deprecated("5.6.0", "Use rip_watchfile instead")
    def watchfile(self, value):
        self.rip_watchfile = value

    @property
    @deprecated("5.6.0", "Use rip_is_inexact instead")
    def inexact(self):
        return self.rip_is_inexact

    @inexact.setter
    @deprecated("5.6.0", "Use rip_is_inexact instead")
    def inexact(self, value):
        self.rip_is_inexact = value

    @property
    @deprecated("5.6.0", "Use rip_is_infinite instead")
    def infinite(self):
        return self.rip_is_infinite

    @infinite.setter
    @deprecated("5.6.0", "Use rip_is_infinite instead")
    def infinite(self, value):
        self.rip_is_infinite = value

    def __str__(self) -> str:
        return str(self.game)


class DuelStats(peewee.Model):
    attacker = peewee.TextField()
    defender = peewee.TextField()
    losses = peewee.IntegerField(null=False, default=0)
    wins = peewee.IntegerField(null=False, default=0)

    class Meta:
        table_name = "duelstats"
        database = database
        primary_key = peewee.CompositeKey("attacker", "defender")


class SourceConfig(peewee.Model):
    game = peewee.ForeignKeyField(model=GameConfig, backref="sources")
    scene = peewee.CharField()
    source = peewee.CharField()
    state = peewee.BooleanField()

    class Meta:
        table_name = "sourceconfig"
        database = database


class ExtraRipCounter(peewee.Model):
    game = peewee.ForeignKeyField(model=GameConfig, backref="extra_rips")
    name = peewee.CharField()
    cnt = peewee.IntegerField(default=1)

    class Meta:
        table_name = "xripcount"
        database = database


class Bot(commands.Bot):
    def __init__(
        self, *, token_filename: str, sio_server_: socketio.AsyncServer
    ) -> None:
        self.token_filename = token_filename
        self.sio_server: socketio.AsyncServer = sio_server_
        super().__init__(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            bot_id=BOT_ID,
            owner_id=OWNER_ID,
            prefix=["!", "! "],
        )

        s1 = (
            "&qwertyuiop[]asdfghjkl;'zxcvbnm,./QWERTYUIOP{"
            "}ASDFGHJKL:ZXCVBNM<>?`~" + '"'
        )
        s2 = (
            "?йцукенгшщзхъфывапролджэячсмитьбю.ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЯЧСМИТЬБЮ,"
            "ёЁ" + "Э"
        )
        self.trans = str.maketrans(s1, s2)
        self.rtrans = str.maketrans(s2, s1)

        # hack
        self._http._refresh_token = os.getenv("TWITCH_REFRESH_TOKEN")

        self.initial_channels = ["#iarspider"]

        self.viewers = CaseInsensitiveDict()
        self.greeted = set()

        self.db = {}
        self.pearls = []

        self.vmod = None
        self.vmod_active = False
        self.pubsub_client: Optional[Client] = None

        self.attacks = defaultdict(list)
        self.bots = (
            "arachnobot",
            "nightbot",
            "pretzelrocks",
            "streamlabs",
            "commanderroot",
            "electricallongboard",
        )
        self.countdown_to: Optional[datetime.datetime] = None  # ! keep this here !
        self.last_messages = CaseInsensitiveDict()  # ! keep this here !

        self.dashboard: List[int] = []

        # self.player = sounds.AudioPlayer(callback=self.player_done)
        self.started = False
        self.sio_server = sio_server_
        self.timer = None
        self.game: Optional[GameConfig] = None
        # self.duels: Optional[DuelStats] = None
        self.pubsub_events: List[Dict] = []
        self.title = ""
        self.game_name = ""

        self.load_pearls()

        self.play_sound_lock = asyncio.Lock()
        self.current_sound = ""

        self.bot_ready = False

        self.radio_station = ""
        self.radio_now_playing: dict[str, str] = {}
        self.radio_now_playing_cover: dict[str, str] = {}

    async def get_announce_text(self, now_=False):
        await self.get_game_v5()

        delta = self.countdown_to - datetime.datetime.now()
        delta_m = delta.seconds // 60
        if delta_m > 0 and not now_:
            delta_text = "примерно " + numeral.get_plural(
                delta_m, ("минута", "минуты", "минут")
            )
        else:
            delta_text = "меньше минуты"

        #        delta_text = "всё время мира"

        announcement = [
            (
                f'Паучок запустил стрим "{self.title}" '
                f'по игре "{self.game_name}"! У вас есть {delta_text} чтобы'
                " открыть стрим - <https://twitch.tv/iarspider>!"
            ),
            (
                f'Паучок запустил стрим "{self.title}" '
                f'по игре "{self.game_name}"! У вас есть {delta_text} чтобы'
            ),
        ]

        return announcement

    async def play_sound(self, sound: str | bytes, is_temporary: bool = False):
        logger.info("play_sound - waiting for lock")
        await self.play_sound_lock.acquire()
        logger.info("play_sound - lock acquired")

        if not self.sio_server:
            logger.info("Playing sound", sound, "using mplayer")
            self.current_sound = ""

            if not is_temporary:
                soundfile = str(pathlib.Path(__file__).parent / sound)
            else:
                soundfile = sound
                self.current_sound = soundfile

            logger.debug(
                f"play sound from{' temporary' if is_temporary else ''} {soundfile}"
            )
            await self.bot_play_sound(soundfile)
        else:
            logger.info(f"Playing sound {sound} using dashboard")
            with open(sound, "rb") as mp3_file:
                chunk_size = 4096  # Size of each chunk
                while True:
                    chunk = mp3_file.read(chunk_size)
                    if not chunk:
                        break
                    logger.debug("Sending chunk...")
                    await self.sio_server.emit("mp3_chunk", chunk)
                    logger.debug("Chunk sent")
                logger.debug("Sending mp3_end...")
                await self.sio_server.emit(
                    "mp3_end",
                )
                logger.debug("Sending mp3_end - done")

    # TODO: Temporary solution until implemented upstream
    async def bot_play_sound(self, filename: str):
        """Plays a sound file using mplayer asynchronously, returning immediately."""
        full_path = os.path.abspath(filename)  # Ensure full path
        cmd = ["mplayer", full_path]

        async def run_player():
            """Runs mplayer and calls player_done() when finished."""
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,  # Suppress output
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.communicate()  # Wait for playback to finish
            await self.player_done()  # Call the callback function

        asyncio.create_task(run_player())  # Run in background and return immediately

    def load_pearls(self):
        self.pearls = []
        with open("pearls.txt", "r", encoding="utf-8") as f:
            for line in f:
                self.pearls.append(line.strip())

    def write_pearls(self):
        with open("pearls.txt", "w", encoding="utf-8") as f:
            for pearl in self.pearls:
                # noinspection PyTypeChecker
                print(pearl, file=f)

    async def player_done(self):
        self.play_sound_lock.release()
        if self.current_sound:
            logger.info(f"Done playing sound {self.current_sound}")
            count = 60
            while count > 0:
                try:
                    os.unlink(self.current_sound)
                except PermissionError as e:
                    logger.warning(
                        f"Failed to unlink tempfile "
                        f"{os.path.basename(self.current_sound)}: {str(e)}"
                    )
                    count -= 1
                    time.sleep(1)
                else:
                    break
            else:
                logger.error(f"Giving up on file {self.current_sound}")
        else:
            logger.info(f"Done playing some sound")
        pass

    def call_components(self, method):
        for cog in self._components.values():
            cog_method = getattr(cog, method, None)
            if cog_method:
                cog_method()

    # @staticmethod
    # def check_sender(ctx: commands.Context, users: Union[str, Iterable[str]]):
    #     if isinstance(users, str):
    #         users = (users,)
    #
    #     return ctx.chatter.name in users

    # TODO
    async def my_run_commercial(self, user_id, length=90):
        # return
        try:
            user = self.create_partialuser(user_id=user_id)
            await user.start_commercial(length=length)
        except HTTPException:
            pass
        return

    async def get_game_v5(self):
        channel_info = await self.fetch_channels([OWNER_ID])
        game_changed = False

        if (
            self.game_name != channel_info[0].game_name
            or self.title != channel_info[0].title
        ):
            game_changed = True

        self.game_name = channel_info[0].game_name
        self.title = channel_info[0].title
        logger.info(f"get_game_v5: game is {self.game_name}, title is {self.title}")

        self.game = GameConfig.get_or_none(game=self.game_name)
        if self.game is None:
            self.game = GameConfig.create(game=self.game_name)
            self.game.save()

        # nightbot_api.enable_disable_timer(self.nightbot, "Мультитвич", self.game.mt)
        # nightbot_api.enable_disable_timer(self.nightbot, "Neputin", not self.game.mt)

        # if self.game.mt:
        # commands = nightbot_api.get_commands(self.nightbot)
        # if self.game.mt_str.startswith("http"):
        # msg = "Мультитвич: " + self.game.mt_str
        # else:
        # msg = "Мультитвич: https://www.multitwitch.tv/" + self.game.mt_str
        # cmd_id = None
        # for cmd in commands:
        # if cmd["name"] == "!mt":
        # cmd_id = cmd["_id"]
        # break
        # if not cmd_id:
        # logger.error("!mt command not found!")
        # else:
        # nightbot_api.put_command(self.nightbot, cmd_id, {"message": msg})

        if game_changed:
            self.call_components("update")

    def add_user(self, user: Chatter):
        name = user.name.lower()
        display_name = user.display_name.lower()
        if name not in self.viewers:
            self.viewers[name] = user

        if display_name not in self.viewers:
            self.viewers[display_name] = user

        if not (
            name in self.greeted
            or display_name in self.greeted
            or name in self.bots
            or name == "iarspider"
        ):
            self.greeted.add(name)
            self.greeted.add(display_name)
            if user.subscriber or user.founder:
                logger.info("Start custom greeter")
                if os.path.exists(f"greetings//{name.lower()}.mp3"):
                    logger.info("Found from 1st try")
                    asyncio.ensure_future(
                        self.play_sound(f"greetings//{name.lower()}.mp3")
                    )
                    return
                else:
                    logger.info(f"No such file: greetings//{name.lower()}.mp3")

                if os.path.exists(f"greetings//{display_name.lower()}.mp3"):
                    logger.info("Found from 2nd try")
                    asyncio.ensure_future(
                        self.play_sound(f"greetings//{display_name.lower()}.mp3")
                    )
                    return
                else:
                    logger.info(f"No such file: greetings//{display_name.lower()}.mp3")

                i = 4
            else:
                i = random.randint(1, 3)
            asyncio.ensure_future(
                self.play_sound(f"sound//TOWER_TITLES@GREETING_{i}@JES.mp3")
            )

    # Fill in missing stuff
    def get_component(self, name):
        ret = super().get_component(name)
        if ret is None:
            logger.error(
                f"No such cog: {name}, known components: {','.join(self._components.keys())}"
            )

        return ret

    async def send_viewer_joined(self, user: Chatter, sid: Optional[int] = None):
        # DEBUG
        # return
        if user.name.lower() in self.bots:
            return

        femme = (
            user.name.lower() in twitch_ladies
            or user.display_name.lower() in twitch_ladies
        )

        if user.subscriber:
            status = "spider"
        elif user.moderator:
            status = "hammer"
        elif user.vip:
            status = "award"
        else:
            status = "eye"

        color = user.color.hex if user.color else "#FFFFFF"

        # logger.debug(f"Tags: {user.tags}")
        logger.debug(f"Badges: {user.badges}")
        logger.debug(
            f"Send user {user.display_name} with status {status} and color {color}"
        )

        item = {
            "action": "add",
            "value": {
                "name": user.display_name,
                "status": status,
                "color": color,
                "femme": femme,
            },
        }
        if self.sio_server is not None:
            await self.sio_server.emit(item["action"], item["value"], to=sid)
        else:
            logger.warning("send_viewer_joined: sio_server is none!")

    # async def event_message(self, chat_message: ChatMessage):
    #     chat_message.text = re.sub(r"^!\s+", "!", chat_message.text)
    #     for fg in chat_message.fragments:
    #         if fg.text:
    #             fg.text = re.sub(r"^!\s+", "!", fg.text)
    #             break
    #
    #     await self.process_commands(chat_message)
    #
    async def on_dashboard_connected(self, sid):
        if self.sio_server is None:
            return

        ids = set()
        tasks = []

        await self.sio_server.emit("reset", "", to=sid)

        viewer: Chatter
        for viewer in self.viewers.values():
            if viewer.id not in ids:
                ids.add(viewer.id)
                tasks.append(asyncio.create_task(self.send_viewer_joined(viewer)))

        for item in self.pubsub_events:
            tasks.append(
                asyncio.create_task(self.sio_server.emit(item["action"], item["value"]))
            )

        # noinspection PySimplifyBooleanCheck
        if tasks != []:
            await asyncio.wait(tasks)

    async def my_get_stream(self) -> Stream:
        logger.debug(f"Getting stream for {self.owner_id=}")
        stream = await self.fetch_streams(user_ids=[self.owner_id])
        logger.debug(stream)
        while not stream:
            logger.info("Stream not detected yet, sleeping...")
            await asyncio.sleep(5)

        logger.info(f"Got stream {stream[0]}")
        return stream[0]

    async def send_message(self, msg):
        user = self.create_partialuser(user_id=self.owner_id)
        await user.send_message(sender=self.user, message=msg)

    # region Boilerplate

    ####################
    # Boilerplate code #
    ####################

    async def setup_hook(self) -> None:
        # Bot: http://localhost:4343/oauth?scopes=user:read:chat%20user:write:chat%20user:bot%20channel:read:redemptions%20channel:manage:redemptions%20channel:manage:broadcast%20channel:edit:commercial
        # User: http://localhost:4343/oauth?scopes=channel:bot%20channel:read:redemptions%20channel:manage:redemptions%20user:edit:broadcast
        # Subscribe to read chat (event_message) from our channel as the bot...
        # This creates and opens a websocket to Twitch EventSub...
        subscription = eventsub.ChatMessageSubscription(
            broadcaster_user_id=OWNER_ID, user_id=BOT_ID
        )
        await self.subscribe_websocket(payload=subscription)
        #
        # Subscribe and listen to when a stream goes live...
        # For this example listen to our own stream...
        subscription = eventsub.StreamOnlineSubscription(broadcaster_user_id=OWNER_ID)
        await self.subscribe_websocket(payload=subscription)

        subscription = eventsub.ChannelPointsRedeemAddSubscription(
            broadcaster_user_id=OWNER_ID
        )
        await self.subscribe_websocket(
            payload=subscription, as_bot=False, token_for=OWNER_ID
        )

    async def add_token(
        self, token: str, refresh: str
    ) -> twitchio.authentication.ValidateTokenPayload:
        # Make sure to call super() as it will add the tokens interally and return us some data...
        resp: twitchio.authentication.ValidateTokenPayload = await super().add_token(
            token, refresh
        )

        # Store our tokens in a simple SQLite Database when they are authorized...
        with open(self.token_filename, "r") as f:
            tokens = json.load(f)

        tokens[resp.user_id] = {"token": token, "refresh": refresh}

        with open(self.token_filename, "w") as f:
            # noinspection PyTypeChecker
            json.dump(tokens, f)

        logger.info(f"Added token to the database for user: {resp.user_id}")
        return resp

    async def load_tokens(self, path: str | None = None) -> None:
        # We don't need to call this manually, it is called in .login() from .start() internally...
        with open(self.token_filename, "r") as f:
            tokens = json.load(f)

        for row in tokens.values():
            await self.add_token(row["token"], row["refresh"])

    async def event_ready(self) -> None:
        logger.info(f"Ready | {self.bot_id}")
        self.bot_ready = True
        await self.get_game_v5()

    # endregion

    async def event_command_error(self, payload: CommandErrorPayload):
        if isinstance(payload.exception, CommandOnCooldown):
            await payload.context.reply(
                f"Подожди {payload.exception.remaining:.0f} сек. перед повторным использованием команды"
            )
        else:
            await super().event_command_error(payload)

    async def update_track_text(self):
        if not self.sio_server:
            logger.warning("sio_server is none!")
            return
        if twitch_bot.radio_station:
            await self.sio_server.emit("track_show")
            await self.sio_server.emit(
                "track_update",
                {
                    "text": twitch_bot.radio_now_playing.get(self.radio_station, ""),
                    "cover": twitch_bot.radio_now_playing_cover.get(
                        self.radio_station, ""
                    ),
                },
            )

        else:
            await self.sio_server.emit("track_hide")


def main() -> None:
    global CLIENT_ID, CLIENT_SECRET, BOT_ID, OWNER_ID, twitch_bot

    CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
    CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
    BOT_ID = os.getenv("TWITCH_BOT_ID")
    OWNER_ID = os.getenv("TWITCH_OWNER_ID")

    random.seed()

    setup_logging("bot.log", color=True, debug=False, http_debug=False)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    sio_server = socketio.AsyncServer(
        async_mode="asgi",
        logger=False,
        engineio_logger=False,
        cors_allowed_origins=["https://fr.iarazumov.com", "http://overlay.home"],
    )
    app = socketio.ASGIApp(sio_server, socketio_path="/ws")
    config = uvicorn.Config(
        app, host="0.0.0.0", port=8081, ws="websockets-sansio", lifespan="on"
    )
    # noinspection PyUnusedLocal
    server = uvicorn.Server(config)

    # noinspection PyUnresolvedReferences,PyUnusedLocal
    @sio_server.on("connect")
    async def on_ws_connected(sid, _):
        global twitch_bot
        while not twitch_bot.bot_ready:
            await asyncio.sleep(0.1)

        twitch_bot.dashboard.append(sid)
        asyncio.ensure_future(twitch_bot.on_dashboard_connected(sid))
        logger.info(f"Dashboard connected with id {sid}")
        ripcog: "RIPCog" = twitch_bot.get_component("RIPCog")
        await ripcog.display_rip()
        plushchcog = twitch_bot.get_component("PluschCog")
        plushchcog.write_plusch(init=True)
        await twitch_bot.update_track_text()

    @sio_server.on("disconnect")
    async def on_ws_disconnected(sid):
        global twitch_bot
        if sid in twitch_bot.dashboard:
            logger.warning(f"Dashboard {sid} disconnected!")
            twitch_bot.dashboard.remove(sid)

    # noinspection PyUnresolvedReferences,PyUnusedLocal
    @sio_server.on("rip")
    async def on_ws_rip(sid):
        logger.info(f"Received message: rip")
        ripcog: "RIPCog" = twitch_bot.get_component("RIPCog")
        msg = await ripcog.do_rip(n=1)
        await twitch_bot.send_message(msg)

    # noinspection PyUnresolvedReferences,PyUnusedLocal
    @sio_server.on("unrip")
    async def on_ws_unrip(sid):
        logger.info(f"Received message: unrip")
        ripcog: "RIPCog" = twitch_bot.get_component("RIPCog")
        msg = await ripcog.do_rip(n=-1)
        await twitch_bot.send_message(msg)

    # noinspection PyUnresolvedReferences,PyUnusedLocal
    @sio_server.on("break")
    async def on_ws_break(sid):
        logger.info(f"Received message: break")
        cog: "OBSCog" = twitch_bot.get_component("OBSCog")
        cog.do_pause(None, False)
        await twitch_bot.send_message("Начать перепись населения!")

    # noinspection PyUnresolvedReferences,PyUnusedLocal
    @sio_server.on("resume")
    async def on_ws_resume(sid):
        logger.info(f"Received message: resume")
        cog: "OBSCog" = twitch_bot.get_component("OBSCog")
        msg = await cog.do_resume(None)
        await twitch_bot.send_message(msg)

    @sio_server.on("audioFinished")
    async def on_ws_audio_finished(sid):
        _ = sid
        logger.info(f"Received message: audioFinished")
        twitch_bot.play_sound_lock.release()

    # noinspection PyUnresolvedReferences,PyUnusedLocal
    @sio_server.on("*")
    def catch_all(event, sid, data):
        logger.warning(f"Unhandled event {event} (data {data})")
        pass

    # Run bot
    if sio_server is None:
        logger.warning("sio_server is none!")

    twitch_bot = Bot(token_filename="twitch_token.json", sio_server_=sio_server)
    listener = VLCTrackListener()
    radio_listener = RadioTrackListener()

    async def vlc_consumer(listener_: VLCTrackListener, twitch_bot_: Bot):
        while True:
            event = await listener_.queue.get()
            logger.info(f"📼 Now playing: {event['artist']} — {event['title']}")
            twitch_bot_.radio_now_playing["vlc"] = (
                f"{event['artist']} — {event['title']}"
            )
            twitch_bot_.radio_now_playing_cover["vlc"] = event["cover"]
            await twitch_bot_.update_track_text()

    async def radio_consumer(listener_: RadioTrackListener, twitch_bot_: Bot):
        while True:
            event = await listener_.queue.get()
            twitch_bot_.radio_now_playing[event["station"]] = (
                f"{event['artist']} — {event['title']}"
            )
            twitch_bot_.radio_now_playing_cover[event["station"]] = event["cover"]
            logger.info(
                f"📻️ Now playing on {event['station']} : {event['artist']} — {event['title']}"
            )
            await twitch_bot_.update_track_text()

    async def runner() -> None:
        await twitch_bot.load_module("components.misccog")
        if os.getenv("OBSWS_ADDRESS") is not None:
            logger.info("Loading module obscog")
            await twitch_bot.load_module("components.obscog")

        for extension in (
            "discordcog",
            "pluschcog",
            "ripcog",
            "SLCog",
            "elfcog",
            "duelcog",
            "pointcog",
        ):  # 'raidcog', 'vmodcog', 'musiccog'
            # noinspection PyUnboundLocalVariable
            logger.info(f"Loading module {extension}")
            await twitch_bot.load_module(f"components.{extension}")

        twitch_bot.call_components("setup")

        async with asyncio.TaskGroup() as tg:
            tg.create_task(twitch_bot.start())
            tg.create_task(server.serve())
            tg.create_task(keyboard_listener(twitch_bot))
            tg.create_task(listener.run())
            tg.create_task(vlc_consumer(listener, twitch_bot))
            tg.create_task(radio_listener.run())
            tg.create_task(radio_consumer(radio_listener, twitch_bot))

        await twitch_bot.close()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        with open("shutdown", "w") as f:
            print("1", file=f)
        logger.warning("Shutting down due to KeyboardInterrupt...")


# Patched version of socketio.AsyncManager.emit,
# see https://github.com/miguelgrinberg/python-socketio/pull/941
# Can't update socketio/engineio because SL is using old socketio
# version that is not supported in modern versions
# noinspection PyProtectedMember, PySimplifyBooleanCheck,PyUnusedLocal
async def emit(
    self, event, data, namespace, room=None, skip_sid=None, callback=None, **kwargs
):
    """Emit a message to a single client, a room, or all the clients
    connected to the namespace.

    Note: this method is a coroutine.
    """
    if namespace not in self.rooms or room not in self.rooms[namespace]:
        return
    tasks = []
    if not isinstance(skip_sid, list):
        skip_sid = [skip_sid]
    for sid in self.get_participants(namespace, room):
        if sid not in skip_sid:
            if callback is not None:
                id_ = self._generate_ack_id(sid, namespace, callback)
            else:
                id_ = None
            tasks.append(
                asyncio.create_task(
                    self.server._emit_internal(sid, event, data, namespace, id_)
                )
            )
    if tasks == []:  # pragma: no cover
        return
    await asyncio.wait(tasks)


#
# async def do_wizlight_disco():
#     states = []
#     logger.info("Starting disco...")
#     for _ in wiz_config:
#         b = wizlight(**_)
#         state = await b.updateState()
#         if not state.get_state():
#             logger.error(f"!!! Lightbulb {_['ip']} is off !!!")
#             states.append(None)
#             continue
#
#         states.append(
#             {
#                 "speed": state.get_speed(),
#                 "scene": state.get_scene_id(),
#                 "brightness": state.get_brightness(),
#             }
#         )
#
#         await b.turn_on(PilotBuilder(speed=200, scene=4, brightness=255))
#         await b.async_close()
#         del b
#
#     logger.info("Sleeping...")
#     await asyncio.sleep(180)
#     logger.info("Restoring...")
#
#     for i, _ in enumerate(wiz_config):
#         if states[i] is not None:
#             b = wizlight(**_)
#             await b.turn_on(PilotBuilder(**states[i]))
#             await b.async_close()
#             del b
#
#     await asyncio.sleep(1)


def patch_socketio():
    socketio.AsyncManager.emit = emit


if __name__ == "__main__":
    load_dotenv()
    patch_socketio()
    main()

'''
import asyncio
import uuid
from typing import AsyncIterable, Optional, Union, Callable, Awaitable, BinaryIO

class SoundManager:
    def __init__(self, ws_client, *, ack_timeout: float = 15.0):
        self.ws = ws_client  # должен уметь send_json / send_bytes
        self.ack_timeout = ack_timeout
        self._lock = asyncio.Lock()
        self._pending_acks: dict[str, asyncio.Event] = {}
        # на случай reconnect — можно держать флаг готовности
        self._overlay_ready = asyncio.Event()

    # вызывать при установке WS-соединения оверлеем
    def on_overlay_ready(self):
        self._overlay_ready.set()

    # вызывать из WS-ридера при сообщении типа {"type":"sound_done","id": "..."}
    def on_overlay_ack(self, sound_id: str):
        ev = self._pending_acks.get(sound_id)
        if ev:
            ev.set()

    async def play_sound(
        self,
        source: Union[str, bytes, AsyncIterable[bytes], Callable[[], AsyncIterable[bytes]]],
        *,
        mime: str = "audio/mpeg",
        meta: Optional[dict] = None,
        require_ready: bool = True,
        sound_id: Optional[str] = None,
    ):
        """
        source:
          - str: путь к файлу
          - bytes: весь буфер (не рекомендуется для больших)
          - AsyncIterable[bytes]: поток чанков (например, TTS)
          - Callable -> AsyncIterable[bytes]: лениво создаём стрим (удобно для TTS)
        """
        if require_ready:
            await self._overlay_ready.wait()

        sid = sound_id or uuid.uuid4().hex
        ack_event = asyncio.Event()
        self._pending_acks[sid] = ack_event

        await self._lock.acquire()
        try:
            # 1) сообщаем о старте
            await self.ws.send_json({
                "type": "sound_start",
                "id": sid,
                "mime": mime,
                "meta": meta or {},
            })

            # 2) шлём чанки
            async for chunk in self._iter_chunks(source):
                # протокол: бинарные фреймы, или json с base64 — зависит от твоего оверлея
                await self.ws.send_bytes(chunk)

            # 3) сигнал конца
            await self.ws.send_json({
                "type": "sound_end",
                "id": sid,
            })

            # 4) ждём ACK от оверлея
            try:
                await asyncio.wait_for(ack_event.wait(), timeout=self.ack_timeout)
            except asyncio.TimeoutError:
                # важно залогировать и продолжить — чтобы лок не завис
                # при желании можно шлёпнуть команду стопа на оверлей
                # await self.ws.send_json({"type":"sound_abort","id":sid})
                raise

        finally:
            # аккуратно чистим состояние и точно отпускаем лок
            self._pending_acks.pop(sid, None)
            if self._lock.locked():
                self._lock.release()

    # ---------- helpers ----------

    async def _iter_chunks(self, source) -> AsyncIterable[bytes]:
        # путь к файлу
        if isinstance(source, str):
            # читаем порциями (без mmap, но можно и его)
            async def file_iter(path: str):
                loop = asyncio.get_running_loop()
                # открытие файла в потоковом треде, чтобы не блокировать
                def _read_all():
                    with open(path, "rb") as f:
                        while True:
                            b = f.read(64 * 1024)
                            if not b:
                                break
                            yield b
                # оборачиваем синхронного генератора в асинхронный
                for chunk in await loop.run_in_executor(None, lambda: list(_read_all())):
                    yield chunk
            async for c in file_iter(source):
                yield c
            return

        # готовый буфер
        if isinstance(source, (bytes, bytearray)):
            yield bytes(source)
            return

        # асинхронный итерируемый поток
        if hasattr(source, "__aiter__"):
            async for c in source:
                yield c
            return

        # фабрика стрима
        if callable(source):
            async for c in source():
                yield c
            return

        raise TypeError("Unsupported sound source")
'''
