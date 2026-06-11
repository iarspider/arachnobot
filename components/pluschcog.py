import asyncio

from pytils import numeral
from twitchio.ext import commands
from twitchio.ext.commands import Component

from twitch_commands import twitch_command_aliased


class PluschCog(Component):
    def __init__(self, bot):
        self.bot = bot
        self.plusches = 0

        self.write_plusch()

    def write_plusch(self, init=False):
        if self.plusches == 0:
            text = "Пока что никого не плющило"
        else:
            text = "Кого-то поплющило {0}...".format(
                numeral.get_plural(self.plusches, ("раз", "раза", "раз"))
            )

        with open("plusch.txt", "w", encoding="utf8") as f:
            f.write(text)

        if self.bot.sio_server:
            asyncio.ensure_future(
                self.bot.sio_server.emit(
                    "update_plush_count",
                    {"text": text, "animate": not init},
                    namespace="/overlay",
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
            asyncio.ensure_future(self.bot.play_sound("my_sound//Вот это вштырило.mp3"))

        self.plusches += 1
        self.write_plusch()

    @twitch_command_aliased(name="plusch", aliases=("плющ", "вштырь"))
    async def plusch(self, ctx: commands.Context):
        command_ = ctx.message.text.split()[0]
        try:
            who = ctx.message.text.split(None, 1)[1]
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
        command_ = ctx.message.text.split()[0]
        self.do_plusch(ctx, "", "экивштырило" in command_)
        self.plusches += 1
        self.write_plusch()

    @twitch_command_aliased(name="splusch", aliases=("самоплющ", "самовштырь"))
    async def splusch(self, ctx: commands.Context):
        command_ = ctx.message.text.split()[0]
        display_name = ctx.author.display_name
        self.do_plusch(ctx, display_name, "вштырь" in command_, True)


async def setup(bot: commands.Bot):
    await bot.add_component(PluschCog(bot))
