import asyncio
import random

import twitchio
from pywizlight import wizlight, PilotBuilder
from twitchio.ext import commands
from twitchio.ext.commands import Component

from config import wiz_config
from loguru import logger


class LOGGER:
    @staticmethod
    def info(*args, **kwargs):
        pass


class PointCog(Component):
    def __init__(self, bot):
        self.bot = bot

    async def do_wizlight_disco(self):
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

    @commands.Component.listener()
    async def event_custom_redemption_add(
        self, payload: twitchio.ChannelPointsRedemptionAdd
    ) -> None:
        logger.info(
            f"{payload.user!r} has redeemed {payload.reward.title} ({payload.reward.id}) at {payload.timestamp}"
        )

    @commands.reward_command(
        id="a108ed9d-aaad-431a-b78a-c80084ccabf3",
        invoke_when=commands.RewardStatus.all,
    )
    async def nothing(self, ctx: commands.Context, *, user_input: str = "") -> None:
        # "Ничего"
        requestor = ctx.author.display_name or ctx.author.name
        logger.debug(f"Queued redemption: nothing, {requestor}")
        await self.bot.play_sound("my_sound//nothing0.mp3")

        item = {"action": "event", "value": {"type": "nothing", "from": requestor}}
        if self.bot.sio_server is not None:
            self.bot.pubsub_events.append(item)
            await self.bot.sio_server.emit(item["action"], item["value"])

        logger.info("Команда Ничего выполнена")

    @commands.reward_command(
        id="0ec4f099-0640-48e4-8b6e-7e55b7dd6a22",
        invoke_when=commands.RewardStatus.all,
    )
    async def sit(self, ctx: commands.Context, *, user_input: str = "") -> None:
        # "Стримлер! Не горбись!"
        requestor = ctx.author.display_name or ctx.author.name
        logger.debug(f"Queued redemption: sit, {requestor}")
        await self.bot.play_sound("my_sound//StraightenUp.mp3")

        item = {"action": "event", "value": {"type": "sit", "from": requestor}}
        if self.bot.sio_server is not None:
            self.bot.pubsub_events.append(item)
            await self.bot.sio_server.emit(item["action"], item["value"])

        logger.info("Команда Стримлер! Не горбись! выполнена")

    @commands.reward_command(
        id="7862899c-f539-451f-8454-d01a53bf66d1",
        invoke_when=commands.RewardStatus.all,
    )
    async def designer_nothing(
        self, ctx: commands.Context, *, user_input: str = ""
    ) -> None:
        # "Дизайнерское Ничего"
        requestor = ctx.author.display_name or ctx.author.name
        logger.debug(f"Queued redemption: designer nothing, {requestor}")
        await self.bot.play_sound("my_sound//designer_nothing0.mp3")

        item = {"action": "event", "value": {"type": "nihil", "from": requestor}}
        if self.bot.sio_server is not None:
            self.bot.pubsub_events.append(item)
            await self.bot.sio_server.emit(item["action"], item["value"])

        logger.info("Команда Дизайнерское Ничего выполнена")

    @commands.reward_command(
        id="d1f84d27-4ed5-4718-a866-6d2ea30578d0",
        invoke_when=commands.RewardStatus.all,
    )
    async def disperse(self, ctx: commands.Context, *, user_input: str = "") -> None:
        # "Распылить упорин"
        requestor = ctx.author.display_name or ctx.author.name
        logger.debug(f"Queued redemption: fun, {requestor}")

        s = random.choice(
            ["Nice01", "Nice02", "ThatWasFun01", "ThatWasFun02", "ThatWasFun03"]
        )
        await self.bot.play_sound(f"sound//Minion General Speech@ignore@{s}.mp3")
        asyncio.ensure_future(self.do_wizlight_disco())

        item = {"action": "event", "value": {"type": "fun", "from": requestor}}
        if self.bot.sio_server is not None:
            self.bot.pubsub_events.append(item)
            await self.bot.sio_server.emit(item["action"], item["value"])

        logger.info("Команда Распылить упорин выполнена")

    @commands.reward_command(
        id="9d362ab3-93ca-4bff-93c1-8f825564f82d",
        invoke_when=commands.RewardStatus.all,
    )
    async def burn(self, ctx: commands.Context, *, user_input: str = "") -> None:
        # "Гори!"
        snd = random.choice(["Goblin_Burn_1", "Minion_BurnBurn", "Minion_FireNoHurt"])
        await self.bot.play_sound(f"sound//Minion General Speech@ignore@{snd}.mp3")
        logger.info("Команда Гори! выполнена")

    @commands.reward_command(
        id="f0981fcc-ab43-4818-b748-c969152d63fb",
        invoke_when=commands.RewardStatus.all,
    )
    async def hug_chat(self, ctx: commands.Context, *, user_input: str = "") -> None:
        # "Обнять чатик"
        requestor = ctx.author.display_name or ctx.author.name
        logger.debug(f"Queued redemption: hugs, {requestor}")
        await ctx.send(f"{requestor} обнял чатик!")

        item = {"action": "event", "value": {"type": "hugs", "from": requestor}}
        if self.bot.sio_server is not None:
            self.bot.pubsub_events.append(item)
            await self.bot.sio_server.emit(item["action"], item["value"])

        logger.info("Команда Обнять чатик выполнена")

    @commands.reward_command(
        id="729c17ee-3850-4987-b693-d22892933584",
        invoke_when=commands.RewardStatus.all,
    )
    async def hug_streamer(
        self, ctx: commands.Context, *, user_input: str = ""
    ) -> None:
        # "Обнять стримера"
        requestor = ctx.author.display_name or ctx.author.name
        logger.debug(f"Queued redemption: hugs, {requestor}")
        await ctx.send(f"{requestor} обнял стримера! Спасибо, {requestor}!")

        item = {"action": "event", "value": {"type": "hugs", "from": requestor}}
        if self.bot.sio_server is not None:
            self.bot.pubsub_events.append(item)
            await self.bot.sio_server.emit(item["action"], item["value"])

        logger.info("Команда Обнять стримера выполнена")

    @commands.reward_command(
        id="f45ebad5-af4d-4810-a857-ee10ac50589a",
        invoke_when=commands.RewardStatus.all,
    )
    async def moar(self, ctx: commands.Context, *, user_input: str = "") -> None:
        # "Маловато будет"
        await self.bot.play_sound("my_sound//МАЛОВАТО БУДЕТ.mp3")
        logger.info("Команда Маловато будет выполнена")

    @commands.reward_command(
        id="7191eaaf-ca94-4c71-89ac-e08ae28a1c94",
        invoke_when=commands.RewardStatus.all,
    )
    async def not_greedy(self, ctx: commands.Context, *, user_input: str = "") -> None:
        # "Я не жадный"
        await self.bot.play_sound("my_sound//Я не жадный.mp3")
        logger.info("Команда Я не жадный выполнена")

    @commands.reward_command(
        id="ecf2daaa-06a9-4c42-8d4d-1b4c1ae75659",
        invoke_when=commands.RewardStatus.all,
    )
    async def exclusive_nothing(
        self, ctx: commands.Context, *, user_input: str = ""
    ) -> None:
        # "Эксклюзивное Ничего, pro edition"
        requestor = ctx.author.display_name or ctx.author.name
        logger.debug(f"Queued redemption: pro nothing, {requestor}")
        await self.bot.play_sound("my_sound//exclusive_nothing_pro.mp3")

        item = {"action": "event", "value": {"type": "nihil", "from": requestor}}
        if self.bot.sio_server is not None:
            self.bot.pubsub_events.append(item)
            await self.bot.sio_server.emit(item["action"], item["value"])

        logger.info("Команда Эксклюзивное Ничего, pro edition выполнена")

    @commands.reward_command(
        id="bf796646-7100-402f-a718-48086c290a2b",
        invoke_when=commands.RewardStatus.all,
    )
    async def ruin(self, ctx: commands.Context, *, user_input: str = "") -> None:
        # "Ты всё испортил!"
        await self.bot.play_sound("my_sound//fail.mp3")
        logger.info("Команда Ты всё испортил! выполнена")

    @commands.reward_command(
        id="4b0f043a-109b-44da-b4e3-a142c7dd139d",
        invoke_when=commands.RewardStatus.all,
    )
    async def greed(self, ctx: commands.Context, *, user_input: str = "") -> None:
        # "Жадность"
        await self.bot.play_sound("my_sound//Жадность это плохо.mp3")
        logger.info("Команда Жадность выполнена")


# This is our entry point for the module.
async def setup(bot: commands.Bot) -> None:
    await bot.add_component(PointCog(bot))
