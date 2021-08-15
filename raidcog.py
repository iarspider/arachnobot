import logging

from twitchio import Context
from twitchio.ext import commands


@commands.cog()
class RaidCog:
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("arachnobot.raid")

    @commands.command(name="raid", aliases=("рейд", "битва", "мясо"))
    async def raid(self, ctx:Context):
        await ctx.send("Присоединяйтесь к битве: https://www.streamraiders.com/t/iarspider")