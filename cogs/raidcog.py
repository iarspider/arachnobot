from twitchio.ext import commands

from bot import Bot
from cogs.mycog import MyCog


class RaidCog(MyCog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="raid", aliases=("рейд", "битва", "мясо"))
    async def raid(self, ctx: commands.Context):
        await ctx.send(
            "Присоединяйтесь к битве: https://www.streamraiders.com/t/iarspider"
        )


def prepare(bot: Bot):
    bot.add_cog(RaidCog(bot))
