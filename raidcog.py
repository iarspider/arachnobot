import logging

from twitchio.ext import commands
from twitchio.ext.commands import Cog, Context

from singleton import Singleton


class RaidCog(Cog, metaclass=Singleton):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("arachnobot.raid")

    @commands.command(name="raid", aliases=("рейд", "битва", "мясо"))
    async def raid(self, ctx: Context):
        await ctx.send("Присоединяйтесь к битве: https://www.streamraiders.com/t/iarspider")
