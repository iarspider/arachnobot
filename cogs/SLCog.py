import sys

from twitch_commands import twitch_command_aliased

# sys.path.append("..")

import asyncio
import datetime
import logging
import os
import time
from tempfile import NamedTemporaryFile
from loguru import logger

import requests
import socketio.asyncio_client
from bs4 import BeautifulSoup
from requests.structures import CaseInsensitiveDict
from twitchio.ext import commands

import streamlabs_api as api
from cogs.mycog import MyCog

from config import rippers, streamlabs_redirect_uri


class SLClient(socketio.asyncio_client.AsyncClient):
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


class SLCog(MyCog):
    def __init__(self, bot):
        self.bot = bot
        logger = logging.getLogger("arachnobot.sl")
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
        self.last_post = CaseInsensitiveDict()
        self.post_timeout = 1 * 60
        self.post_price = {"regular": 50, "vip": 25, "mod": 25}

        self.session = requests.Session()
        try:
            res = self.session.get("https://voxworker.com/ru")
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")

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
        except requests.HTTPError as e:
            logger.exception(msg="Failed to initialize voxworker session", exc_info=e)
            self.voxdata = None
        except (IndexError, KeyError) as e:
            logger.exception("Failed to parse voxworker page")
            self.voxdata = None

    def __getattr__(self, item):
        if item != "__bases__":
            logger.warning(
                f"[OBS] Failed to get attribute {item}, redirecting to self.bot!"
            )
        return self.bot.__getattribute__(item)

    async def say(self, text):
        if not self.voxdata:
            logger.warning("VoxWorker not setup")
            return False
        self.voxdata["text"] = text
        res = self.session.post(
            "https://voxworker.com/ru/ajax/convert", data=self.voxdata
        )
        if not res.ok:
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
            if not res.ok:
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
            if not res.ok:
                logger.error(f"Failed to download URL: {res.status_code}")
            with NamedTemporaryFile(delete=False, suffix=".mp3") as tempfile:
                fname = tempfile.name
                tempfile.write(res.content)

            await self.bot.play_sound("my_sound\\ding-sound-effect_1.mp3")
            await self.bot.play_sound(tempfile.name, True)
            return True

    @twitch_command_aliased(name="bugs", aliases=("баги",))
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
        except requests.HTTPError:
            res = 0

        await ctx.send(f"@{user} Набрано багов: {res}")

    @twitch_command_aliased(name="post", aliases=("почта",))
    async def post(self, ctx: commands.Context):
        try:
            post_message = ctx.message.content.split(None, 1)[1]
        except IndexError:
            return

        # await self.ctx.send("Почта на ремонте")
        # await self.bot.play_sound("pochta.mp3")
        # return
        #
        now = datetime.datetime.now()
        if ctx.author.name != "iarspider":
            lastpost = self.last_post.get(ctx.author.name, None)
            if lastpost is not None:
                delta = now - lastpost
                if delta.seconds < self.post_timeout:
                    asyncio.ensure_future(
                        ctx.send("Не надо так часто отправлять почту!")
                    )
                    return

            if ctx.author.is_mod:
                price = self.post_price["mod"]
            elif ctx.author.is_vip:
                price = self.post_price["vip"]
            else:
                price = self.post_price["regular"]

            points = api.get_points(self.streamlabs_oauth, ctx.author.name)

            if points < price:
                asyncio.ensure_future(
                    ctx.send(
                        f"У вас недостаточно багов для отправки почты - вам нужно "
                        f"минимум {price}. Проверить баги: !баги"
                    )
                )

                return
        else:
            price = 0

        if await self.say(post_message):
            if price > 0:
                res = api.sub_points(self.streamlabs_oauth, ctx.author.name, price)
                logger.debug(res)
            self.last_post[ctx.author.name] = now
        else:
            await self.bot.play_sound("my_sound\\pochta.mp3")

    @twitch_command_aliased(name="sos", aliases=("alarm",))
    async def sos(self, ctx: commands.Context):
        if not (
            ctx.author.is_mod
            or ctx.author.name.lower() == "iarspider"
            or ctx.author.name in rippers
        ):
            asyncio.ensure_future(
                ctx.send("Эта кнопочка - не для тебя. Руки убрал, ЖИВО!")
            )
            return

        await self.bot.play_sound("my_sound\\matmatmat.mp3")

    @twitch_command_aliased(name="spin")
    async def spin(self, ctx: commands.Context):
        if ctx.author.name.lower() != "iarspider":
            return

        # points = api.get_points(self.streamlabs_oauth, ctx.author.name)
        # httpclient_logging_patch()
        requests.post(
            "https://streamlabs.com/api/v1.0/wheel/spin",
            data={"access_token": self.streamlabs_oauth.access_token},
        )
        # httpclient_logging_patch(logging.INFO)


def prepare(bot: commands.Bot):
    bot.add_cog(SLCog(bot))
