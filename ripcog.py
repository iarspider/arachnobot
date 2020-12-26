import asyncio
import codecs
from typing import Optional
import logging

from twitchio import Context
from twitchio.ext import commands


@commands.core.cog()
class RIPCog:
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("arachnobot.rip")

        # Forwarding functions from bot
        self.is_vip = self.bot.is_vip
        self.check_sender = self.bot.check_sender

        self.deaths = {'today': 0, 'total': 0}

        self.rippers = ['iarspider', 'twistr_game', 'luciustenebrysflamos', 'phoenix__tv', 'wmuga', 'johnrico85']
        self.write_rip()

        try:
            with open('rip.txt') as f:
                self.deaths['total'] = int(f.read().strip())
        except (FileNotFoundError, TypeError, ValueError):
            pass

    def write_rip(self):
        with codecs.open('rip_display.txt', 'w', 'utf8') as f:
            f.write(u'☠: {today} (всего: {total})'.format(**self.deaths))

        with open('rip.txt', 'w') as f:
            f.write(str(self.deaths['total']))

    async def do_rip(self, ctx: Context, reason: Optional[str] = None):
        if not (ctx.author.is_mod or self.is_vip(ctx.author) or ctx.author.name.lower() in self.rippers):
            asyncio.ensure_future(ctx.send("Эту кнопку не трожь!"))
            return

        self.deaths['today'] += 1
        self.deaths['total'] += 1

        self.write_rip()
        if reason:
            await ctx.send(reason)

        asyncio.ensure_future(ctx.send("riPepperonis {today}".format(**self.deaths)))

    @commands.command(name='rip', aliases=("смерть",))
    async def rip(self, ctx: Context):
        """
            Счётчик смертей

            %% rip
        """
        await self.do_rip(ctx)

    @commands.command(name='unrip')
    async def unrip(self, ctx: Context):
        """
        Отмена смерти
        """
        if not self.check_sender(ctx, 'iarspider'):
            return

        self.deaths['today'] -= 1
        self.deaths['total'] -= 1

        self.write_rip()

        asyncio.ensure_future(ctx.send("MercyWing1 PinkMercy MercyWing2".format(*self.deaths)))

    @commands.command(name='enrip')
    async def enrip(self, ctx: Context):
        """
        Временно (до перезапуска бота) добавляет пользователя в rip-список
        """
        if not self.check_sender(ctx, 'iarspider'):
            return

        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            asyncio.ensure_future(ctx.send("Неправильный запрос"))
        self.rippers.append(args[0])

        asyncio.ensure_future(ctx.send("{0} TwitchVotes ".format(args[0])))

    # async def mc_rip(self):
    #     try:
    #         with open(r"e:\MultiMC\instances\InSphere Deeper 0.8.3\.minecraft\LP World v3_deathcounter.txt") as f:
    #             self.deaths[0] = int(f.read())
    #             self.deaths[1] = self.deaths[0]
    #             self.write_rip()
    #     except OSError:
    #         return
        
    # @commands.command(name='ripz')
    # async def ripz(self, ctx: Context):
    #     """
    #         Счётчик смертей
    #
    #         %% ripz
    #     """
    #     await self.do_rip(ctx, "#Отзомбячено!")
    #
    # @commands.command(name='riph')
    # async def riph(self, ctx: Context):
    #     """
    #         Счётчик смертей
    #
    #         %% riph
    #     """
    #     await self.do_rip(ctx, "#Захедкраблено")
    #
    # @commands.command(name='ripc')
    # async def ripc(self, ctx: Context):
    #     """
    #         Счётчик смертей
    #
    #         %% ripc
    #     """
    #     await self.do_rip(ctx, "#Укомбайнено")
    #
    # @commands.command(name='ripb')
    # async def ripb(self, ctx: Context):
    #     """
    #         Счётчик смертей
    #
    #         %% ripb
    #     """
    #     await self.do_rip(ctx, "#Барнакнуто")
    #
    # @commands.command(name='ripn', aliases=['nom', 'omnomnom', 'ном', 'ням', 'омномном'])
    # async def nom(self, ctx: Context):
    #     await self.do_rip(ctx, 'Ом-ном-ном!')
