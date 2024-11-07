import asyncio
import datetime
import http.client as http_client
import logging
import os
import pathlib
import random
import string
import sys
import time
from collections import defaultdict, deque
from multiprocessing import Process
from typing import Union, Iterable, Optional, List, Dict

import peewee
import requests
import socketio
import uvicorn
from dotenv import load_dotenv
from loguru import logger
from pywizlight import wizlight, PilotBuilder
from requests.structures import CaseInsensitiveDict
from twitchio import User, Message, Channel, Chatter, Client
from twitchio.ext import commands, sounds, pubsub

# noinspection PyUnresolvedReferences
import nightbot_api
import twitch_api
from aio_timer import Periodic
from config import *

from twitch_commands import twitch_command_aliased

httpclient_logger = logging.getLogger("http.client")
proc: Process
dashboard_timer: Periodic
sl_client: socketio.AsyncClient
database = peewee.SqliteDatabase(database_file)
# PubSub client
client: Optional[Client] = None


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


class GameConfig(peewee.Model):
    game = peewee.CharField(primary_key=True)
    rip_total = peewee.IntegerField(default=0)
    rip_enabled = peewee.BooleanField(default=True)
    music_enabled = peewee.BooleanField(default=False)
    window = peewee.CharField(default="X")
    infinite = peewee.BooleanField(default=False)
    inexact = peewee.BooleanField(default=False)
    mt = peewee.BooleanField(default=False)
    mt_str = peewee.CharField(default="iarspider/moar__/danzio_plagius")
    watchfile = peewee.CharField(default="")
    rip_emoji = peewee.CharField(default="☠")

    class Meta:
        database = database


class DuelStats(peewee.Model):
    attacker = peewee.TextField()
    defender = peewee.TextField()
    losses = peewee.IntegerField(null=False, default=0)
    wins = peewee.IntegerField(null=False, default=0)

    class Meta:
        table_name = "duelstats"
        database = database
        primary_key = peewee.CompositeKey("attacker", "defender")


