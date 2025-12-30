import asyncio


from twitchio import ChatMessageFragment
from twitchio.ext import commands
from twitchio.ext.commands import Component

from twitch_commands import twitch_command_aliased


class ElvenCog(Component):
    def __init__(self, bot):
        self.bot = bot

        s1 = (
            "&qwertyuiop[]asdfghjkl;'zxcvbnm,./QWERTYUIOP{}ASDFGHJKL:ZXCVBNM<>?`~" + '"'
        )
        s2 = (
            "?йцукенгшщзхъфывапролджэячсмитьбю.ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЯЧСМИТЬБЮ,ёЁ" + "Э"
        )
        self.trans = str.maketrans(s1, s2)

    @twitch_command_aliased(
        name="translit",
        aliases=("translate", "tr", "trans", "перевод", "переведи", "эльф"),
    )
    async def translit(self, ctx: commands.Context):
        params = ctx.message.text.split()[1:]
        # print("translit(): ", params)
        if len(params) < 1 or len(params) > 2:
            return

        if len(params) == 1:
            try:
                count = int(params[0])
                author = ctx.author.name.lstrip("@")
            except ValueError:
                author = params[0].lstrip("@")
                count = 1
        else:
            try:
                author = params[0].lstrip("@")
                count = int(params[1])
            except ValueError:
                author = params[1].lstrip("@")
                count = int(params[0])

        # print(f"translit(): author {author}, count {count}")

        if self.bot.last_messages.get(author, None) is None:
            asyncio.ensure_future(ctx.send(f"{author} ещё ничего не посылал!"))
            return

        count = min(count, len(self.bot.last_messages[author]))

        messages = list(reversed(self.bot.last_messages[author]))
        if count > 0:
            messages = messages[:count]
        else:
            messages = [messages[abs(count)]]

        res = ["Перевод окончен"]

        format_fields = ["", "", ""]
        format_fields[0] = "" if count == 1 else str(count) + " "
        format_fields[1] = "ее" if count == 1 else "их"
        format_fields[2] = {1: "е", 2: "я", 3: "я", 4: "я"}.get(count, "й")

        for fragments in messages:
            # message = messages[i].translate(self.trans)
            # type fragments: List[ChatMessageFragment]
            fragment: ChatMessageFragment
            message_tr = []

            for fragment in fragments:

                if fragment.type == "text":
                    for word in fragment.text.split(" "):
                        if not word.startswith("@"):
                            word = word.translate(self.trans)
                        message_tr.append(word)
                elif fragment.type == "emote":
                    message_tr.append(fragment.text)

            res.append(" ".join(message_tr))

        res.append(
            "Перевожу {0}последн{1} сообщени{2} @{author}:".format(
                *format_fields, author=author
            )
        )

        for m in reversed(res):
            await ctx.send(m)


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(ElvenCog(bot))
