import asyncio
import os
import time
from tempfile import NamedTemporaryFile

import httpx
import socketio
from bs4 import BeautifulSoup
from loguru import logger
from twitchio.ext import commands
from twitchio.ext.commands import is_broadcaster, Component, cooldown
from fake_useragent import UserAgent

import streamlabs_api as api
from config import rippers, streamlabs_redirect_uri
from twitch_commands import twitch_command_aliased, check_sender


# noinspection PyMethodMayBeStatic
class SLClient(socketio.AsyncClient):
    def __init__(self, **kwargs):
        self.bot = kwargs.pop("bot")
        super().__init__(**kwargs)
        self.on("connect", self.sl_client_connected)
        self.on("disconnect", self.sl_client_disconnected)
        self.on("event", self.sl_client_event)

    async def sl_client_connected(self):
        logger.info("SL client connected")

    async def sl_client_disconnected(self):
        logger.warning("SL client disconnected")

    async def sl_client_event(self, data):
        pick_keys = []
        logger.info(f'SL event: {data["type"]}')
        if data["type"] == "donation":
            pick_keys.extend(("from", "message", "formatted_amount"))
        elif data["type"] == "follow":
            pick_keys.extend(("name",))
        elif data["type"] == "subscription":
            pick_keys.extend(("name", "months", "message", "sub_plan", "sub_type"))
            if data["message"][0]["sub_type"] == "subgift":
                pick_keys.extend(("gifter_display_name",))
        elif data["type"] == "resub":
            pick_keys.extend(("name", "months", "streak_months", "message", "sub_plan"))
        elif data["type"] == "host":
            pick_keys.extend(("name", "viewers"))
        elif data["type"] == "bits":
            pick_keys.extend(("name", "amount", "message"))
        elif data["type"] == "raid":
            pick_keys.extend(("name", "raiders"))
        elif data["type"] in (
            "alertPlaying",
            "streamlabels",
            "streamlabels.underlying",
            "subscription-playing",
        ):
            return
        else:
            logger.info(f'SL event: {data["type"]}')
            logger.warning(f"Unknown SL event type: {data}")
            return

        def copy_keys(from_, to_, keys_):
            for k_ in keys_:
                if k_ in from_:
                    to_[k_] = from_[k_]
                else:
                    logger.warning(f'Event {data["type"]} missing key {k_}')
                    to_[k_] = "UNKNOWN"

        message = {"action": "event", "value": {"type": data["type"]}}
        if isinstance(data["message"], list):
            for msg in data["message"]:
                copy_keys(msg, message["value"], pick_keys)
        else:
            copy_keys(data["message"], message["value"], pick_keys)

        await self.bot.sio_server.emit(message["action"], message["value"])


post_price = {"regular": 50, "vip": 25, "mod": 25}


