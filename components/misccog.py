import asyncio
import datetime
import os
import random
import string
from collections import deque

import twitchio
from loguru import logger
from pytils import numeral
from twitchio import Stream
from twitchio.ext import commands
from twitchio.ext.commands import is_broadcaster

import config
from config import twitch_extra_bite, twitch_no_bite, rippers
from twitch_commands import twitch_command_aliased, check_sender

import telegram


class MiscCog(commands.Component):
    def __init__(self, bot):
        self.bot = bot
        self.__component_name__ = "MiscCog"

    @property
    def last_messages(self):
        return self.bot.last_messages

    @property
    def game(self):
        return self.bot.game

    # We use a listener in our Component to display the messages received.
    @commands.Component.listener()
    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        # print(f"[{payload.broadcaster.name}] - {payload.chatter.name}: {payload.text}")
        if payload.source_broadcaster is not None:
            # Filter out messages in shared chat
            return

        if payload.chatter is None:
            d = datetime.datetime.now().timestamp()
            fn = f"msg_{d}.txt"
            with open(fn, "w") as f:
                f.write(payload.__repr__())
            logger.warning(f"event_message with no author! See {fn} for details")
            return

        if payload.chatter.name.lower() not in self.bot.viewers:
            await self.bot.send_viewer_joined(payload.chatter)
            logger.debug(
                f"JOIN sent for {payload.chatter.name} ({payload.chatter.display_name})! "
            )

        self.bot.add_user(payload.chatter)

        if payload.chatter.name not in self.bot.last_messages:
            self.bot.last_messages[payload.chatter.name] = deque(maxlen=10)

        if payload.chatter.name.lower() not in self.bot.bots:
            if not payload.text.startswith("!"):
                self.bot.last_messages[payload.chatter.name].append(payload.fragments)
                logger.debug(
                    f"Updated last messages for {payload.chatter.name}, "
                    + f"I remember last "
                    f"{len(self.last_messages[payload.chatter.name])}"
                )

    @is_broadcaster()
    @twitch_command_aliased(
        name="pingg",
        aliases=[
            "пингг",
        ],
    )
    async def cmd_ping(self, ctx: commands.Context):
        await ctx.send("Yeth, Mathter?")

    # noinspection PyUnusedLocal
    @commands.Component.listener()
    async def event_stream_online(self, payload: twitchio.StreamOnline) -> None:
        # Event dispatched when a user goes live from the subscription we made above...

        # Keep in mind we are assuming this is for ourselves
        # others may not want your bot randomly sending messages...
        await payload.broadcaster.send_message(
            sender=self.bot.bot_id,
            message=f"Hi... {payload.broadcaster}! You are live!",
        )

        ann_text = await self.bot.get_announce_text()

        logger.info("Getting Discord cog...")
        discord_cog = self.bot.get_component("DiscordCog")
        if discord_cog:
            logger.info("Got it, requesting announce...")
            # noinspection PyUnresolvedReferences
            asyncio.ensure_future(discord_cog.announce(ann_text))
        else:
            logger.warning("Discord cog not found")

        # ann_text = ann_text.replace(
        #     "<https://twitch.tv/iarspider>", "https://twitch.tv/iarspider"
        # )
        bot = telegram.Bot(os.getenv("TELEGRAM_TOKEN"))
        await bot.send_message(config.telegram_channel, text=ann_text)

    @twitch_command_aliased(name="roll", aliases=("dice", "кинь", "r"))
    async def roll(self, ctx: commands.Context):
        dices = []

        args = ctx.message.text.split()[1:]
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
        args = ctx.message.text.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !bite <кого>")
            return
        defender = args[0].strip("@")
        last_bite = self.bot.db.get(attacker, 31525200.0)
        now = datetime.datetime.now()

        last_bite = datetime.datetime.fromtimestamp(last_bite)
        if (now - last_bite).seconds < 15 and attacker != "iarspider":
            await ctx.send(
                "Не кусай так часто, @{0}! Дай моим челюстям отдохнуть!".format(
                    attacker
                )
            )
            return

        if defender.lower() in self.bot.bots:
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

        if defender not in self.bot.viewers and attacker != "iarspider":
            await ctx.send(
                "Кто такой или такая @" + defender + "? Я не буду кусать кого попало!"
            )
            return

        try:
            defender_name = self.bot.viewers[defender].display_name
        except KeyError:
            defender_name = defender

        self.bot.db[attacker] = now.timestamp()

        prefix = random.choice(("нежно ", "ласково "))
        target = what or ""

        if defender.lower() in twitch_no_bite:
            if defender.lower() == "babytigeronthesunflower":
                old_defender = "Тигру"
            else:
                old_defender = defender

            defender_name = self.bot.viewers[attacker].display_name

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

    @twitch_command_aliased(name="bomb", aliases=("man", "manual", "руководство"))
    async def man(self, ctx: commands.Context):
        await ctx.send(
            "Руководство по разминированию тут - https://bombmanual.com/ru/web/index.html"
        )

    @twitch_command_aliased(name="help", aliases=("помощь", "справка", "хелп"))
    async def help(self, ctx: commands.Context):
        # asyncio.ensure_future(ctx.send(f"Никто тебе не поможет,
        # {ctx.author.display_name}!"))
        asyncio.ensure_future(
            ctx.reply(
                f"Справка по командам ботика: "
                f"https://iarspider.github.io/arachnobot/help"
            )
        )

    @is_broadcaster()
    @twitch_command_aliased(name="join")
    async def test_join(self, ctx: commands.Context):

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
        if self.bot.sio_server is not None:
            await self.bot.sio_server.emit(item["action"], item["value"])
        else:
            logger.warning("send_viewer_joined: sio_server is none!")

    @is_broadcaster()
    @twitch_command_aliased(name="leave")
    async def test_leave(self, ctx: commands.Context):
        arg = ctx.message.text.split()[1]
        item = {"action": "remove", "value": arg}
        if self.bot.sio_server is not None:
            await self.bot.sio_server.emit(item["action"], item["value"])
        else:
            logger.warning("send_viewer_joined: sio_server is none!")

    @twitch_command_aliased(name="amivip")
    async def amivip(self, ctx: commands.Context):
        logger.info("Badges: " + str(ctx.author.badges))
        if ctx.author.vip:
            await ctx.reply("Да! 💎")
        else:
            await ctx.reply("Нет! 🗿")

    @is_broadcaster()
    @twitch_command_aliased(name="togglemt")
    async def toggmelt(self, ctx: commands.Context):
        self.bot.game.mt = not self.bot.game.mt
        self.bot.game.save()

    @twitch_command_aliased(
        name="perl", aliases=("перл", "пёрл", "pearl", "quote", "цитата", "цытата")
    )
    async def pearl(self, ctx: commands.Context):
        try:
            arg = ctx.message.text.split(None, 1)[1]
        except IndexError:
            arg = ""

        if arg.startswith("+"):
            if not ctx.author.name.lower() in rippers:
                await ctx.send("Недостаточно прав для выполнения этой команды")
                return
            pearl = arg[1:].strip()
            self.bot.pearls.append(pearl)
            self.bot.write_pearls()
            await ctx.send(f"ПаукоПёрл №{len(self.bot.pearls)} сохранён")
        elif arg.startswith("?"):
            await ctx.send(f"Всего ПаукоПёрлов: {len(self.bot.pearls)}")
        else:
            if arg:
                try:
                    pearl_id = int(arg)
                    pearl = self.bot.pearls[pearl_id]
                except (IndexError, ValueError) as e:
                    await ctx.send("Ошибка: нет такого пёрла")
                    logger.exception(e)
                    return
            else:
                pearl_id = random.randrange(len(self.bot.pearls))
                pearl = self.bot.pearls[pearl_id]

            await ctx.send(f"ПаукоПёрл №{pearl_id}: {pearl}")

    @is_broadcaster()
    @twitch_command_aliased(name="savetags")
    async def savetags(self, ctx: commands.Context):
        owner = ctx.broadcaster
        channel_info = await self.bot.fetch_channels([owner.id])
        if not self.game:
            await self.bot.get_game_v5()

        self.game.tags = ";".join(channel_info[0].tags)
        self.game.save()


# This is our entry point for the module.
async def setup(bot: commands.Bot) -> None:
    await bot.add_component(MiscCog(bot))
