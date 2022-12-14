import logging

from twitchio.ext import commands


class RaidCog:
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("arachnobot.raid")

    @commands.command(name="raid", aliases=("рейд", "битва", "мясо"))
    async def raid(self, ctx: commands.Context):
        await ctx.send(
            "Присоединяйтесь к битве: https://www.streamraiders.com/t/iarspider"
        )


def prepare(bot: commands.Bot):
    bot.add_cog(RaidCog(bot))
