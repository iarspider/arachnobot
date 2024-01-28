# Dummy cog for beatsaber+ commands
from twitchio.ext import commands

from cogs.mycog import MyCog
from twitch_commands import twitch_command_aliased


class BSRCog(MyCog):
    @twitch_command_aliased(
        name="bsr",
        aliases=[
            "link",
            "bsrhelp",
            "queue",
            "queuestatus",
            "!oops",
            "!wrongsong",
            "!wrong",
        ],
    )
    def bsr(self, ctx):
        return


def prepare(bot: commands.Bot):
    bot.add_cog(BSRCog())
