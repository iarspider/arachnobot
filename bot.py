import asyncio
import codecs
import copy
import datetime
import pathlib
import random
from collections import deque, defaultdict
from multiprocessing import Process
from typing import Union, Iterable, Optional

import colorlog
import discord
import pygame
import requests
import simplejson
import socketio
import twitchio
import uvicorn
from pytils import numeral
from requests.structures import CaseInsensitiveDict
# For typing
from twitchio.dataclasses import Context, User
from twitchio.ext import commands

import twitch_api
from config import *

try:
    import pywinauto
except ImportError as e:
    print("[WARN] PyWinAuto not found, sending keys will not work" + str(e))
    pywinauto = None

import logging
import http.client as http_client

httpclient_logger = logging.getLogger("http.client")
logger: logging.Logger
proc: Process
timer: asyncio.Task
sl_client: socketio.AsyncClient


def setup_logging(logfile, debug, color, http_debug):
    global logger
    logger = logging.getLogger("bot")
    logger.propagate = False
    ws_logger = logging.getLogger('websockets.server')

    handler = logging.StreamHandler()
    if color:
        handler.setFormatter(
            colorlog.ColoredFormatter(
                '%(asctime)s %(log_color)s[%(name)s:%(levelname)s:%(lineno)s]%(reset)s %(message)s',
                datefmt='%H:%M:%S'))
    else:
        handler.setFormatter(logging.Formatter(fmt="%(asctime)s [%(name)s:%(levelname)s:%(lineno)s] %(message)s",
                                               datefmt='%H:%M:%S'))

    file_handler = logging.FileHandler(logfile, "w")
    file_handler.setFormatter(logging.Formatter(fmt="%(asctime)s [%(name)s:%(levelname)s:%(lineno)s] %(message)s"))

    logger.addHandler(handler)
    logger.addHandler(file_handler)

    ws_logger.addHandler(handler)
    ws_logger.addHandler(file_handler)

    if not debug:
        logger.setLevel(logging.INFO)
        logging.getLogger('discord').setLevel(logging.INFO)
        ws_logger.setLevel(logging.INFO)
    else:
        logger.info("Debug logging is ON")
        logger.setLevel(logging.DEBUG)
        logging.getLogger('discord').setLevel(logging.DEBUG)
        ws_logger.setLevel(logging.DEBUG)

    if http_debug:
        http_client.HTTPConnection.debuglevel = 1


def httpclient_logging_patch(level=logging.DEBUG):
    """Enable HTTPConnection debug logging to the logging framework"""

    def httpclient_log(*args):
        httpclient_logger.log(level, " ".join(args))

    # mask the print() built-in in the http.client module to use
    # logging instead
    http_client.print = httpclient_log
    # enable debugging
    http_client.HTTPConnection.debuglevel = 1


async def create_timer(timeout, stuff):
    while True:
        await asyncio.sleep(timeout)
        await stuff()


