import asyncio
import random
from collections import defaultdict

import peewee
from twitchio.dataclasses import Context
from twitchio.ext import commands
import logging

from mycog import MyCog

from bot import DuelStats

from config import *


@commands.core.cog()
class DuelCog(MyCog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("arachnobot.duel")

        self.attacks = defaultdict(list)
        self.bots = bot.bots

    @commands.command(name='fakeduel')
    async def fake_duel(self, ctx: Context):
        if not self.check_sender(ctx, 'iarspider'):
            return

        args = ctx.message.content.split()[1:]
        if len(args) != 4:
            await ctx.send("Usage: fake_duel attacker defender score_a score_d")
            return

        attacker, defender, attack_d, defence_d = args
        attacker_s = attacker
        defender_s = defender

        if attack_d > defence_d:
            await ctx.send(
                "#FAKEDUEL! @{0} побеждает с результатом {1}:{2}!".format(attacker_s, attack_d, defence_d))
            # await ctx.timeout(defender, 60)
            d: DuelStats = DuelStats.get_or_create(attacker=attacker, defender=defender)[0]
            d.wins += 1
            d.save()
            d: DuelStats = DuelStats.get_or_create(attacker=defender, defender=attacker)[0]
            d.losses += 1
            d.save()
        elif attack_d < defence_d:
            await ctx.send(
                "#FAKEDUEL! @{0} побеждает с результатом {2}:{1}!".format(defender_s, attack_d, defence_d))
            # await ctx.timeout(attacker, 60)
            d: DuelStats = DuelStats.get_or_create(attacker=attacker, defender=defender)[0]
            d.losses += 1
            d.save()
            d: DuelStats = DuelStats.get_or_create(attacker=defender, defender=attacker)[0]
            d.wins += 1
            d.save()
        else:
            await ctx.send("#FAKEDUEL! Бойцы вырубили друг друга!")
            # await ctx.timeout(defender, 30)
            # await ctx.timeout(attacker, 30)

    @commands.command(name='deny', aliases=('no', 'pass'))
    async def deny_attack(self, ctx: Context):
        defender_s = ctx.author.display_name
        defender = defender_s.lower()

        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !deny <от кого>")
        attacker_s = args[0].strip('@')
        attacker = attacker_s.lower()

        if not attacker in self.attacks[defender]:
            await ctx.send(f'{attacker_s} не вызывал на дуэль {defender_s}!')
            self.logger.info(self.attacks)
            return

        self.attacks[defender].remove(attacker)
        asyncio.ensure_future(ctx.send(f"Бой между {attacker_s} и {defender_s} не состоится, можете расходиться"))

    @commands.command(name='accept', aliases=('yes', 'ok'))
    async def accept_attack(self, ctx: Context):
        defender_s = ctx.author.display_name
        defender = defender_s.lower()

        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !accept <от кого>")

        attacker_s = args[0].strip('@')
        attacker = attacker_s.lower()

        if not attacker in self.attacks[defender]:
            await ctx.send(f'{attacker_s} не вызывал на дуэль {defender_s}!')
            self.logger.info(self.attacks)
            return

        self.attacks[defender].remove(attacker)

        await ctx.send("Пусть начнётся битва: {0} против {1}!".format(attacker_s, defender_s))

        attack_d = random.randint(1, 20)
        defence_d = random.randint(1, 20)

        if attack_d > defence_d:
            await ctx.send(
                "@{0} побеждает с результатом {1}:{2}!".format(attacker_s, attack_d, defence_d))
            await ctx.timeout(defender, 60)
            d: DuelStats = DuelStats.get_or_create(attacker=attacker, defender=defender)[0]
            d.wins += 1
            d.save()
            d: DuelStats = DuelStats.get_or_create(attacker=defender, defender=attacker)[0]
            d.losses += 1
            d.save()
        elif attack_d < defence_d:
            await ctx.send(
                "@{0} побеждает с результатом {2}:{1}!".format(defender_s, attack_d, defence_d))
            await ctx.timeout(attacker, 60)
            d: DuelStats = DuelStats.get_or_create(attacker=attacker, defender=defender)[0]
            d.losses += 1
            d.save()
            d: DuelStats = DuelStats.get_or_create(attacker=defender, defender=attacker)[0]
            d.wins += 1
            d.save()
        else:
            await ctx.send("Бойцы вырубили друг друга!")
            await ctx.timeout(defender, 30)
            await ctx.timeout(attacker, 30)

    @commands.command(name='attack')
    async def attack(self, ctx: Context):
        attacker_s = ctx.author.display_name
        attacker = attacker_s.lower()
        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !attack <кого>")
            return

        defender = self.bot.viewers.get(args[0].strip('@'), None)
        if defender is None:
            await ctx.send(f"{args[0].strip('@')} сейчас не на стриме и не может быть вызван на дуэль")
            return

        if ctx.author.is_mod and not allow_duel_from_mod:
            await ctx.send("Модерам не нужны кубики, чтобы кого-то забанить :)")
            return

        if defender.is_mod and not allow_duel_to_mod:
            await ctx.send(f"А вот модеров не трожь, @{attacker}!")
            return

        if defender.display_name.lower() == attacker.lower():
            await ctx.send("РКН на тебя нет, негодяй!")
            await ctx.timeout(defender, 120)
            return

        if defender.display_name.lower() in self.bots and not allow_duel_to_bot:
            await ctx.send("Ботика не трожь!")
            return

        defender_s = defender.display_name
        defender = defender_s.lower()
        self.attacks[defender].append(attacker)

        asyncio.ensure_future(ctx.send(f"@{defender_s}, тебя вызвал на дуэль {attacker_s}!"
                                       f" Чтобы принять вызов пошли в чат !accept {attacker}"
                                       f", чтобы отказаться - !deny {attacker}."))

    @commands.command(name='mystats')
    async def mystats(self, ctx: Context):
        author = ctx.author.display_name.lower()
        cnt = DuelStats.select().where(DuelStats.attacker == author).count()
        if cnt == 0:
            asyncio.ensure_future(ctx.send(f"{author} ещё никого не атаковал"))
            return

        sum_wins, sum_losses = DuelStats.select(peewee.fn.Sum(DuelStats.wins), peewee.fn.Sum(DuelStats.losses)).where(
            DuelStats.attacker == author).scalar(as_tuple=True)

        res = DuelStats.select(DuelStats.wins, DuelStats.defender).filter(DuelStats.attacker == author).order_by(
            DuelStats.wins.asc()).get()

        max_wins = res.wins
        defender_a = res.defender

        res = DuelStats.select(DuelStats.wins, DuelStats.defender).filter(DuelStats.attacker == author).order_by(
            DuelStats.losses.asc()).get()

        max_losses = res.losses
        defender_b = res.defender

        asyncio.ensure_future(ctx.send(f"Статистика {author}: побед {sum_wins}, поражений {sum_losses}. "
                                       f"Чаще всего побеждал {defender_a} ({max_wins} раз), "
                                       f"чаще всего проигрывал {defender_b} ({max_losses} раз)"))
