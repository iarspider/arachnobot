import asyncio
import codecs

from pytils import numeral

from twitchio.ext import commands

from cogs.mycog import MyCog
from twitch_commands import twitch_command_aliased


class PluschCog(MyCog):
    def __init__(self, bot):
        self.bot = bot
        self.plusches = 0

        self.write_plusch()

    def write_plusch(self):
        with codecs.open("plusch.txt", "w", "utf8") as f:
            if self.plusches == 0:
                f.write("Пока что никого не плющило")
            else:
                f.write(
                    "Кого-то поплющило {0}...".format(
                        numeral.get_plural(self.plusches, ("раз", "раза", "раз"))
                    )
                )

    def do_plusch(self, ctx: commands.Context, who="", shtyr=False, slf=False):
        if not who.strip():
            who = "кого-то"

        if not shtyr:
            asyncio.ensure_future(
                ctx.send("Эк {0} {1}поплющило...".format(who, "само" if slf else ""))
            )
        else:
            asyncio.ensure_future(
                ctx.send(
                    "Эк {0} вштырно {1}поплющило...".format(who, "само" if slf else "")
                )
            )

        self.plusches += 1
        self.write_plusch()

    @twitch_command_aliased(name="plusch", aliases=("плющ", "вштырь"))
    async def plusch(self, ctx: commands.Context):
        command_ = ctx.message.content.split()[0]
        try:
            who = ctx.message.content.split(None, 1)[1]
            self.do_plusch(ctx, who, "вштырь" in command_)
        except IndexError:
            self.do_plusch(ctx, "", "вштырь" in command_)
            pass

    @twitch_command_aliased(name="plushch", aliases=("плющь", "вштыр"))
    async def plushch(self, ctx: commands.Context):
        await ctx.send(
            f"/me стукнул {ctx.author.display_name} по голове учебником Розенталя"
        )

    @twitch_command_aliased(name="eplusch", aliases=("экипоплющило", "экивштырило"))
    async def eplusch(self, ctx: commands.Context):
        command_ = ctx.message.content.split()[0]
        self.do_plusch(ctx, "", "экивштырило" in command_)
        self.plusches += 1
        self.write_plusch()

    @twitch_command_aliased(name="splusch", aliases=("самоплющ", "самовштырь"))
    async def splusch(self, ctx: commands.Context):
        command_ = ctx.message.content.split()[0]
        display_name = ctx.author.display_name
        self.do_plusch(ctx, display_name, "вштырь" in command_, True)


def prepare(bot: commands.Bot):
    bot.add_cog(PluschCog(bot))