class Bot(commands.Bot):
    def __init__(self, sio_server_, initial_channels=None):
        super().__init__(
            token=os.getenv("TWITCH_CHAT_PASSWORD"),
            client_id=os.getenv("TWITCH_CHAT_CLIENT_ID"),
            nick="arachnobot",
            prefix="!",
            initial_channels=initial_channels or ["#iarspider"],
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

        self.initial_channels = initial_channels or ["#iarspider"]

        self.viewers = CaseInsensitiveDict()
        self.greeted = set()

        self.db = {}
        self.pearls = []

        self.streamer_id = -1

        self.vmod = None
        self.vmod_active = False
        self.pubsub_client: Optional[Client] = None

        self.attacks = defaultdict(list)
        self.bots = (
            self.nick,
            "nightbot",
            "pretzelrocks",
            "streamlabs",
            "commanderroot",
            "electricallongboard",
        )
        self.countdown_to: Optional[datetime.datetime] = None  # ! keep this here !
        self.last_messages = CaseInsensitiveDict()  # ! keep this here !

        self.dashboard: List[int] = []

        self.player = sounds.AudioPlayer(callback=self.player_done)
        self.started = False
        self.sio_server = sio_server_
        self.timer = None
        self.game: Optional[GameConfig] = None
        # self.duels: Optional[DuelStats] = None
        self.pubsub_events: List[Dict] = []
        self.title = ""

        self.load_pearls()

        self.play_sound_lock = asyncio.Lock()
        self.current_sound = ""

        # self.nightbot = nightbot_api.get_nightbot_session(
        # os.getenv("NIGHTBOT_CLIENT_ID"),
        # os.getenv("NIGHTBOT_CLIENT_SECRET"),
        # nightbot_redirect_url
        # )

    async def send_message(self, message):
        channel: Channel = self.get_channel(self.initial_channels[0].lstrip("#"))
        asyncio.ensure_future(channel.send(message))

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

    def call_cogs(self, method):
        for cog in self.cogs.values():
            cog_method = getattr(cog, method, None)
            if cog_method:
                cog_method()

    def get_game_v5(self):
        r = requests.get(
            f"https://api.twitch.tv/helix/channels?broadcaster_id={self.streamer_id}&",
            headers={
                "Authorization": f"Bearer {os.getenv('TWITCH_CHAT_PASSWORD')}",
                "Client-ID": os.getenv("TWITCH_CHAT_CLIENT_ID"),
            },
        )

        try:
            r.raise_for_status()
        except requests.RequestException as e:
            logger.error("Request to Helix API failed!" + str(e))
            self.game = GameConfig.create(game="")
            return

        if "error" in r.json():
            logger.error("Request to Helix API failed!" + r.json()["message"])
            self.game = GameConfig.create(game="")
            return
        #
        # with open("game.json", "w") as f:
        #     json.dump(r.json(), f)

        self.title = r.json()["data"][0]["title"]
        game_name = r.json()["data"][0]["game_name"]
        logger.info(f"get_game_v5: game is {game_name}, title is {self.title}")
        self.game = GameConfig.get_or_none(game=game_name)
        if self.game is None:
            self.game = GameConfig.create(game=game_name)
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

        self.call_cogs("update")

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
            if user.is_subscriber or user.badges.get("founder", -1) != -1:
                logger.info("Start custom greeter")
                if os.path.exists(f"greetings\\{name.lower()}.mp3"):
                    logger.info("Found from 1st try")
                    asyncio.ensure_future(
                        self.play_sound(f"greetings\\{name.lower()}.mp3")
                    )
                    return
                else:
                    logger.info(f"No such file: greetings\\{name.lower()}.mp3")

                if os.path.exists(f"greetings\\{display_name.lower()}.mp3"):
                    logger.info("Found from 2nd try")
                    asyncio.ensure_future(
                        self.play_sound(f"greetings\\{display_name.lower()}.mp3")
                    )
                    return
                else:
                    logger.info(f"No such file: greetings\\{display_name.lower()}.mp3")

                i = 4
            else:
                i = random.randint(1, 3)
            asyncio.ensure_future(
                self.play_sound(f"sound\\TOWER_TITLES@GREETING_{i}@JES.mp3")
            )

    # Fill in missing stuff
    def get_cog(self, name):
        try:
            return self.cogs[name]
        except KeyError:
            logger.error(
                f"No such cog: {name}, known cogs: {','.join(self.cogs.keys())}"
            )
            return None

    # def set_ws_server(self, sio_server):
    #     # print("@@ set_ws_server @@")
    #     if sio_server is not None and self.sio_server is None:
    #         # print("@@ set sio_server @@")
    #         self.sio_server = sio_server
    #         self.timer.cancel()

    async def event_ready(self):
        logger.info(f"Ready | {self.nick}")
        c: Channel = self.connected_channels[0]
        u: List["User"] = await self.fetch_users(names=[c.name])
        uu: User = u[0]
        self.streamer_id = uu.id

        # noinspection PyProtectedMember
        topics = [pubsub.channel_points(self.pubsub_client._http.token)[uu.id]]
        # noinspection PyUnresolvedReferences
        await self.pubsub_client.pubsub.subscribe_topics(topics)
        await self.pubsub_client.connect()

        # self.timer = Periodic("ws_server", 1, self.set_ws_server, self.loop)
        # await self.timer.start()

        self.get_game_v5()

    @staticmethod
    def get_emotes(tag, msg):
        # example tag: '306267910:5-11,20-26/74409:13-18'
        res = []
        if tag:
            emotes_list = tag.split("/")
            for emote_data in emotes_list:
                emote_id, ranges = emote_data.split(":")
                # emote_id = int(emote_id)

                if "," not in ranges:
                    ranges = [ranges]
                else:
                    ranges = ranges.split(",")

                for range_ in ranges:
                    start, end = map(int, range_.split("-"))
                    end += 1
                    res.append(
                        {
                            "id": emote_id,
                            "start": start,
                            "end": end,
                            "text": msg[start:end],
                        }
                    )

        return res

    async def event_message(self, message: Message):
        if message.raw_data.startswith(
            "> " ":arachnobot!arachnobot@arachnobot.tmi.twitch.tv"
        ):
            return

        if message.author is None:
            d = datetime.datetime.now().timestamp()
            fn = f"msg_{d}.json"
            with open(fn, "w") as f:
                f.write(message.raw_data)
            logger.warning(f"event_message with no author! See {fn} for details")
            return

        if message.author.name.lower() not in self.viewers:
            # tags = ','.join(f'{k} = {v}' for k, v in message.tags.items())
            # print(f"Message from {message.author}, tags: {tags}")
            # print(f"Raw data: {message.raw_data}")
            await self.send_viewer_joined(message.author)
            logger.debug("JOIN sent")
        #
        # self.viewers.add(message.author.name.lower())
        # if message.author.is_mod:
        #     self.mods.add(message.author.name.lower())
        # if message.author.is_subscriber:
        #     self.subs.add(message.author.name.lower())
        #
        # if message.author.badges.get('vip', 0) == 1:
        #     self.vips.add(message.author.name.lower())
        self.add_user(message.author)

        if message.author.name not in self.last_messages:
            self.last_messages[message.author.name] = deque(maxlen=10)

        if message.author.name.lower() not in self.bots:
            emotes = self.get_emotes(message.tags["emotes"], message.content)
            # todo: chat2html?

            if not message.content.startswith("!"):
                tmp_emotes = set(x["text"] for x in emotes)
                self.last_messages[message.author.name].append(
                    (message.content, tmp_emotes)
                )
                logger.debug(
                    f"Updated last messages for {message.author.name}, "
                    + f"will remember last "
                    f"{len(self.last_messages[message.author.name])}"
                )

        if message.content.startswith("!"):
            message.content = "!" + message.content.lstrip("! ")
            try:
                command, args = message.content.split(" ", 1)
                args = " " + args
            except ValueError:
                command = message.content
                args = ""
            message.content = command.lower() + args

        logger.debug("handle_command start: %s", message)
        await self.handle_commands(message)
        logger.debug("handle_command end: %s", message)

    # async def event_join(self, user):
    #     if user.name.lower() not in self.viewers:
    #         # await self.send_viewer_joined(user.name)
    #         # self.viewers.add(user:wq.name.lower())
    #         logger.info(f"User {user.name} joined! tags {user.tags}, badges {
    #         user.badges}")

    async def event_part(self, user: User):
        if user.name.lower() in self.viewers:
            await asyncio.ensure_future(self.send_viewer_left(user))

        try:
            del self.viewers[user.name.lower()]
        except KeyError:
            pass

        try:
            del self.viewers[user.display_name.lower()]
        except (KeyError, AttributeError):
            pass

    async def event_pubsub_channel_points(
        self, event: pubsub.PubSubChannelPointsMessage
    ):
        user = await self.create_user(event.user.id, event.user.name).fetch()
        # user = await event.user.fetch()
        await self.do_reward(user, event.reward.title, event.input)

    # noinspection PyUnusedLocal
    async def do_reward(self, user: User, title: str, prompt: str):
        item = None
        requestor = user.display_name or user.name
        match title:
            case "Смена голоса на 1 минуту":
                vmod = self.get_cog("VMcog")
                # noinspection PyUnresolvedReferences
                asyncio.ensure_future(vmod.activate_voicemod())
            case "Обнять стримера":
                logger.debug(f"Queued redepmtion: hugs, {requestor}")
                item = {"action": "event", "value": {"type": "hugs", "from": requestor}}
                channel: Channel = self.get_channel(
                    self.initial_channels[0].lstrip("#")
                )
                await self.send_message(
                    f"{requestor} обнял стримера! Спасибо, {requestor}!"
                )
            case "Обнять чатик":
                logger.debug(f"Queued redepmtion: hugs, {requestor}")
                item = {"action": "event", "value": {"type": "hugs", "from": requestor}}
                channel: Channel = self.get_channel(
                    self.initial_channels[0].lstrip("#")
                )
                await self.send_message(f"{requestor} обнял чатик!")

            case "Ничего":
                logger.debug(f"Queued redepmtion: nothing, {requestor}")
                await self.play_sound("my_sound\\nothing0.mp3")
                item = {
                    "action": "event",
                    "value": {"type": "nothing", "from": requestor},
                }
            case "Дизайнерское Ничего":
                logger.debug(f"Queued redepmtion: designer nothing, {requestor}")
                await self.play_sound("my_sound\\designer_nothing0.mp3")
                item = {
                    "action": "event",
                    "value": {"type": "nihil", "from": requestor},
                }
            case "Эксклюзивное Ничего, pro edition":
                logger.debug(f"Queued redepmtion: pro nothing, {requestor}")
                await self.play_sound("my_sound\\exclusive_nothing_pro.mp3")
                item = {
                    "action": "event",
                    "value": {"type": "nihil", "from": requestor},
                }
            case "Стримлер! Не горбись!":
                logger.debug(f"Queued redepmtion: sit, {requestor}")
                await self.play_sound("my_sound\\StraightenUp.mp3")
                item = {"action": "event", "value": {"type": "sit", "from": requestor}}
            case "Распылить упорин":
                logger.debug(f"Queued redepmtion: fun, {requestor}")
                item = {"action": "event", "value": {"type": "fun", "from": requestor}}
                s = random.choice(
                    ["Nice01", "Nice02", "ThatWasFun01", "ThatWasFun02", "ThatWasFun03"]
                )
                await self.play_sound(f"sound\\Minion General Speech@ignore@{s}.mp3")
                asyncio.ensure_future(do_wizlight_disco())
            case "Гори!":
                snd = random.choice(
                    ["Goblin_Burn_1", "Minion_BurnBurn", "Minion_FireNoHurt"]
                )
                await self.play_sound(f"sound\\Minion General Speech@ignore@{snd}.mp3")
            case "Лисо-Флешкино безумие":
                await self.play_sound("my_sound\\FoxFlashMadness.mp3")
            case "Ты всё испортил!":
                await self.play_sound("my_sound\\fail.mp3")
            case "СТОП-игра!":
                await self.play_sound("my_sound\\NO GOD, PLEASE NO.mp3")

        if item and (self.sio_server is not None):
            self.pubsub_events.append(item)
            await self.sio_server.emit(item["action"], item["value"])

    async def play_sound(self, sound: str | bytes, is_temporary: bool = False):
        logger.info("play_sound - waiting for lock")
        await self.play_sound_lock.acquire()
        logger.info("play_sound - lock acquired")

        if not self.sio_server:
            self.current_sound = ""

            if not is_temporary:
                soundfile = str(pathlib.Path(__file__).parent / sound)
            else:
                soundfile = sound
                self.current_sound = soundfile

            logger.debug(
                f"play sound from{' temporary' if is_temporary else ''} {soundfile}"
            )

            sound = sounds.Sound(soundfile)
            self.player.play(sound)
        else:
            with open(sound, "rb") as mp3_file:
                chunk_size = 4096  # Size of each chunk
                while True:
                    chunk = mp3_file.read(chunk_size)
                    if not chunk:
                        break
                    await self.sio_server.emit("mp3_chunk", chunk)
                await self.sio_server.emit(
                    "mp3_end",
                )
                self.play_sound_lock.release()

    async def send_viewer_joined(self, user: Chatter, sid: Optional[int] = None):
        # DEBUG
        # return
        if user.name.lower() in self.bots:
            return

        femme = (
            user.name.lower() in twitch_ladies
            or user.display_name.lower() in twitch_ladies
        )

        if user.is_subscriber:
            status = "spider"
        elif user.is_mod:
            status = "hammer"
        elif user.is_vip:
            status = "award"
        else:
            status = "eye"

        color = user.color

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

    async def send_viewer_left(self, user: User):
        # DEBUG
        # return
        if user.name.lower() in self.bots:
            return

        item = {"action": "remove", "value": user.display_name}
        if self.sio_server is not None:
            await self.sio_server.emit(item["action"], item["value"])
        else:
            logger.warning("send_viewer_joined: sio_server is none!")

    @staticmethod
    def check_sender(ctx: commands.Context, users: Union[str, Iterable[str]]):
        if isinstance(users, str):
            users = (users,)

        return ctx.author.name in users

    # async def event_raw_data(self, data):
    #     lines = data.splitlines(keepends=False)
    #     for line in lines:
    #         print('>', line)

    @twitch_command_aliased(name="roll", aliases=("dice", "кинь", "r"))
    async def roll(self, ctx: commands.Context):
        dices = []

        args = ctx.message.content.split()[1:]
        # print(args)
        if args is None or len(args) == 0:
            dices = ((1, 6),)
        else:
            for arg in args:
                # print("arg is", arg)
                if "d" not in arg:
                    continue
                num, sides = arg.split("d")
                try:
                    if not num:
                        num = 1
                    else:
                        num = int(num)
                    sides = int(sides)
                except ValueError:
                    continue

                if not ((0 < num <= 10) and (2 <= sides <= 100)):
                    continue

                dices.append((num, sides))
                # print("Rolling {0} {1}-sided dice(s)".format(num, sides))

        rolls = []
        for num, sides in dices:
            rolls.extend([random.randint(1, sides) for _ in range(num)])

        roll_sum = sum(rolls)
        # print("You rolled:", ";".join(str(x) for x in rolls), "sum is", roll_sum)
        if len(rolls) > 1:
            await ctx.send(
                "@{} выкинул: {}={}".format(
                    ctx.author.display_name, "+".join(str(x) for x in rolls), roll_sum
                )
            )
        elif len(rolls) == 1:
            await ctx.send("@{} выкинул: {}".format(ctx.author.display_name, roll_sum))

    @twitch_command_aliased(name="bite", aliases=("кусь",))
    async def bite(self, ctx: commands.Context):
        attacker = ctx.author.name.lower()
        attacker_name = ctx.author.display_name
        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !bite <кого>")
            return
        defender = args[0].strip("@")
        last_bite = self.db.get(attacker, 31525200.0)
        now = datetime.datetime.now()

        last_bite = datetime.datetime.fromtimestamp(last_bite)
        if (now - last_bite).seconds < 15 and attacker != "iarspider":
            await ctx.send(
                "Не кусай так часто, @{0}! Дай моим челюстям отдохнуть!".format(
                    attacker
                )
            )
            return

        if defender.lower() in self.bots:
            await ctx.send(
                f'С криком "Да здравствуют роботы!" @{ctx.author.display_name} '
                f"поцеловал блестящий "
                f"металлический зад {defender}а"
            )
            return

        if defender.lower() == "кусь" or defender.lower() == "bite":
            await ctx.send(
                f"@{ctx.author.display_name} попытался сломать систему, но не смог "
                f"BabyRage"
            )
            return

        what = random.choice(twitch_extra_bite.get(defender.lower(), (None,)))

        if attacker.lower() == defender.lower():
            what = what or " за жопь"
            await ctx.send(
                f"@{ctx.author.display_name} укусил сам себя{what}. Как, а главное - "
                f"зачем он это сделал? "
                f"Загадка..."
            )
            return

        if defender not in self.viewers and attacker != "iarspider":
            await ctx.send(
                "Кто такой или такая @" + defender + "? Я не буду кусать кого попало!"
            )
            return

        try:
            defender_name = self.viewers[defender].display_name
        except KeyError:
            defender_name = defender

        self.db[attacker] = now.timestamp()

        prefix = random.choice(("нежно ", "ласково "))
        target = what or ""

        if defender.lower() in twitch_no_bite:
            if defender.lower() == "babytigeronthesunflower":
                old_defender = "Тигру"
            else:
                old_defender = defender

            defender_name = self.viewers[attacker].display_name

            attacker_name = "стримлера"
            prefix = ""
            with_ = random.choice(
                (
                    "некроёжиком с тентаклями вместо колючек",
                    "зомбокувалдой",
                    "некочайником",
                )
            )
            target = " {0}, ибо {1} кусать нельзя!".format(with_, old_defender)

        if defender.lower() == "thetestmod":
            await ctx.send(
                "По поручению {0} {1} потрогал @{2} фирменным паучьим трогом".format(
                    ctx.author.display_name, prefix, defender_name
                )
            )
        else:
            await ctx.send(
                "По поручению {0} {1} кусаю @{2}{3}".format(
                    attacker_name, prefix, defender_name, target
                )
            )

    @staticmethod
    def my_get_users(user_name):
        res = requests.get(
            "https://api.twitch.tv/helix/users",
            params={"login": user_name},
            headers={
                "Accept": "application/vnd.twitchtv.v5+json",
                "Authorization": f"Bearer {os.getenv('TWITCH_CHAT_PASSWORD')}",
                "Client-ID": os.getenv("TWITCH_CHAT_CLIENT_ID"),
            },
        )
        res.raise_for_status()
        ress = res.json()["data"][0]
        res.close()
        return ress

    @staticmethod
    async def my_get_stream(user_id) -> dict:
        while True:
            logger.info("Attempting to get stream...")
            res = requests.get(
                "https://api.twitch.tv/helix/streams",
                params={"user_id": user_id},
                headers={
                    "Accept": "application/vnd.twitchtv.v5+json",
                    "Authorization": f"Bearer " f"{os.getenv('TWITCH_CHAT_PASSWORD')}",
                    "Client-ID": os.getenv("TWITCH_CHAT_CLIENT_ID"),
                },
            )

            try:
                res.raise_for_status()
                stream = res.json()["data"][0]
            except IndexError:
                logger.info("Stream not detected yet")
                pass
            except requests.RequestException as e:
                logger.error(f"Request to /helix/streams failed: {str(e)}")
            else:
                logger.info("Got stream")
                res.close()
                return stream

            res.close()
            await asyncio.sleep(60)

    @staticmethod
    def my_get_game(game_id):
        res = requests.get(
            "https://api.twitch.tv/helix/games",
            params={"id": game_id},
            headers={
                "Accept": "application/vnd.twitchtv.v5+json",
                "Authorization": f"Bearer {os.getenv('TWITCH_CHAT_PASSWORD')}",
                "Client-ID": os.getenv("TWITCH_CHAT_CLIENT_ID"),
            },
        )

        ress = res.json()["data"][0]
        res.close()
        return ress

    async def my_run_commercial(self, user_id, length=90):
        await self.my_get_stream(self.streamer_id)
        sess = twitch_api.get_session(
            os.getenv("TWITCH_CLIENT_ID"),
            os.getenv("TWITCH_CLIENT_SECRET"),
            twitch_redirect_url,
        )
        res = sess.post(
            "https://api.twitch.tv/helix/channels/commercial",
            data={"broadcaster_id": user_id, "length": length},
            headers={"Client-ID": os.getenv("TWITCH_CLIENT_ID")},
        )
        try:
            res.raise_for_status()
            res.close()
        except requests.HTTPError:
            logger.error("Failed to run commercial:", res.json())

    @twitch_command_aliased(name="ping", aliases=("пинг",))
    async def cmd_ping(self, ctx: commands.Context):
        if not self.check_sender(ctx, "iarspider"):
            return

        await ctx.send("Yeth, Mathter?")

    @twitch_command_aliased(name="bomb", aliases=("man", "manual", "руководство"))
    async def man(self, ctx: commands.Context):
        await ctx.send("Руководство тут - https://bombmanual.com/ru/web/index.html")

    @twitch_command_aliased(name="help", aliases=("помощь", "справка", "хелп"))
    async def help(self, ctx: commands.Context):
        # asyncio.ensure_future(ctx.send(f"Никто тебе не поможет,
        # {ctx.author.display_name}!"))
        asyncio.ensure_future(
            ctx.send(
                f"@{ctx.author.display_name} Справка по командам ботика: "
                f"https://iarspider.github.io/arachnobot/help"
            )
        )

    @twitch_command_aliased(name="join")
    async def test_join(self, ctx: commands.Context):
        if not self.check_sender(ctx, "iarspider"):
            return

        display_name = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=5)
        )
        status = random.choice(random.choice(("spider", "hammer", "award", "eye")))
        color = "#FFFFFF"
        femme = random.choice((True, False))
        item = {
            "action": "add",
            "value": {
                "name": display_name,
                "status": status,
                "color": color,
                "femme": femme,
            },
        }
        if self.sio_server is not None:
            await self.sio_server.emit(item["action"], item["value"])
        else:
            logger.warning("send_viewer_joined: sio_server is none!")

    @twitch_command_aliased(name="leave")
    async def test_leave(self, ctx: commands.Context):
        if not self.check_sender(ctx, "iarspider"):
            return

        arg = ctx.message.content.split()[1]
        item = {"action": "remove", "value": arg}
        if self.sio_server is not None:
            await self.sio_server.emit(item["action"], item["value"])
        else:
            logger.warning("send_viewer_joined: sio_server is none!")

    def load_pearls(self):
        self.pearls = []
        with open("pearls.txt", "r", encoding="utf-8") as f:
            for line in f:
                self.pearls.append(line.strip())

    def write_pearls(self):
        with open("pearls.txt", "w", encoding="utf-8") as f:
            for pearl in self.pearls:
                print(pearl, file=f)

    @twitch_command_aliased(name="amivip")
    async def amivip(self, ctx: commands.Context):
        logger.info("Badges: " + str(ctx.author.badges))
        if ctx.author.is_vip:
            await ctx.send("Да! 💎")
        else:
            await ctx.send("Нет! 🗿")

    @twitch_command_aliased(name="togglemt")
    async def toggmelt(self, ctx: commands.Context):
        if not self.check_sender(ctx, "iarspider"):
            return

        self.game.mt = not self.game.mt
        self.game.save()

    @twitch_command_aliased(
        name="perl", aliases=("перл", "пёрл", "pearl", "quote", "цитата", "цытата")
    )
    async def pearl(self, ctx: commands.Context):
        try:
            arg = ctx.message.content.split(None, 1)[1]
        except IndexError:
            arg = ""

        if arg.startswith("+"):
            if not ctx.author.name.lower() in rippers:
                await ctx.send("Недостаточно прав для выполнения этой команды")
                return
            pearl = arg[1:].strip()
            self.pearls.append(pearl)
            self.write_pearls()
            await ctx.send(f"ПаукоПёрл №{len(self.pearls)} сохранён")
        elif arg.startswith("?"):
            await ctx.send(f"Всего ПаукоПёрлов: {len(self.pearls)}")
        else:
            if arg:
                try:
                    pearl_id = int(arg)
                    pearl = self.pearls[pearl_id]
                except (IndexError, ValueError) as e:
                    await ctx.send("Ошибка: нет такого пёрла")
                    logger.exception(e)
                    return
            else:
                pearl_id = random.randrange(len(self.pearls))
                pearl = self.pearls[pearl_id]

            await ctx.send(f"ПаукоПёрл №{pearl_id}: {pearl}")

    async def on_dashboard_connected(self, sid):
        if self.sio_server is None:
            return

        ids = set()

        await self.sio_server.emit("reset", "", to=sid)

        tasks = []

        # type viewer: Chatter
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