class Bot(commands.Bot):
    def __init__(self, loop: asyncio.AbstractEventLoop = None):
        super().__init__(irc_token='oauth:' + twitch_chat_password,
                         client_id=twitch_client_id, nick='arachnobot',
                         prefix='!',
                         initial_channels=['#iarspider'],
                         loop=loop)

        self.logger = logger

        self.mods = set()
        self.subs = set()
        self.viewers = set()
        self.vips = set()

        self.db = {}

        self.user_id = -1
        self.plusches = 0

        self.last_post = CaseInsensitiveDict()
        self.post_timeout = 10 * 60
        self.post_price = {'regular': 20, 'vip': 10, 'mod': 0}

        self.vmod = None
        self.vmod_active = False
        self.pubsub_nonce = ''

        s1 = "&qwertyuiop[]asdfghjkl;'zxcvbnm,./QWERTYUIOP{}ASDFGHJKL;\"ZXCVBNM<>?`~"
        s2 = "?йцукенгшщзхъфывапролджэячсмитьбю.ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,ёЁ"
        self.trans = str.maketrans(s1, s2)

        self.last_messages = CaseInsensitiveDict()
        self.attacks = defaultdict(list)
        self.bots = (self.nick, 'nightbot', 'pretzelrocks', 'streamlabs', 'commanderroot', 'electricallongboard')
        self.countdown_to: Optional[datetime.datetime] = None  # ! keep this here !
        self.dashboard = None
        self.queue = asyncio.Queue()

        self.setup_mixer()
        self.write_plusch()

    # Fill in missing stuff
    def get_cog(self, name):
        try:
            return self.cogs[name]
        except KeyError:
            logger.error(f"No such cog: {name}")
            return None

    # twitchio, I can and will handle pubsub
    async def event_pubsub(self, data):
        pass

    @staticmethod
    async def sl_event(data):
        logger.debug(f'SL event: {data}!')

    @staticmethod
    async def sl_connected():
        logger.debug(f'SL connected!')

    # noinspection PyPep8Naming
    @staticmethod
    def setup_mixer():
        def getmixerargs():
            pygame.mixer.init()
            freq, size, chan = pygame.mixer.get_init()
            return freq, size, chan

        BUFFER = 3072  # audio buffer size, number of samples since pygame 1.8.
        FREQ, SIZE, CHAN = getmixerargs()

        pygame.mixer.init(FREQ, SIZE, CHAN, BUFFER)
        pygame.init()

    @staticmethod
    def play_sound(sound: str):
        soundfile = pathlib.Path(__file__).with_name(sound)
        logger.debug("play sound", soundfile)
        pygame.mixer.music.load(str(soundfile))
        pygame.mixer.music.play()

    def is_online(self, nick: str):
        nick = nick.lower()
        return nick in self.viewers  # or online_bot

    def is_mod(self, nick: str):
        return nick.lower() in self.mods  # or is_mod_by_prefix

    def is_vip(self, nick: str):
        return nick.lower() in self.vips

    # Events don't need decorators when subclassed
    async def event_ready(self):
        logger.info(f'Ready | {self.nick}')
        self.user_id = self.my_get_users(self.initial_channels[0].lstrip('#'))['id']
        sess = twitch_api.get_session(twitch_client_id, twitch_client_secret, twitch_redirect_url)
        self.pubsub_nonce = await self.pubsub_subscribe(sess.token["access_token"],
                                                        'channel-points-channel-v1.{0}'.format(self.user_id))
        # socket_token = api.get_socket_token(self.streamlabs_oauth)
        # self.streamlabs_socket.on('message', self.sl_event)
        # self.streamlabs_socket.on('connect', self.sl_connected)
        #

    async def send_viewer_joined(self, user: User):
        if user.name.lower() in self.bots:
            return

        femme = (user.name.lower() in twitch_ladies)

        if user.badges.get('subscriber', 0):
            status = 'spider'
        elif user.badges.get('moderator', 0):
            status = 'hammer'
        elif user.badges.get('vip', 0):
            status = 'award'
        else:
            status = 'eye'

        color = user.tags.get('color', '#8F8F8F')

        logger.debug(f"Tags: {user.tags}")
        logger.debug(f"Badges: {user.badges}")
        logger.debug(f"Send user {user.display_name} with status {status} and color {color}")

        await self.queue.put({'action': 'add', 'value': {'name': user.display_name, 'status': status,
                                                         'color': color, 'femme': femme}})

    async def send_viewer_left(self, user: User):
        if user.name.lower() in self.bots:
            return

        await self.queue.put({'action': 'remove', 'value': user.display_name})

    async def event_message(self, message):
        # if message.author.name.lower() not in self.viewers:
        await self.send_viewer_joined(message.author)

        logger.debug("JOIN sent")

        self.viewers.add(message.author.name.lower())
        if message.author.is_mod:
            self.mods.add(message.author.name.lower())
        if message.author.is_subscriber:
            self.subs.add(message.author.name.lower())

        if message.author.badges.get('vip', 0) == 1:
            self.vips.add(message.author.name.lower())

        if message.author.name not in self.last_messages:
            self.last_messages[message.author.name] = deque(maxlen=10)

        if message.author.name.lower() not in self.bots:
            if not message.content.startswith('!'):
                self.last_messages[message.author.name].append(message.content)
                logger.debug(f"Updated last messages for {message.author.name}, " +
                             f"will remember last {len(self.last_messages[message.author.name])}")

        if message.content.startswith('!'):
            message.content = '!' + message.content.lstrip('! ')
            try:
                command, args = message.content.split(' ', 1)
                args = ' ' + args
            except ValueError:
                command = message.content
                args = ''
            message.content = command.lower() + args

        logger.debug("handle_command start")
        await self.handle_commands(message)

    # async def event_join(self, user):
    #     if user.name.lower() not in self.viewers:
    #         # await self.send_viewer_joined(user.name)
    #         # self.viewers.add(user.name.lower())
    #         logger.info(f"User {user.name} joined! tags {user.tags}, badges {user.badges}")

    async def event_part(self, user: User):
        if user.name.lower() in self.viewers:
            await asyncio.ensure_future(self.send_viewer_left(user))

        try:
            self.viewers.remove(user.name.lower())
        except KeyError:
            pass

        try:
            self.mods.remove(user.name.lower())
        except KeyError:
            pass

        try:
            self.subs.remove(user.name.lower())
        except KeyError:
            pass

    async def event_pubsub_message_channel_points_channel_v1(self, data):
        # import pprint
        # pprint.pprint(data)
        d = datetime.datetime.now().timestamp()

        if data.get('type', '') != 'reward-redeemed':
            return

        reward = data['data']['redemption']['reward']['title']
        reward_key = reward.replace(' ', '')
        # noinspection PyUnusedLocal
        prompt = data['data']['redemption']['reward']['prompt']
        try:
            requestor = data['data']['redemption']['user'].get('display_name',
                                                               data['data']['redemption']['user']['login'])
        except KeyError:
            logger.error(f"Failed to get reward requestor! Saving reward in {d}.json")
            with open(f'{d}.json', 'w', encoding='utf-8') as f:
                simplejson.dump(data, f)
            requestor = 'Unknown'

        logger.debug("Reward:", reward)
        logger.debug("Key:", reward_key)
        logger.debug("Prompt:", prompt)

        if reward_key == "Смена голоса на 1 минуту".replace(' ', ''):
            vmod = self.get_cog('VMcog')
            asyncio.ensure_future(vmod.activate_voicemod())

        if reward_key == "Обнять стримера".replace(' ', ''):
            logger.debug(f"Queued redepmtion: hugs, {requestor}")
            await self.queue.put({'action': 'event', 'value': {'type': 'hugs', 'from': requestor}})

        if reward_key == "Стримлер! Не горбись!".replace(' ', ''):
            logger.debug(f"Queued redepmtion: sit, {requestor}")
            await self.queue.put({'action': 'event', 'value': {'type': 'sit', 'from': requestor}})

        if reward_key == "Добавить упорину".replace(' ', ''):
            logger.debug(f"Queued redepmtion: fun, {requestor}")
            await self.queue.put({'action': 'event', 'value': {'type': 'fun', 'from': requestor}})

    async def event_pubsub_response(self, data):
        if data['nonce'] == self.pubsub_nonce and self.pubsub_nonce != '':
            if data['error'] != '':
                raise RuntimeError("PubSub failed: " + data['error'])
            else:
                self.pubsub_nonce = ''  # We are done

    async def event_pubsub_message(self, data):
        data = data['data']
        topic = data['topic'].rsplit('.', 1)[0].replace('-', '_')
        data['message'] = simplejson.loads(data['message'])
        handler = getattr(self, 'event_pubsub_message_' + topic, None)
        if handler:
            asyncio.ensure_future(handler(data['message']))

    async def event_raw_pubsub(self, data):
        topic = data['type'].lower()
        handler = getattr(self, 'event_pubsub_' + topic, None)
        if handler:
            asyncio.ensure_future(handler(data))

    @staticmethod
    def check_sender(ctx: Context, users: Union[str, Iterable[str]]):
        if isinstance(users, str):
            users = (users,)

        return ctx.author.name in users

    # async def event_raw_data(self, data):
    #     lines = data.splitlines(keepends=False)
    #     for line in lines:
    #         print('>', line)

    # Commands use a different decorator
    # @commands.command(name='test')
    # async def test(self, ctx: Context):
    #     await ctx.send(f'Hello {ctx.author.name}!')

    @commands.command(name='roll', aliases=['dice', 'кинь', 'r'])
    async def roll(self, ctx: Context):
        dices = []

        args = ctx.message.content.split()[1:]
        # print(args)
        if args is None or len(args) == 0:
            dices = ((1, 6),)
        else:
            for arg in args:
                # print("arg is", arg)
                if 'd' not in arg:
                    continue
                num, sides = arg.split('d')
                try:
                    if not num:
                        num = 1
                    else:
                        num = int(num)
                    sides = int(sides)
                except ValueError:
                    continue

                if not ((0 < num <= 10) and (2 <= sides <= 100)):
                    continue

                dices.append((num, sides))
                # print("Rolling {0} {1}-sided dice(s)".format(num, sides))

        rolls = []
        for num, sides in dices:
            rolls.extend([random.randint(1, sides) for _ in range(num)])

        roll_sum = sum(rolls)
        # print("You rolled:", ";".join(str(x) for x in rolls), "sum is", roll_sum)
        if len(rolls) > 1:
            await ctx.send(
                "@{} выкинул: {}={}".format(ctx.author.display_name, "+".join(str(x) for x in rolls), roll_sum))
        elif len(rolls) == 1:
            await ctx.send("@{} выкинул: {}".format(ctx.author.display_name, roll_sum))

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
        defender = args[0].strip('@')

        if self.is_mod(attacker):
            await ctx.send("Модерам не нужны кубики, чтобы кого-то забанить :)")
            return

        if self.is_mod(defender):
            await ctx.send(f"А вот модеров не трожь, @{attacker}!")
            await asyncio.sleep(15)
            await ctx.timeout(attacker, 1)
            return

        # if not self.is_online(defender):
        #     await ctx.send(
        #         f"Эй, @{attacker}, ты не можешь напасть на {defender} - он(а) сейчас не в сети!")
        #     return

        if defender.lower() == attacker.lower():
            await ctx.send("РКН на тебя нет, негодяй!")
            await ctx.timeout(defender, 120)
            return

        if defender.lower() in self.bots:
            await ctx.send("Ботика не трожь!")
            return

        asyncio.ensure_future(ctx.send(f"@{defender}, тебя вызвал на дуэль {attacker}!"
                                       f" Чтобы принять вызов пошли в чат !accept {attacker}"
                                       f", чтобы отказаться - !deny {attacker}."))

        attacker = attacker.lower()
        defender = defender.lower()
        self.attacks[defender].append(attacker)

    @commands.command(name='bite', aliases=['кусь'])
    async def bite(self, ctx: Context):
        attacker = ctx.author.display_name
        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !bite <кого>")
        defender = args[0].strip('@')
        last_bite = self.db.get(attacker, 31525200.0)
        now = datetime.datetime.now()

        last_bite = datetime.datetime.fromtimestamp(last_bite)
        if (now - last_bite).seconds < 90 and attacker != 'iarspider':
            await ctx.send("Не кусай так часто, @{0}! Дай моим челюстям отдохнуть!".format(attacker))
            return

        if not self.is_online(defender):
            await ctx.send('Кто такой или такая @' + defender + '? Я не буду кусать кого попало!')
            return

        self.db[attacker] = now.timestamp()

        if defender.lower() in self.bots:
            await ctx.timeout(ctx.author.name, 300, 'поКУСЬился на ботика')
            await ctx.send('@' + attacker + ' попытался укусить ботика. @' + attacker + ' SMOrc')
            return

        if defender.lower() == 'кусь':
            await ctx.timeout(ctx.author.name, 1)
            await ctx.send('@' + attacker + ' попытался сломать систему, но не смог BabyRage')

        if attacker.lower() == defender.lower():
            await ctx.send('@{0} укусил сам себя за жопь. Как, а главное - зачем он это сделал? Загадка...'.format(
                attacker))
            return

        prefix = u"нежно " if random.randint(1, 2) == 1 else "ласково "
        target = ""
        if defender.lower() == "prayda_alpha":
            target = u" за хвостик" if random.randint(1, 2) == 1 else " за ушко"

        if defender.lower() == "looputaps":
            target = u" за лапку в тапке"

        if defender.lower() == "babytigeronthesunflower":
            defender = attacker
            attacker = 'iarspider'
            prefix = ""
            target = ", ибо Тигру кусать нельзя!"

        if defender.lower() != "thetestmod":
            await ctx.send("По поручению {0} {1} кусаю @{2}{3}".format(attacker, prefix, defender, target))
        else:
            await ctx.send("По поручению {0} {1} потрогал @{2}".format(attacker, prefix, defender, target))

    @staticmethod
    def my_get_users(user_name):
        res = requests.get('https://api.twitch.tv/helix/users', params={'login': user_name},
                           headers={'Accept': 'application/vnd.twitchtv.v5+json',
                                    'Authorization': f'Bearer {twitch_chat_password}',
                                    'Client-ID': twitch_client_id_alt})
        res.raise_for_status()
        return res.json()['data'][0]

    @staticmethod
    async def my_get_stream(user_id) -> dict:
        while True:
            logger.info("Attempting to get stream...")
            try:
                res = requests.get('https://api.twitch.tv/helix/streams', params={'user_id': user_id},
                                   headers={'Accept': 'application/vnd.twitchtv.v5+json',
                                            'Authorization': f'Bearer {twitch_chat_password}',
                                            'Client-ID': twitch_client_id_alt})
                res.raise_for_status()
                stream = res.json()['data'][0]
            except IndexError:
                logger.info("Stream not detected yet")
                pass
            else:
                logger.info("Got stream")
                return stream

            await asyncio.sleep(60)

    @staticmethod
    def my_get_game(game_id):
        res = requests.get('https://api.twitch.tv/helix/games', params={'id': game_id},
                           headers={'Accept': 'application/vnd.twitchtv.v5+json',
                                    'Authorization': f'Bearer {twitch_chat_password}',
                                    'Client-ID': twitch_client_id_alt})

        return res.json()['data'][0]

    async def my_run_commercial(self, user_id, length=90):
        await self.my_get_stream(self.user_id)
        sess = twitch_api.get_session(twitch_client_id, twitch_client_secret, twitch_redirect_url)
        res = sess.post('https://api.twitch.tv/helix/channels/commercial',
                        data={'broadcaster_id': user_id, 'length': length},
                        headers={'Client-ID': twitch_client_id})
        try:
            res.raise_for_status()
        except requests.HTTPError:
            logger.error("Failed to run commercial:", res.json())

    def write_plusch(self):
        with codecs.open("plusch.txt", "w", "utf8") as f:
            f.write("Кого-то поплющило {0}...".format(numeral.get_plural(self.plusches, ('раз', 'раза', 'раз'))))

    @commands.command(name='plusch', aliases=['плющ'])
    async def plusch(self, ctx: Context):
        # if not self.is_mod(ctx.author.name) and ctx.author.name != 'iarspider':
        #     asyncio.ensure_future(ctx.send("No effect? I'm gonna need a bigger sword! (c)"))
        #     return

        who = " ".join(ctx.message.content.split()[1:])
        asyncio.ensure_future(ctx.send("Эк {0} поплющило...".format(who)))
        self.plusches += 1
        self.write_plusch()

    @commands.command(name='eplusch', aliases=['экипоплющило'])
    async def eplusch(self, ctx: Context):
        asyncio.ensure_future(ctx.send("Эки кого-то поплющило..."))
        self.plusches += 1
        self.write_plusch()

    @commands.command(name='bomb', aliases=['man', 'manual', 'руководство'])
    async def man(self, ctx: Context):
        await ctx.send("Руководство тут - https://bombmanual.com/ru/web/index.html")

    @commands.command(name='help', aliases=('помощь', 'справка'))
    async def help(self, ctx: Context):
        # asyncio.ensure_future(ctx.send(f"Никто тебе не поможет, {ctx.author.display_name}!"))
        asyncio.ensure_future(ctx.send(f"@{ctx.author.display_name} Справка по командам бота тут: "))

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
            author = params[0]
            count = int(params[1])

        # print(f"translit(): author {author}, count {count}")

        if self.last_messages.get(author, None) is None:
            asyncio.ensure_future(ctx.send(f"{author} ещё ничего не посылал!"))
            return

        if len(self.last_messages[author]) < count:
            count = len(self.last_messages[author])

        messages = copy.copy(self.last_messages[author])
        messages.reverse()

        res = ["Перевод окончен"]

        format_fields = ['', '', '']
        format_fields[0] = '' if count == 1 else str(count) + ' '
        format_fields[1] = 'ее' if count == 1 else 'их'
        format_fields[2] = {1: 'е', 2: 'я', 3: 'я', 4: 'я'}.get(count, 'й')

        for i in range(count):
            message = messages[i].translate(self.trans)
            res.append(f'{message}')

        res.append("Перевожу {0}последн{1} сообщени{2} @{author}:".format(*format_fields, author=author))

        for m in reversed(res):
            await ctx.send(m)

    async def mc_rip(self):
        try:
            with open(r"e:\MultiMC\instances\InSphere Deeper 0.8.3\.minecraft\LP World v3_deathcounter.txt") as f:
                self.deaths[0] = int(f.read())
                self.deaths[1] = self.deaths[0]
                self.write_rip()
        except OSError:
            return


