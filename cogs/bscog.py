# Dummy cog for beatsaber+ commands
from twitchio.ext import commands

from cogs.mycog import MyCog


class BSRCog(MyCog):
    @commands.command(name="bsr", aliases=["link", "bsrhelp", "queue", "queuestatus",
                                           "!oops", "!wrongsong", "!wrong"])
    def bsr(self, ctx):
        return

def prepare(bot: commands.Bot):
    bot.add_cog(BSRCog())
