from twitchio.ext import commands

from bot import Bot
from cogs.mycog import MyCog
from twitch_commands import twitch_command_aliased


class RaidCog(MyCog):
    def __init__(self, bot):
        self.bot = bot

    @twitch_command_aliased(name="raid", aliases=("рейд", "битва", "мясо"))
    async def raid(self, ctx: commands.Context):
        await ctx.send(
            "Присоединяйтесь к битве: https://www.streamraiders.com/t/iarspider"
        )


def prepare(bot: Bot):
    bot.add_cog(RaidCog(bot))