twitch_bot: Optional[Bot] = None
discord_bot: Optional[discord.Client] = None
sio_client: Optional[socketio.AsyncClient] = None
sio_server: Optional[socketio.AsyncServer] = None
app: Optional[socketio.WSGIApp] = None

if __name__ == '__main__':
    import logging

    setup_logging("bot.log", color=True, debug=False, http_debug=False)

    # logger.setLevel(logging.DEBUG)
    # Run bot
    _loop = asyncio.get_event_loop()
    twitch_bot = Bot()

    invalid = list(twitchio.dataclasses.Messageable.__invalid__)
    invalid.remove('w')
    twitchio.dataclasses.Messageable.__invalid__ = tuple(invalid)

    sio_server = socketio.AsyncServer(async_mode='asgi',  # logger=True, engineio_logger=True,
                                      cors_allowed_origins='https://fr.iarazumov.com')
    app = socketio.ASGIApp(sio_server, socketio_path='/ws')
    config = uvicorn.Config(app, host='0.0.0.0', port=8081)
    server = uvicorn.Server(config)


    @sio_server.on('connect')
    async def on_ws_connected(sid, _):
        global twitch_bot, timer
        twitch_bot.dashboard = sid
        logger.info(f"Dashboard connected with id f{sid}")
        timer = asyncio.ensure_future(create_timer(1, dashboard_loop))


    @sio_server.on('disconnect')
    async def on_ws_disconnected(sid):
        global timer, twitch_bot
        if twitch_bot.dashboard == sid:
            logger.warning(f'Dashboard disconnected!')
            twitch_bot.dashboard = None
            timer.cancel()


    async def dashboard_loop():
        try:
            item = twitch_bot.queue.get_nowait()
            logger.info(f"send item {item}")
            # await websocket.send(simplejson.dumps(item))
            await sio_server.emit(item['action'], item['value'])
            logger.info("sent")
        except asyncio.QueueEmpty:
            # logger.info("get item failed")
            return
        except (ValueError, Exception):
            logger.exception(f'Emit failed!')


    asyncio.ensure_future(discord_bot.start(discord_bot_token))
    asyncio.ensure_future(twitch_bot.start())
    _loop.run_until_complete(server.serve())
    _loop.run_until_complete(discord_bot.close())
    _loop.stop()
