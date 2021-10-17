import asyncio
import codecs
from typing import Optional
import logging

import sqlite3
from config import *

import requests
from twitchio import Context
from twitchio.ext import commands


@commands.core.cog()
class RIPCog:
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("arachnobot.rip")

        # Forwarding functions from bot
        self.is_vip = self.bot.is_vip
        self.check_sender = self.bot.check_sender

        self.deaths = {'today': 0, 'total': 0}

        self.rippers = ['iarspider', 'twistr_game', 'luciustenebrysflamos', 'phoenix__tv', 'wmuga', 'johnrico85',
                        'ved_s', 'owlsforever', 'antaryo']

        self.game = None

        self.obscog = None

        try:
            with open('rip.txt') as f:
                self.deaths['total'] = int(f.read().strip())
        except (FileNotFoundError, TypeError, ValueError):
            pass

    def init(self):
        self.get_game_v5()
        self.obscog = self.bot.get_cog('OBSCog')
        self.load_rip()

    def get_game_v5(self):
        r = requests.get(f'https://api.twitch.tv/helix/channels?broadcaster_id={self.bot.user_id}',
                         headers={'Authorization': f'Bearer {twitch_chat_password}',
                                  'Client-ID': twitch_client_id_alt})

        try:
            r.raise_for_status()
        except requests.RequestException as e:
            self.logger.error("Request to Helix API failed!" + str(e))
            return None

        if 'error' in r.json():
            self.logger.error("Request to Helix API failed!" + r.json()['message'])
            return None

        self.game = r.json()['data'][0]['game_name']
        print(f"self.game is {self.game}")

    def load_rip(self):
        print(f"self.game is {self.game}")
        if self.game is None:
            self.deaths = {'today': 0, 'total': 0}
            enabled = False
        else:
            db = sqlite3.connect('bot.db')
            cur = db.cursor()
            cur.execute('SELECT total,enabled FROM rip WHERE game=?;', (self.game,))
            res = cur.fetchone()
            if res is None:
                print("Game not known, fixing")
                cur.execute('INSERT INTO rip VALUES (?, 0, 1);', (self.game,))
                self.deaths['total'] = 0
                self.deaths['today'] = 0
                enabled = True
            else:
                print(f"Total deaths: {res[0]}")
                self.deaths['total'] = res[0]
                enabled = bool(res[1])

            cur.close()
            db.close()
        asyncio.ensure_future(self.obscog.enable_rip(enabled))
        if enabled:
            self.display_rip()

    def display_rip(self):
        with codecs.open('rip_display.txt', 'w', 'utf8') as f:
            f.write(u'☠: {today} (всего: {total})'.format(**self.deaths))

    def write_rip(self):
        self.display_rip()
        db = sqlite3.connect('bot.db')
        with db:
            db.execute("INSERT OR REPLACE INTO rip (game, total) VALUES (?, ?);", (self.game, self.deaths['total']))
        db.close()

    async def do_rip(self, ctx: Context, reason: Optional[str] = None, n=1):
        if not (ctx.author.is_mod or self.is_vip(ctx.author) or ctx.author.name.lower() in self.rippers):
            asyncio.ensure_future(ctx.send("Эту кнопку не трожь!"))
            return

        self.deaths['today'] += n
        self.deaths['total'] += n

        self.write_rip()
        if reason:
            await ctx.send(reason)

        asyncio.ensure_future(ctx.send("riPepperonis {today}".format(**self.deaths)))

    @commands.command(name='rip', aliases=("смерть", "кшз"))
    async def rip(self, ctx: Context):
        """
            Счётчик смертей

            %% rip
        """
        args = ctx.message.content.split()[1:]
        if args and (args[0] == 'who' or args[0] == '?'):
            ans = 'Счетоводы: ' + ', '.join(self.rippers)

        if args and args[0].startswith('+'):
            try:
                n_rip = int(args[0])
            except ValueError:
                n_rip = 1
        else:
            n_rip = 1

        await self.do_rip(ctx, n=n_rip)

    @commands.command(name='unrip')
    async def unrip(self, ctx: Context):
        """
        Отмена смерти
        """
        if not self.check_sender(ctx, 'iarspider'):
            return

        self.deaths['today'] -= 1
        self.deaths['total'] -= 1

        self.write_rip()

        asyncio.ensure_future(ctx.send("MercyWing1 PinkMercy MercyWing2"))

    @commands.command(name='enrip')
    async def enrip(self, ctx: Context):
        """
        Временно (до перезапуска бота) добавляет пользователя в rip-список
        """
        if not self.check_sender(ctx, 'iarspider'):
            return

        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            asyncio.ensure_future(ctx.send("Неправильный запрос"))
        self.rippers.append(args[0].lower())

        asyncio.ensure_future(ctx.send("{0} TwitchVotes ".format(args[0])))

    @commands.command(name='lrip')
    async def lrip(self, ctx: Context):
        """
        Перезагружает счётчик смертей (в случае смены игры)
        """
        if not self.check_sender(ctx, 'iarspider'):
            print("check_sender failed")
            return

        self.get_game_v5()
        self.load_rip()
        await ctx.send('Счётчик смертей обновлён')

    @commands.command(name='setrip')
    async def setrip(self, ctx: Context):
        """
        Устанавливает значение счётчика смертей за сегодня
        """
        try:
            arg = int(ctx.message.content.split()[1])
        except (IndexError, ValueError):
            await ctx.send("Usage: !setrip <N>")
            return
        else:
            self.deaths['today'] = arg
            self.display_rip()

    @commands.command(name='yesrip')
    async def yesrip(self, ctx: Context):
        """
        Включает отображение смертей
        """
        db = sqlite3.connect('bot.db')
        with db:
            db.execute("INSERT OR REPLACE INTO rip (game, enabled) VALUES (?, 1);", (self.game,))
        db.close()
        await self.obscog.enable_rip(True)
        await ctx.send('Счётчик смертей активирован')

    @commands.command(name='norip')
    async def norip(self, ctx: Context):
        """
        Включает отображение смертей
        """
        db = sqlite3.connect('bot.db')
        with db:
            db.execute("INSERT OR REPLACE INTO rip (game, enabled) VALUES (?, 0);", (self.game,))
        db.close()
        await self.obscog.enable_rip(False)
        await ctx.send('Счётчик смертей отключён')

    # @commands.command(name='ripz')
    # async def ripz(self, ctx: Context):
    #     """
    #         Счётчик смертей
    #
    #         %% ripz
    #     """
    #     await self.do_rip(ctx, "#Отзомбячено!")
    #
    # @commands.command(name='riph')
    # async def riph(self, ctx: Context):
    #     """
    #         Счётчик смертей
    #
    #         %% riph
    #     """
    #     await self.do_rip(ctx, "#Захедкраблено")
    #
    # @commands.command(name='ripc')
    # async def ripc(self, ctx: Context):
    #     """
    #         Счётчик смертей
    #
    #         %% ripc
    #     """
    #     await self.do_rip(ctx, "#Укомбайнено")
    #
    # @commands.command(name='ripb')
    # async def ripb(self, ctx: Context):
    #     """
    #         Счётчик смертей
    #
    #         %% ripb
    #     """
    #     await self.do_rip(ctx, "#Барнакнуто")
    #
    # @commands.command(name='ripn', aliases=['nom', 'omnomnom', 'ном', 'ням', 'омномном'])
    # async def nom(self, ctx: Context):
    #     await self.do_rip(ctx, 'Ом-ном-ном!')
