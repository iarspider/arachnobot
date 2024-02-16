import asyncio
import random
import sys
from collections import defaultdict

import peewee
from loguru import logger
from twitchio.ext import commands

from bot import DuelStats, Bot
from cogs.mycog import MyCog
from twitch_commands import twitch_command_aliased

sys.path.append("..")
from config import allow_duel_from_mod, allow_duel_to_bot, allow_duel_to_mod


class DuelCog(MyCog):
    def __init__(self, bot):
        self.bot = bot

        self.attacks = defaultdict(list)
        self.bots = bot.bots

    async def timeout(self, user: str, ctx: commands.Context, duration: int = 600):
        # TODO: use Twitch API for this
        await ctx.send(f"/timeout {user} {duration}")

    @twitch_command_aliased(name="fakeduel")
    async def fake_duel(self, ctx: commands.Context):
        if not self.check_sender(ctx, "iarspider"):
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
                "#FAKEDUEL! @{0} побеждает с результатом {1}:{2}!".format(
                    attacker_s, attack_d, defence_d
                )
            )
            # await ctx.timeout(defender, 60)
            d: DuelStats = DuelStats.get_or_create(
                attacker=attacker, defender=defender
            )[0]
            d.wins += 1
            d.save()
            d: DuelStats = DuelStats.get_or_create(
                attacker=defender, defender=attacker
            )[0]
            d.losses += 1
            d.save()
        elif attack_d < defence_d:
            await ctx.send(
                "#FAKEDUEL! @{0} побеждает с результатом {2}:{1}!".format(
                    defender_s, attack_d, defence_d
                )
            )
            # await ctx.timeout(attacker, 60)
            d: DuelStats = DuelStats.get_or_create(
                attacker=attacker, defender=defender
            )[0]
            d.losses += 1
            d.save()
            d: DuelStats = DuelStats.get_or_create(
                attacker=defender, defender=attacker
            )[0]
            d.wins += 1
            d.save()
        else:
            await ctx.send("#FAKEDUEL! Бойцы вырубили друг друга!")
            # await ctx.timeout(defender, 30)
            # await ctx.timeout(attacker, 30)

    @twitch_command_aliased(name="deny", aliases=("no", "pass"))
    async def deny_attack(self, ctx: commands.Context):
        defender_s = ctx.author.display_name
        defender = defender_s.lower()

        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !deny <от кого>")
        attacker_s = args[0].strip("@")
        attacker = attacker_s.lower()

        if not attacker in self.attacks[defender]:
            await ctx.send(f"{attacker_s} не вызывал на дуэль {defender_s}!")
            logger.info(self.attacks)
            return

        self.attacks[defender].remove(attacker)
        asyncio.ensure_future(
            ctx.send(
                f"Бой между {attacker_s} и {defender_s} не состоится, можете "
                f"расходиться"
            )
        )

    @twitch_command_aliased(name="accept", aliases=("yes", "ok"))
    async def accept_attack(self, ctx: commands.Context):
        defender_name = ctx.author.display_name
        defender_lower = defender_name.lower()

        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !accept <от кого>")

        attacker_name = args[0].strip("@")
        attacker_lower = attacker_name.lower()

        if not attacker_lower in self.attacks[defender_lower]:
            await ctx.send(f"{attacker_name} не вызывал на дуэль {defender_name}!")
            logger.info(self.attacks)
            return

        self.attacks[defender_lower].remove(attacker_lower)

        await ctx.send(
            "Пусть начнётся битва: {0} против {1}!".format(attacker_name, defender_name)
        )

        attack_d = random.randint(1, 20)
        defence_d = random.randint(1, 20)

        if attack_d > defence_d:
            await ctx.send(
                "@{0} побеждает с результатом {1}:{2}!".format(
                    attacker_name, attack_d, defence_d
                )
            )
            await self.timeout(defender_name, ctx, 60)
            d: DuelStats = DuelStats.get_or_create(
                attacker=attacker_lower, defender=defender_lower
            )[0]
            d.wins += 1
            d.save()
            d: DuelStats = DuelStats.get_or_create(
                attacker=defender_lower, defender=attacker_lower
            )[0]
            d.losses += 1
            d.save()
        elif attack_d < defence_d:
            await ctx.send(
                "@{0} побеждает с результатом {2}:{1}!".format(
                    defender_name, attack_d, defence_d
                )
            )
            await self.timeout(attacker_name, ctx, 60)
            d: DuelStats = DuelStats.get_or_create(
                attacker=attacker_lower, defender=defender_lower
            )[0]
            d.losses += 1
            d.save()
            d: DuelStats = DuelStats.get_or_create(
                attacker=defender_lower, defender=attacker_lower
            )[0]
            d.wins += 1
            d.save()
        else:
            await ctx.send("Бойцы вырубили друг друга!")
            await self.timeout(defender_name, ctx, 30)
            await self.timeout(attacker_name, ctx, 30)

    @twitch_command_aliased(name="attack")
    async def attack(self, ctx: commands.Context):
        attacker_s = ctx.author.display_name
        attacker = attacker_s.lower()
        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !attack <кого>")
            return

        defender = self.bot.viewers.get(args[0].strip("@"), None)
        if defender is None:
            await ctx.send(
                f"{args[0].strip('@')} сейчас не на стриме и не может быть вызван на "
                f"дуэль"
            )
            return

        if ctx.author.is_mod and not allow_duel_from_mod:
            await ctx.send("Модерам не нужны кубики, чтобы кого-то забанить :)")
            return

        if defender.is_mod and not allow_duel_to_mod:
            await ctx.send(f"А вот модеров не трожь, @{attacker}!")
            return

        if defender.display_name.lower() == attacker.lower():
            await ctx.send("РКН на тебя нет, негодяй!")
            await ctx.send(f"/timeout {defender.name} 120")
            return

        if defender.display_name.lower() in self.bots and not allow_duel_to_bot:
            await ctx.send("Ботика не трожь!")
            return

        defender_s = defender.display_name
        defender = defender_s.lower()
        self.attacks[defender].append(attacker)

        asyncio.ensure_future(
            ctx.send(
                f"@{defender_s}, тебя вызвал на дуэль {attacker_s}!"
                f" Чтобы принять вызов пошли в чат !accept {attacker_s}"
                f", чтобы отказаться - !deny {attacker_s}."
            )
        )

    async def get_duel_stats(self, ctx, author):
        cnt = DuelStats.select().where(DuelStats.attacker == author).count()
        if cnt == 0:
            asyncio.ensure_future(ctx.send(f"{author} ещё никого не атаковал"))
            return

        sum_wins, sum_losses = (
            DuelStats.select(
                peewee.fn.Sum(DuelStats.wins), peewee.fn.Sum(DuelStats.losses)
            )
            .where(DuelStats.attacker == author)
            .scalar(as_tuple=True)
        )

        max_wins = (
            DuelStats.select(
                DuelStats.attacker, peewee.fn.MAX(DuelStats.wins).alias("max_wins")
            )
            .where(DuelStats.attacker == author)
            .get()
            .max_wins
        )

        if max_wins > 0:
            result = DuelStats.select(
                DuelStats.attacker, DuelStats.defender, DuelStats.wins
            ).where((DuelStats.wins == max_wins) & (DuelStats.attacker == author))

            defenders_string = ", ".join([row.defender for row in result])
            max_wins = result[0].wins
            wins_string = (
                f"Чаще всего одерживал победу над {defenders_string} ({max_wins} раз),"
            )
        else:
            wins_string = "Не одерживал побед, "

        max_losses = (
            DuelStats.select(
                DuelStats.attacker, peewee.fn.MAX(DuelStats.losses).alias("max_losses")
            )
            .where(DuelStats.attacker == author)
            .get()
            .max_losses
        )

        if max_losses > 0:
            result = DuelStats.select(
                DuelStats.attacker, DuelStats.defender, DuelStats.losses
            ).where((DuelStats.losses == max_losses) & (DuelStats.attacker == author))

            defenders_string = ", ".join([row.defender for row in result])
            max_wins = result[0].wins
            losses_string = (
                f"Чаще всего терпел поражение от {defenders_string} ({max_losses} раз)"
            )
        else:
            losses_string = "не терпел поражений"

        asyncio.ensure_future(
            ctx.send(
                f"Статистика дуэлянта {author}: побед {sum_wins}, поражений {sum_losses}. {wins_string}{losses_string}"
            )
        )

    @twitch_command_aliased(name="duelstats")
    async def duelstats(self, ctx: commands.Context):
        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !duelstats <кто>")
            return

        await self.get_duel_stats(ctx, args[0].lower())

    @twitch_command_aliased(name="mystats")
    async def mystats(self, ctx: commands.Context):
        author = ctx.author.display_name.lower()
        await self.get_duel_stats(ctx, author)


def prepare(bot: Bot):
    bot.add_cog(DuelCog(bot))
