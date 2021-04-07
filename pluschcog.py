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

    def do_plusch(self, ctx: Context, who="", shtyr=False, slf=False):
        if not who.strip():
            who = 'кого-то'

        if not shtyr:
            asyncio.ensure_future(ctx.send("Эк {0} {1}поплющило...".format(who, 'само' if slf else '')))
        else:
            asyncio.ensure_future(ctx.send("Эк {0} вштырно {1}поплющило...".format(who, 'само' if slf else '')))
        
        self.plusches += 1
        self.write_plusch()
        

    @commands.command(name='plusch', aliases=['плющ', 'вштырь'])
    async def plusch(self, ctx: Context):
        command_ = ctx.message.content.split()[0]
        who = ctx.message.content.split(None, 1)[1]
        self.do_plusch(ctx, who, 'вштырь' in command_)


    @commands.command(name='eplusch', aliases=['экипоплющило', 'экивштырило'])
    async def eplusch(self, ctx: Context):
        command_ = ctx.message.content.split()[0]
        self.do_plusch(ctx, "", 'экивштырило' in command_)
        self.plusches += 1
        self.write_plusch()

    @commands.command(name='splusch', aliases=['самоплющ', 'самовштырь'])
    async def splusch(self, ctx: Context):
        display_name = ctx.author.display_name
        do_plusch(ctx, display_name, 'вштырь' in command_, True)