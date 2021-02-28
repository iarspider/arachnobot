import asyncio
import codecs

from pytils import numeral
from twitchio import Context
from twitchio.ext import commands
import logging


@commands.cog()
class PluschCog:
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("arachnobot.plu")
        self.plusches = 0

        self.write_plusch()

    def write_plusch(self):
        with codecs.open("plusch.txt", "w", "utf8") as f:
            if self.plusches == 0:
                f.write("Пока что никого не плющило")
            else:
                f.write("Кого-то поплющило {0}...".format(numeral.get_plural(self.plusches, ('раз', 'раза', 'раз'))))

    @commands.command(name='plusch', aliases=['плющ', 'вштырь'])
    async def plusch(self, ctx: Context):
        who = " ".join(ctx.message.content.split()[1:])
        asyncio.ensure_future(ctx.send("Эк {0} поплющило...".format(who)))
        self.plusches += 1
        self.write_plusch()

    @commands.command(name='eplusch', aliases=['экипоплющило', 'экивштырило'])
    async def eplusch(self, ctx: Context):
        asyncio.ensure_future(ctx.send("Эки кого-то поплющило..."))
        self.plusches += 1
        self.write_plusch()