twitch_bot: Optional[Bot] = None
# discord_bot: Optional[discord.Client] = None
sio_client: Optional[socketio.AsyncClient] = None
# sio_server: Optional[socketio.AsyncServer] = None
# app: Optional[socketio.WSGIApp] = None


@logger.catch
async def main():
    global client, twitch_bot
    setup_logging("bot.log", color=True, debug=False, http_debug=False)

    random.seed()

    # logger.setLevel(logging.DEBUG)
    logging.getLogger("asyncio").setLevel(logging.DEBUG)

    sio_server = socketio.AsyncServer(
        async_mode="asgi",
        # logger=True, engineio_logger=True,
        cors_allowed_origins=["https://fr.iarazumov.com", "http://overlay.home"],
    )
    app = socketio.ASGIApp(sio_server, socketio_path="/ws")
    config = uvicorn.Config(app, host="0.0.0.0", port=8081)
    # noinspection PyUnusedLocal
    server = uvicorn.Server(config)

    # noinspection PyUnresolvedReferences,PyUnusedLocal
    @sio_server.on("connect")
    async def on_ws_connected(sid, _):
        global twitch_bot
        twitch_bot.dashboard.append(sid)
        asyncio.ensure_future(twitch_bot.on_dashboard_connected(sid))
        logger.info(f"Dashboard connected with id {sid}")
        ripcog: "RIPCog" = twitch_bot.get_cog("RIPCog")
        await ripcog.display_rip()
        plushchcog = twitch_bot.get_cog("PluschCog")
        plushchcog.write_plusch()

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
        ripcog: "RIPCog" = twitch_bot.get_cog("RIPCog")
        msg = await ripcog.do_rip(n=1)
        await twitch_bot.send_message(msg)

    # noinspection PyUnresolvedReferences,PyUnusedLocal
    @sio_server.on("unrip")
    async def on_ws_unrip(sid):
        logger.info(f"Received message: unrip")
        ripcog: "RIPCog" = twitch_bot.get_cog("RIPCog")
        msg = await ripcog.do_rip(n=-1)
        await twitch_bot.send_message(msg)

    # noinspection PyUnresolvedReferences,PyUnusedLocal
    @sio_server.on("break")
    async def on_ws_break(sid):
        logger.info(f"Received message: break")
        cog: "OBSCog" = twitch_bot.get_cog("OBSCog")
        cog.do_pause(None, False)
        await twitch_bot.send_message("Начать перепись населения!")

    # noinspection PyUnresolvedReferences,PyUnusedLocal
    @sio_server.on("resume")
    async def on_ws_resume(sid):
        logger.info(f"Received message: resume")
        cog: "OBSCog" = twitch_bot.get_cog("OBSCog")
        msg = await cog.do_resume(None)
        await twitch_bot.send_message(msg)

    # noinspection PyUnresolvedReferences,PyUnusedLocal
    @sio_server.on("*")
    def catch_all(event, sid, data):
        logger.warning(f"Unhandled event {event} (data {data})")
        pass

    # Run bot
    if sio_server is None:
        logger.warning("sio_server is none!")
    twitch_bot = Bot(sio_server_=sio_server)

    if os.getenv("OBSWS_ADDRESS") is not None:
        logger.info("Loading module obscog")
        twitch_bot.load_module("cogs.obscog")

    for extension in (
        "discordcog",
        "pluschcog",
        "ripcog",
        "SLCog",
        "elfcog",
        "duelcog",
    ):  # 'raidcog', 'vmodcog', 'musiccog'
        # noinspection PyUnboundLocalVariable
        logger.info(f"Loading module {extension}")
        twitch_bot.load_module(f"cogs.{extension}")

    twitch_bot.call_cogs("setup")
    pubsub_sess = twitch_api.get_session(
        os.getenv("TWITCH_CLIENT_ID"),
        os.getenv("TWITCH_CLIENT_SECRET"),
        twitch_redirect_url,
    )
    client = Client(
        token=pubsub_sess.token["access_token"].replace("oauth2:", ""),
        initial_channels=["#iarspider"],
        client_secret=os.getenv("TWITCH_CLIENT_SECRET"),
    )

    client.pubsub = pubsub.PubSubPool(client)
    twitch_bot.pubsub_client = client

    # Forward event to bot. DO NOT DELETE THIS!!!
    @client.event()
    async def event_pubsub_channel_points(event: pubsub.PubSubChannelPointsMessage):
        await twitch_bot.event_pubsub_channel_points(event)

    @client.event()
    async def event_token_expired():
        logger.info("Renewing token...")
        pubsub_sess_ = twitch_api.get_session(
            os.getenv("TWITCH_CLIENT_ID"),
            os.getenv("TWITCH_CLIENT_SECRET"),
            twitch_redirect_url,
        )

        return pubsub_sess_.token["access_token"].replace("oauth2:", "")

    # await twitch_bot.start()
    async with asyncio.TaskGroup() as tg:
        task1 = tg.create_task(twitch_bot.start())
        task2 = tg.create_task(server.serve())

    # noinspection PyProtectedMember
    # if not client._closing.is_set():
    #     await client.close()


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


async def do_wizlight_disco():
    states = []
    logger.info("Starting disco...")
    for _ in wiz_config:
        b = wizlight(**_)
        state = await b.updateState()
        if not state.get_state():
            logger.error(f"!!! Lightbulb {_['ip']} is off !!!")
            states.append(None)
            continue

        states.append(
            {
                "speed": state.get_speed(),
                "scene": state.get_scene_id(),
                "brightness": state.get_brightness(),
            }
        )

        await b.turn_on(PilotBuilder(speed=200, scene=4, brightness=255))
        await b.async_close()
        del b

    logger.info("Sleeping...")
    await asyncio.sleep(180)
    logger.info("Restoring...")

    for i, _ in enumerate(wiz_config):
        if states[i] is not None:
            b = wizlight(**_)
            await b.turn_on(PilotBuilder(**states[i]))
            await b.async_close()
            del b

    await asyncio.sleep(1)


def patch_socketio():
    socketio.AsyncManager.emit = emit


if __name__ == "__main__":
    load_dotenv()
    patch_socketio()
    asyncio.run(main())
