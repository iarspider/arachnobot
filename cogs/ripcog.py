import asyncio
import codecs
import sys

from loguru import logger
from twitchio.ext import commands

from cogs.mycog import MyCog

sys.path.append("..")
from config import rippers


class RIPCog(MyCog):
    def __init__(self, bot):
        self.bot = bot

        # Forwarding functions from bot
        self.check_sender = self.bot.check_sender

        self.deaths = {"today": 0, "total": 0}

        self.obscog = None

    def setup(self):
        self.obscog = self.bot.get_cog("OBSCog")

    def update(self):
        self.deaths = {"today": 0, "total": self.bot.game.rip_total}
        enabled = self.bot.game.rip_enabled
        asyncio.ensure_future(self.obscog.enable_rip(enabled))
        self.display_rip()

    def display_rip(self):
        with codecs.open("rip_display.txt", "w", "utf8") as f:
            f.write("☠: {today} (всего: {total})".format(**self.deaths))

    def write_rip(self):
        self.display_rip()
        self.game.rip_total = self.deaths["total"]
        self.game.save()

    async def do_rip(self, n=1):
        self.deaths["today"] += n
        self.deaths["total"] += n

        self.write_rip()

        return (
            "riPepperonis {today}".format(**self.deaths)
            if n > 0
            else "MercyWing1 PinkMercy MercyWing2"
        )

    @commands.command(name="rip", aliases=("смерть", "кшз"))
    async def rip(self, ctx: commands.Context):
        """
        Счётчик смертей

        %% rip
        """
        args = ctx.message.content.split()[1:]
        if args and (args[0] == "who" or args[0] == "?"):
            ans = "Счетоводы: " + ", ".join(rippers)
            asyncio.ensure_future(ctx.send(ans))
            return

        if not (
                ctx.author.is_mod or ctx.author.is_vip or ctx.author.name.lower() in
                rippers
        ):
            asyncio.ensure_future(ctx.send("Эту кнопку не трожь!"))
            return

        if args and args[0].startswith("+"):
            try:
                n_rip = int(args[0])
            except ValueError as e:
                n_rip = 1
        else:
            n_rip = 1

        n_rip = max(1, n_rip)
        ans = await self.do_rip(n=n_rip)
        asyncio.ensure_future(ctx.send(ans))

    @commands.command(name="unrip")
    async def unrip(self, ctx: commands.Context):
        """
        Отмена смерти
        """
        if not self.check_sender(ctx, "iarspider"):
            return

        msg = await self.do_rip(n=-1)

        asyncio.ensure_future(ctx.send(msg))

    @commands.command(name="enrip")
    async def enrip(self, ctx: commands.Context):
        """
        Временно (до перезапуска бота) добавляет пользователя в rip-список
        """
        if not self.check_sender(ctx, "iarspider"):
            return

        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            asyncio.ensure_future(ctx.send("Неправильный запрос"))
        rippers.append(args[0].lower())

        asyncio.ensure_future(ctx.send("{0} TwitchVotes ".format(args[0])))

    @commands.command(name="lrip")
    async def lrip(self, ctx: commands.Context):
        """
        Перезагружает счётчик смертей (в случае смены игры)
        """
        if not self.check_sender(ctx, "iarspider"):
            logger.info("check_sender failed")
            return

        self.get_game_v5()
        await ctx.send("Счётчик смертей обновлён")

    @commands.command(name="setrip")
    async def setrip(self, ctx: commands.Context):
        """
        Устанавливает значение счётчика смертей за сегодня
        """
        if not self.check_sender(ctx, "iarspider"):
            logger.info("check_sender failed")
            return

        try:
            arg = int(ctx.message.content.split()[1])
        except (IndexError, ValueError):
            await ctx.send("Usage: !setrip <N>")
            return
        else:
            self.deaths["today"] = arg
            if self.deaths["total"] == 0:
                self.deaths["total"] = arg
            self.display_rip()

    @commands.command(name="yesrip")
    async def yesrip(self, ctx: commands.Context):
        """
        Включает отображение смертей
        """
        if not self.check_sender(ctx, "iarspider"):
            logger.info("check_sender failed")
            return

        self.bot.game.rip_enabled = True
        self.bot.game.save()

        await self.obscog.enable_rip(True)
        await ctx.send("Счётчик смертей активирован")

    @commands.command(name="norip")
    async def norip(self, ctx: commands.Context):
        """
        Включает отображение смертей
        """
        if not self.check_sender(ctx, "iarspider"):
            logger.info("check_sender failed")
            return

        self.bot.game.rip_enabled = False
        self.bot.game.save()

        await self.obscog.enable_rip(False)
        await ctx.send("Счётчик смертей отключён")

    # @commands.command(name='ripz')
    # async def ripz(self, ctx: commands.Context):
    #     """
    #         Счётчик смертей
    #
    #         %% ripz
    #     """
    #     await self.do_rip(ctx, "#Отзомбячено!")
    #
    # @commands.command(name='riph')
    # async def riph(self, ctx: commands.Context):
    #     """
    #         Счётчик смертей
    #
    #         %% riph
    #     """
    #     await self.do_rip(ctx, "#Захедкраблено")
    #
    # @commands.command(name='ripc')
    # async def ripc(self, ctx: commands.Context):
    #     """
    #         Счётчик смертей
    #
    #         %% ripc
    #     """
    #     await self.do_rip(ctx, "#Укомбайнено")
    #
    # @commands.command(name='ripb')
    # async def ripb(self, ctx: commands.Context):
    #     """
    #         Счётчик смертей
    #
    #         %% ripb
    #     """
    #     await self.do_rip(ctx, "#Барнакнуто")
    #
    # @commands.command(name='ripn', aliases=['nom', 'omnomnom', 'ном', 'ням',
    # 'омномном'])
    # async def nom(self, ctx: commands.Context):
    #     await self.do_rip(ctx, 'Ом-ном-ном!')


def prepare(bot: commands.Bot):
    bot.add_cog(RIPCog(bot))