class SLCog(Component):
    def __init__(self, bot):
        self.bot = bot
        self.sl_client: SLClient = SLClient(logger=logger, bot=bot)
        self.streamlabs_oauth = api.get_streamlabs_session(
            os.getenv("STREAMLABS_CLIENT_ID"),
            os.getenv("STREAMLABS_CLIENT_SECRET"),
            streamlabs_redirect_uri,
        )

        token = api.get_socket_token(self.streamlabs_oauth)
        asyncio.ensure_future(
            self.sl_client.connect(f"https://sockets.streamlabs.com?token={token}")
        )

        self.session = httpx.Client(
            headers={"User-Agent": UserAgent.firefox}, follow_redirects=True
        )
        try:
            res = self.session.get("https://voxworker.com/ru")
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "lxml")

            textId = soup.select("input[name=textId]")
            sessionId = soup.select("input[name=sessionId]")

            logger.debug("Prepare session for VoxWorker")

            self.voxdata = dict(
                textId=textId[0]["value"],
                sessionId=sessionId[0]["value"],
                voice="rh-anna",
                speed="1.0",
                pitch="1.0",
                text="Вы можете менять ударение знаком плюс. Например: хлоп+ок в "
                "ладоши или белый "
                "хл+опок.",
            )
            logger.debug("Session ready")
        except httpx.HTTPError as e:
            logger.opt(exception=e).exception("Failed to initialize voxworker session")
            self.voxdata = None
        except (IndexError, KeyError) as e:
            logger.opt(exception=e).exception("Failed to parse voxworker page")
            self.voxdata = None

    # noinspection PyMethodParameters
    async def bypass_streamer(ctx: commands.Context):
        if ctx.broadcaster:
            return None

        return commands.BucketType.chatter(ctx)

    async def check_and_sub_points(
        self, ctx: commands.Context, price: dict[str, int] | int
    ):
        points = api.get_points(self.streamlabs_oauth, ctx.author.name)
        if ctx.broadcaster:
            required = 0
        else:
            if isinstance(price, dict):
                if ctx.author.moderator:
                    required = price["mod"]
                elif ctx.author.vip:
                    required = price["vip"]
                else:
                    required = price["regular"]
            else:
                required = price

        if points < required:
            await ctx.send(f"Недостаточно багов: баланс {points}, цена {required}")
            return False

        api.sub_points(self.streamlabs_oauth, ctx.author.name, required)
        return True

    async def say(self, text):
        if not self.voxdata:
            logger.warning("VoxWorker not setup")
            return False
        self.voxdata["text"] = text
        res = self.session.post(
            "https://voxworker.com/ru/ajax/convert", data=self.voxdata
        )
        if not res.is_success:
            logger.error(f"Initial request to VoxWorker failed: {res.status_code}")
        resj = res.json()
        logger.debug("Sent request to VoxWorker")

        if resj["status"] == "notify":
            logger.error(f"Got status 'notify': {resj['error']}, {resj['errorText']}")
            return False

        statusAttemptCount = 0
        while statusAttemptCount < 60 and resj["status"] == "queue":
            logger.debug(f"VoxWorker: request queued, count: {statusAttemptCount}")
            res = self.session.get(
                f'https://voxworker.com/ru/ajax/status?id={resj["taskId"]}'
            )
            if not res.is_success:
                logger.error(f"Status request to VoxWorker failed: {res.status_code}")
                return False
            resj = res.json()
            statusAttemptCount += 1
            time.sleep(1)

        if statusAttemptCount == 60:
            logger.error("VoxWorker: Conversion error")
            return False

        if resj["status"] != "ok":
            logger.error(
                f"VoxWorker bad status '{resj['status']}': {resj['error']}, "
                f"{resj['errorText']}"
            )
            return False
        else:
            logger.debug("Downloading file from VoxWorker")
            self.voxdata["textId"] = resj.get("textId", "")
            res = self.session.get(resj["downloadUrl"])
            if not res.is_success:
                logger.error(f"Failed to download URL: {res.status_code}")
            with NamedTemporaryFile(delete=False, suffix=".mp3") as tempfile:
                tempfile.write(res.content)

            await self.bot.play_sound("my_sound//ding-sound-effect_1.mp3")
            await self.bot.play_sound(tempfile.name, True)
            return True

    @twitch_command_aliased(name="bugs", aliases=("баги",))
    @cooldown(rate=1, per=60, key=bypass_streamer)
    async def bugs(self, ctx: commands.Context):
        """
        Показывает текущее число "багов" (очков лояльности)

        %%bugs
        """
        user = ctx.author.name
        # print("Requesting points for", user)
        try:
            res = api.get_points(self.streamlabs_oauth, user)
            # print(res)
            # res = res['points']
        except httpx.HTTPError:
            res = 0

        await ctx.send(f"@{user} Набрано багов: {res}")

    @twitch_command_aliased(
        name="post",
        aliases=("почта", "голос"),
    )
    @cooldown(rate=1, per=60, key=bypass_streamer)
    async def post(self, ctx: commands.Context):

        try:
            post_message = ctx.message.text.split(None, 1)[1]
        except IndexError:
            return

        if not await self.check_and_sub_points(ctx, post_price):
            return

        if self.bot.sio_server:
            logger.info("Send tts event to overlay")
            await self.bot.play_sound("my_sound//ding-sound-effect_1.mp3")
            await self.bot.sio_server.emit("tts", post_message)
            logger.info("TTS sent to overlay")
        else:
            if await self.say(post_message):
                pass
            else:
                await self.bot.play_sound("my_sound//pochta.mp3")

    @check_sender(("iarspider",))
    @twitch_command_aliased(name="postt", aliases=("апочта",))
    async def postt(self, ctx: commands.Context):
        try:
            post_message = ctx.message.text.split(None, 1)[1]
        except IndexError:
            return

        if not await self.check_and_sub_points(ctx, post_price):
            return

        if await self.say(post_message):
            pass
        else:
            await self.bot.play_sound("my_sound//pochta.mp3")

    @twitch_command_aliased(name="sos", aliases=("alarm",))
    async def sos(self, ctx: commands.Context):
        if not (ctx.author.vip or ctx.author.broadcaster or ctx.author.name in rippers):
            asyncio.ensure_future(
                ctx.send("Эта кнопочка - не для тебя. Руки убрал, ЖИВО!")
            )
            return

        await self.bot.play_sound("my_sound//matmatmat.mp3")

    # noinspection PyUnusedLocal
    @is_broadcaster()
    @twitch_command_aliased(name="spin")
    async def spin(self, ctx: commands.Context):
        # points = api.get_points(self.streamlabs_oauth, ctx.author.name)
        # httpclient_logging_patch()
        httpx.post(
            "https://streamlabs.com/api/v1.0/wheel/spin",
            data={"access_token": self.streamlabs_oauth.access_token},
        )
        # httpclient_logging_patch(logging.INFO)

    @is_broadcaster()
    @twitch_command_aliased(name="addsp")
    async def addsp(self, ctx: commands.Context):
        try:
            user, points = ctx.message.text.split(None, 2)[1:]
        except IndexError:
            return

        api.add_points(self.streamlabs_oauth, user, int(points))
        await ctx.send(f"Запас багов пользователя {user} пополнен на {points} единиц")

    @twitch_command_aliased(name="жадный")
    @cooldown(rate=1, per=60, key=bypass_streamer)
    async def greedy(self, ctx: commands.Context):
        if not await self.check_and_sub_points(ctx, 1000):
            return
        await self.bot.play_sound("my_sound//Я не жадный.mp3")

    @twitch_command_aliased(name="маловато")
    @cooldown(rate=1, per=60, key=bypass_streamer)
    async def moar(self, ctx: commands.Context):
        if not await self.check_and_sub_points(ctx, 500):
            return
        await self.bot.play_sound("my_sound//МАЛОВАТО БУДЕТ.mp3")

    @twitch_command_aliased(name="жадность")
    @cooldown(rate=1, per=60, key=bypass_streamer)
    async def greed(self, ctx: commands.Context):
        if not await self.check_and_sub_points(ctx, 500):
            return
        await self.bot.play_sound("my_sound//Жадность это плохо.mp3")

    @twitch_command_aliased(name="лужа")
    @cooldown(rate=1, per=60, key=bypass_streamer)
    async def puddle(self, ctx: commands.Context):
        if not await self.check_and_sub_points(ctx, 500):
            return
        await self.bot.play_sound("my_sound//Лужа.mp3")


async def setup(bot: commands.Bot):
    await bot.add_component(SLCog(bot))
