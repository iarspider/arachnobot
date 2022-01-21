import asyncio
import logging

from twitchio import Context
from twitchio.ext import commands


@commands.cog()
class ElvenCog:
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("arachnobot.elf")

        s1 = "&qwertyuiop[]asdfghjkl;'zxcvbnm,./QWERTYUIOP{}ASDFGHJKL:ZXCVBNM<>?`~" + '"'
        s2 = "?йцукенгшщзхъфывапролджэячсмитьбю.ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЯЧСМИТЬБЮ,ёЁ" + 'Э'
        self.trans = str.maketrans(s1, s2)

    @commands.command(name='translit', aliases=('translate', 'tr'))
    async def translit(self, ctx: Context):
        params = ctx.message.content.split()[1:]
        # print("translit(): ", params)
        if len(params) < 1 or len(params) > 2:
            return

        if len(params) == 1:
            try:
                count = int(params[0])
                author = ctx.author.name.lstrip('@')
            except ValueError:
                author = params[0].lstrip('@')
                count = 1
        else:
            try:
                author = params[0].lstrip('@')
                count = int(params[1])
            except ValueError:
                author = params[1].lstrip('@')
                count = int(params[0])
            

        # print(f"translit(): author {author}, count {count}")

        if self.bot.last_messages.get(author, None) is None:
            asyncio.ensure_future(ctx.send(f"{author} ещё ничего не посылал!"))
            return

        if len(self.bot.last_messages[author]) < count:
            count = len(self.bot.last_messages[author])

        messages = list(self.bot.last_messages[author])
        messages.reverse()
        messages = messages[:count]

        res = ["Перевод окончен"]

        format_fields = ['', '', '']
        format_fields[0] = '' if count == 1 else str(count) + ' '
        format_fields[1] = 'ее' if count == 1 else 'их'
        format_fields[2] = {1: 'е', 2: 'я', 3: 'я', 4: 'я'}.get(count, 'й')

        for message, emotes in messages:
            # message = messages[i].translate(self.trans)
            message_tr = []
            for word in message.split(" "):
                if not (word.startswith('@') or word in emotes):
                    word = word.translate(self.trans)
                message_tr.append(word)
            res.append(f'{" ".join(message_tr)}')

        res.append("Перевожу {0}последн{1} сообщени{2} @{author}:".format(*format_fields, author=author))

        for m in reversed(res):
            await ctx.send(m)
