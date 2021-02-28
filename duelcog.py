import asyncio
import random
from collections import defaultdict
from twitchio.dataclasses import Context, User
from twitchio.ext import commands
import logging


@commands.core.cog()
class DuelCog:
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("arachnobot.duel")

        self.attacks = defaultdict(list)
        self.bots = bot.bots

    @commands.command(name='deny', aliases=('no', 'pass'))
    async def deny_attack(self, ctx: Context):
        defender = ctx.author.display_name

        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !deny <от кого>")
        attacker = args[0].strip('@')

        if not attacker.lower() in self.attacks[defender]:
            return

        self.attacks[defender].remove(attacker.lower())
        asyncio.ensure_future(ctx.send(f"Бой между {attacker} и {defender} не состоится, можете расходиться"))

    @commands.command(name='accept', aliases=('yes', 'ok'))
    async def accept_attack(self, ctx: Context):
        defender = ctx.author.display_name

        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !accept <от кого>")
        attacker = args[0].strip('@')

        if not attacker.lower() in self.attacks[defender]:
            return

        self.attacks[defender].remove(attacker.lower())

        await ctx.send("Пусть начнётся битва: {0} против {1}!".format(attacker, defender))

        attack_d = random.randint(1, 20)
        defence_d = random.randint(1, 20)

        if attack_d > defence_d:
            await ctx.send(
                "@{0} побеждает с результатом {1}:{2}!".format(attacker, attack_d, defence_d))
            await ctx.timeout(defender, 60)
        elif attack_d < defence_d:
            await ctx.send(
                "@{0} побеждает с результатом {2}:{1}!".format(defender, attack_d, defence_d))
            await ctx.timeout(attacker, 60)
        else:
            await ctx.send("Бойцы вырубили друг друга!")
            await ctx.timeout(defender, 30)
            await ctx.timeout(attacker, 30)

    @commands.command(name='attack')
    async def attack(self, ctx: Context):
        attacker = ctx.author.display_name
        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !attack <кого>")
            return

        defender = self.bot.viewers.get(args[0].strip('@'), None)
        if defender is None:
            await ctx.send(f"{defender} сейчас не на стриме и не может быть вызван на дуэль")
            return

        if ctx.author.is_mod:
            await ctx.send("Модерам не нужны кубики, чтобы кого-то забанить :)")
            return

        if defender.is_mod:
            await ctx.send(f"А вот модеров не трожь, @{attacker}!")
            return

        if defender.display_name.lower() == attacker.lower():
            await ctx.send("РКН на тебя нет, негодяй!")
            await ctx.timeout(defender, 120)
            return

        if defender.display_name.lower() in self.bots:
            await ctx.send("Ботика не трожь!")
            return

        asyncio.ensure_future(ctx.send(f"@{defender.display_name}, тебя вызвал на дуэль {attacker}!"
                                       f" Чтобы принять вызов пошли в чат !accept {attacker}"
                                       f", чтобы отказаться - !deny {attacker}."))

        attacker = attacker.lower()
        defender = defender.display_name.lower()
        self.attacks[defender].append(attacker)
