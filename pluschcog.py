import asyncio
import codecs
from typing import Optional

from pytils import numeral
from twitchio import Context
from twitchio.ext import commands


@commands.cog()
class PluschCog:
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger

        self.write_plusch()

    def write_plusch(self):
        with codecs.open("plusch.txt", "w", "utf8") as f:
            f.write("Кого-то поплющило {0}...".format(numeral.get_plural(self.plusches, ('раз', 'раза', 'раз'))))

    @commands.command(name='plusch', aliases=['плющ'])
    async def plusch(self, ctx: Context):
        # if not self.is_mod(ctx.author.name) and ctx.author.name != 'iarspider':
        #     asyncio.ensure_future(ctx.send("No effect? I'm gonna need a bigger sword! (c)"))
        #     return

        who = " ".join(ctx.message.content.split()[1:])
        asyncio.ensure_future(ctx.send("Эк {0} поплющило...".format(who)))
        self.plusches += 1
        self.write_plusch()

    @commands.command(name='eplusch', aliases=['экипоплющило'])
    async def eplusch(self, ctx: Context):
        asyncio.ensure_future(ctx.send("Эки кого-то поплющило..."))
        self.plusches += 1
        self.write_plusch()
