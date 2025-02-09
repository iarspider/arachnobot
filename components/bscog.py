# Dummy cog for beatsaber+ commands
from twitchio.ext import commands
from twitchio.ext.commands import Component

from twitch_commands import twitch_command_aliased


class BSRCog(Component):
    @twitch_command_aliased(
        name="bsr",
        aliases=[
            "link",
            "bsrhelp",
            "queue",
            "queuestatus",
            "oops",
            "wrongsong",
            "wrong",
        ],
    )
    def bsr(self, ctx):
        return


def prepare(bot: commands.Bot):
    bot.add_cog(BSRCog())
