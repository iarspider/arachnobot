import asyncio
import codecs
import copy
import datetime
import pathlib
import random
from collections import deque, defaultdict
from typing import Union, Iterable, Optional

import colorlog
import discord
import pygame
import requests
import simplejson
import twitchio
from pytils import numeral
from obswebsocket import obsws
from obswebsocket import requests as obsws_requests
from requests.structures import CaseInsensitiveDict
import socketio
import uvicorn
from multiprocessing import Process
# For typing
from twitchio.dataclasses import Context, User
from twitchio.ext import commands

import streamlabs_api as api
import twitch_api
from config import *

try:
    import pywinauto
except ImportError as e:
    print("[WARN] PyWinAuto not found, sending keys will not work")
    pywinauto = None

import logging
import http.client as http_client

httpclient_logger = logging.getLogger("http.client")
discord_channel: discord.TextChannel
discord_role: discord.Role
logger: logging.Logger
proc: Process
timer: asyncio.Task
sl_client: socketio.AsyncClient


def setup_logging(logfile, debug, color, http_debug):
    global logger
    logger = logging.getLogger("bot")
    logger.propagate = False
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

    if not debug:
        logger.setLevel(logging.INFO)
        logging.getLogger('discord').setLevel(logging.INFO)
    else:
        logger.info("Debug logging is ON")
        logger.setLevel(logging.DEBUG)
        logging.getLogger('discord').setLevel(logging.DEBUG)

    if http_debug:
        http_client.HTTPConnection.debuglevel = 1

    ws_logger = logging.getLogger('websockets.server')
    ws_logger.setLevel(logging.DEBUG)
    ws_logger.addHandler(handler)
    ws_logger.addHandler(file_handler)


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

        try:
            # noinspection PyStatementEffect
            # noinspection PyUnresolvedReferences
            obsws_address
            # noinspection PyStatementEffect
            # noinspection PyUnresolvedReferences
            obsws_port
            # noinspection PyStatementEffect
            # noinspection PyUnresolvedReferences
            obsws_password
        except NameError:
            self.ws = None
        else:
            # noinspection PyUnresolvedReferences
            self.ws = obsws(obsws_address, int(obsws_port), obsws_password)
            self.ws.connect()
            self.aud_sources = self.ws.call(obsws_requests.GetSpecialSources())

        self.mods = set()
        self.subs = set()
        self.viewers = set()
        self.vips = set()

        self.db = {}
        self.streamlabs_oauth = api.get_streamlabs_session(streamlabs_client_id, streamlabs_client_secret,
                                                           streamlabs_redirect_uri)

        # self.streamlabs_socket = socketio.AsyncClient()
        self.user_id = -1

        self.htmlfile = r'e:\__Stream\web\example.html'
        self.vr = False
        self.plusches = 0
        self.deaths = [0, 0]

        self.rippers = ['iarspider', 'twistr_game', 'luciustenebrysflamos', 'phoenix__tv', 'wmuga', 'johnrico85']
        self.write_rip()

        self.last_post = CaseInsensitiveDict()
        self.post_timeout = 10 * 60
        self.post_price = {'regular': 20, 'vip': 10, 'mod': 0}

        self.vmod = None
        self.player = None
        self.vmod_active = False
        self.pubsub_nonce = ''

        s1 = "&qwertyuiop[]asdfghjkl;'zxcvbnm,./QWERTYUIOP{}ASDFGHJKL;\"ZXCVBNM<>?`~"
        s2 = "?йцукенгшщзхъфывапролджэячсмитьбю.ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,ёЁ"
        self.trans = str.maketrans(s1, s2)

        self.last_messages = CaseInsensitiveDict()
        self.attacks = defaultdict(list)
        self.bots = (self.nick, 'nightbot', 'pretzelrocks', 'streamlabs', 'commanderroot', 'electricallongboard')
        self.countdown_to = None
        self.dashboard = None
        self.queue = asyncio.Queue()

        if pywinauto:
            self.get_voicemod()
            self.get_player()

        self.setup_mixer()
        self.write_plusch()

        try:
            with open('rip.txt') as f:
                self.deaths[1] = int(f.read().strip())
        except (FileNotFoundError, TypeError, ValueError):
            pass

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

    async def deactivate_voicemod(self):
        await asyncio.sleep(60)
        self.get_voicemod()
        # self.get_discord()
        if self.vmod is not None:
            self.vmod_active = False
            self.vmod.type_keys('%{VK_DIVIDE}', set_foreground=False)  # random voice

            # if self.get_discord() is not None:
            self.vmod.type_keys('%{VK_NUMPAD0}', set_foreground=False)  # unmute

    async def activate_voicemod(self):
        while self.vmod_active:
            await asyncio.sleep(5)

        self.play_sound('vmod.mp3')

        self.get_voicemod()

        if self.vmod is not None:
            self.vmod.type_keys('%{VK_NUMPAD0}', set_foreground=False)  # mute
            self.vmod_active = True
            self.vmod.type_keys('%{VK_MULTIPLY}', set_foreground=False)  # random voice

        asyncio.ensure_future(self.deactivate_voicemod())

    def get_voicemod(self):
        if not pywinauto:
            return
        try:
            self.vmod = pywinauto.Application().connect(title="Voicemod Desktop").top_window().wrapper_object()
        except (pywinauto.findwindows.ElementNotFoundError, RuntimeError):
            logger.warning('Could not find VoiceMod Desktop window')

    def get_player(self):
        if not pywinauto:
            return
        try:
            self.player = pywinauto.Application().connect(title="Pretzel").top_window().wrapper_object()
        except (pywinauto.findwindows.ElementNotFoundError, RuntimeError):
            logger.warning('Could not find PretzelRocks window')

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
        logger.info(f"Send user {user.display_name} with status {status} and color {color}")

        await self.queue.put({'action': 'add', 'value': {'name': user.display_name, 'status': status,
                                                         'color': color, 'femme': femme}})

    async def send_viewer_left(self, user: User):
        if user.name.lower() in self.bots:
            return

        await self.queue.put({'action': 'remove', 'value': user.display_name})

    async def event_message(self, message):
        # if message.author.name.lower() not in self.viewers:
        await self.send_viewer_joined(message.author)

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
            d = datetime.datetime.now().timestamp()
            logger.error(f"Failed to get reward requestor! Saving reward in {d}.json")
            with open('{d}.json', 'w') as f:
                simplejson.dump(reward, f)
            requestor = 'Unknown'

        logger.debug("Reward:", reward)
        logger.debug("Key:", reward_key)
        logger.debug("Prompt:", prompt)

        if reward_key == "Смена голоса на 1 минуту".replace(' ', ''):
            asyncio.ensure_future(self.activate_voicemod())

        if reward_key == "Обнять стримера".replace(' ', ''):
            await self.queue.put({'type': 'event', 'value': {'type': 'hugs', 'from': requestor}})

        if reward_key == "Стримлер! Не горбись!".replace(' ', ''):
            await self.queue.put({'type': 'event', 'value': {'type': 'sit', 'from': requestor}})

        if reward_key == "Добавить упорину".replace(' ', ''):
            await self.queue.put({'type': 'event', 'value': {'type': 'fun', 'from': requestor}})

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

    @commands.command(name='setup')
    async def setup(self, ctx: Context):
        if not self.check_sender(ctx, 'iarspider'):
            return

        if not self.ws:
            return

        res: obsws_requests.GetStreamingStatus = self.ws.call(obsws_requests.GetStreamingStatus())
        if res.getStreaming():
            logger.error('Already streaming!')
            return

        asyncio.ensure_future(ctx.send('К стриму готов!'))
        self.ws.call(obsws_requests.SetCurrentProfile('Regular games'))
        self.ws.call(obsws_requests.SetCurrentSceneCollection('Twitch'))

    @commands.command(name='countdown', aliases=['preroll', 'cd', 'pr', 'св', 'зк'])
    async def countdown(self, ctx: Context):
        def write_countdown_html():
            args = ctx.message.content.split()[1:]
            parts = tuple(int(x) for x in args[0].split(':'))
            if len(parts) == 2:
                m, s = parts
                # noinspection PyShadowingNames
                delta = datetime.timedelta(minutes=m, seconds=s)
                dt = datetime.datetime.now() + delta
            elif len(parts) == 3:
                h, m, s = parts
                dt = datetime.datetime.now().replace(hour=h, minute=m, second=s)
            else:
                logger.error("Invalid call to countdown: {0}".format(args[0]))
                return

            self.countdown_to = dt

            with codecs.open(self.htmlfile.replace('html', 'template'), encoding='UTF-8') as f:
                lines = f.read()

            lines = lines.replace('@@date@@', dt.isoformat())
            with codecs.open(self.htmlfile, 'w', encoding='UTF-8') as f:
                f.write(lines)

        if not self.check_sender(ctx, 'iarspider'):
            return

        if not self.ws:
            return

        res: obsws_requests.GetStreamingStatus = self.ws.call(obsws_requests.GetStreamingStatus())
        if res.getStreaming():
            logger.error('Already streaming!')
            return

        write_countdown_html()

        self.ws.call(obsws_requests.DisableStudioMode())

        # Refresh countdown
        self.ws.call(obsws_requests.SetCurrentScene('Starting'))

        try:
            self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), True))
        except KeyError:
            logger.warning("[WARN] Can't mute mic-2, please check!")
        self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic1(), True))

        self.ws.call(obsws_requests.EnableStudioMode())

        self.ws.call(obsws_requests.StartStopStreaming())
        self.get_player()
        if self.player is not None:
            self.player.type_keys('+%P', set_foreground=False)  # Pause

        asyncio.ensure_future(ctx.send('Начат обратный отсчёт до {0}!'.format(self.countdown_to.strftime('%X'))))
        asyncio.ensure_future(self.my_run_commercial(self.user_id))

        if discord_bot is not None and discord_channel is not None:
            stream = await self.my_get_stream(self.user_id)
            game = self.my_get_game(stream['game_id'])
            delta = self.countdown_to - datetime.datetime.now()
            delta_m = delta.seconds // 60
            delta_text = numeral.get_plural(delta_m, ('минута', 'минуты', 'минут'))
            announcement = f"<@&{discord_role.id}> Паучок запустил стрим \"{stream['title']}\" " \
                           f"по игре \"{game['name']}\"! У вас есть примерно {delta_text} чтобы" \
                           " открыть стрим - <https://twitch.tv/iarspider>!"
            await discord_channel.send(announcement)
            logger.info("Discord notification sent!")

    # noinspection PyUnusedLocal
    @commands.command(name='end', aliases=['fin', 'конец', 'credits'])
    async def end(self, ctx: Context):
        self.ws.call(obsws_requests.SetCurrentScene('End'))
        try:
            api.roll_credits(self.streamlabs_oauth)
        except requests.HTTPError as exc:
            logger.error("Can't roll credits! " + str(exc))
            pass

    @commands.command(name='vr')
    async def toggle_vr(self, ctx: Context):
        if not self.check_sender(ctx, 'iarspider'):
            return

        self.vr = not self.vr
        asyncio.ensure_future(ctx.send('VR-режим {0}'.format('включен' if self.vr else 'выключен')))

    # async def event_raw_data(self, data):
    #     lines = data.splitlines(keepends=False)
    #     for line in lines:
    #         print('>', line)

    # Commands use a different decorator
    # @commands.command(name='test')
    # async def test(self, ctx: Context):
    #     await ctx.send(f'Hello {ctx.author.name}!')

    @commands.command(name='roll', aliases=['dice', 'кинь'])
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
            await ctx.send("Выкинул: {}={}".format("+".join(str(x) for x in rolls), roll_sum))
        elif len(rolls) == 1:
            await ctx.send("Выкинул: {}".format(roll_sum))

    @commands.command(name='deny', aliases=('no', 'pass'))
    async def deny_attack(self, ctx: Context):
        defender = ctx.author.name

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
        defender = ctx.author.name

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
        attacker = ctx.author.name
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
        attacker = ctx.author.name
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

    @commands.command(name='bugs', aliases=['баги'])
    async def bugs(self, ctx: Context):
        """
            Показывает текущее число "багов" (очков лояльности)

            %%bugs
        """
        user = ctx.author.name
        # print("Requesting points for", user)
        try:
            res = api.get_points(self.streamlabs_oauth, user)
            # print(res)
            # res = res['points']
        except requests.HTTPError:
            res = 0

        await ctx.send(f'@{user} Набрано багов: {res}')
        # await ctx.author.send('Набрано багов: {0}'.format(res))
        # await ctx.send('@' + user + ', ответил в ЛС')

    def switch_to(self, scene: str):
        res = self.ws.call(obsws_requests.GetStudioModeStatus())
        if res.getStudioMode():
            self.ws.call(obsws_requests.SetPreviewScene(scene))
            self.ws.call(obsws_requests.TransitionToProgram('Stinger'))
        else:
            self.ws.call(obsws_requests.SetCurrentScene(scene))

    @commands.command(name='pause', aliases=('break',))
    async def pause(self, ctx: Context):
        """
            Запускает перерыв

            %%pause
        """
        if not self.check_sender(ctx, 'iarspider'):
            asyncio.ensure_future(ctx.send('/timeout ' + ctx.author.name + ' 1'))
            return

        self.get_player()
        if self.player is not None:
            self.player.type_keys('+%P', set_foreground=False)  # Pause

        if self.ws is not None:
            self.switch_to('Paused')
            if self.vr:
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), True))
            else:
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic1(), True))

        # self.get_chatters()
        asyncio.ensure_future(ctx.send('Начать перепись населения!'))
        asyncio.ensure_future(self.my_run_commercial(self.user_id, 60))

    @commands.command(name='start')
    async def start_(self, ctx: Context):
        """
            Начало трансляции. Аналог resume но без подсчёта зрителей

            %%start
        """
        if not self.check_sender(ctx, 'iarspider'):
            asyncio.ensure_future(ctx.send('/timeout ' + ctx.author.name + ' 1'))
            return

        self.get_player()
        if self.player is not None:
            self.player.type_keys('+%P', set_foreground=False)  # Pause

        if self.ws is not None:
            if self.vr:
                self.switch_to('VR Game')
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), False))
            else:
                self.switch_to('Game')
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic1(), False))

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

    @commands.command(name='resume')
    async def resume(self, ctx: Context):
        """
            Отменяет перерыв

            %%resume
        """
        if not self.check_sender(ctx, 'iarspider'):
            asyncio.ensure_future(ctx.send('/timeout ' + ctx.author.name + ' 1'))
            return

        self.get_player()
        if self.player is not None:
            self.player.type_keys('+%P', set_foreground=False)  # Pause

        if self.ws is not None:
            if self.vr:
                self.switch_to('VR Game')
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), False))
            else:
                self.switch_to('Game')
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic1(), False))

        try:
            res = await self.my_get_stream(self.user_id)
            viewers = numeral.get_plural(res['viewer_count'], ('зритель', 'зрителя', 'зрителей'))
            asyncio.ensure_future(
                ctx.send(
                    'Перепись населения завершена успешно! Население стрима составляет {0}'.format(viewers)))
        except (KeyError, TypeError) as exc:
            asyncio.ensure_future(ctx.send('Перепись населения не удалась :('))
            logger.error(str(exc))

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

    def write_rip(self):
        with codecs.open('rip_display.txt', 'w', 'utf8') as f:
            f.write(u'☠: {0} ({1})'.format(*self.deaths))
            # f.write(u'☠: {1}'.format(*self.deaths))

        with open('rip.txt', 'w') as f:
            f.write(str(self.deaths[1]))

    async def do_rip(self, ctx: Context, reason: Optional[str] = None):
        if not (self.is_mod(ctx.author.name) or self.is_vip(
                ctx.author.name) or ctx.author.name.lower() in self.rippers):
            asyncio.ensure_future(ctx.send("Эту кнопку не трожь!"))
            return

        self.deaths[0] += 1
        self.deaths[1] += 1

        self.write_rip()
        if reason:
            await ctx.send(reason)

        asyncio.ensure_future(ctx.send("riPepperonis {0}".format(*self.deaths)))

    @commands.command(name='rip', aliases=("смерть",))
    async def rip(self, ctx: Context):
        """
            Счётчик смертей

            %% rip
        """
        await self.do_rip(ctx)

    @commands.command(name='unrip')
    async def unrip(self, ctx: Context):
        """
        Отмена смерти
        """
        if not self.check_sender(ctx, 'iarspider'):
            return

        self.deaths[0] -= 1
        self.deaths[1] -= 1

        self.write_rip()

        asyncio.ensure_future(ctx.send("MercyWing1 PinkMercy MercyWing2".format(*self.deaths)))

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
        self.rippers.append(args[0])

        asyncio.ensure_future(ctx.send("{0} TwitchVotes ".format(args[0])))

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

    @commands.command(name='post', aliases=['почта'])
    async def post(self, ctx: Context):
        last_post = self.last_post.get(ctx.author.name, None)
        if last_post is not None:
            delta = datetime.datetime.now() - last_post
            if delta.seconds < 10 * 60:
                asyncio.ensure_future(ctx.send("Не надо так часто отправлять почту!"))
                return

        if self.is_mod(ctx.author.name):
            price = self.post_price['mod']
        elif self.is_vip(ctx.author.name):
            price = self.post_price['vip']
        else:
            price = self.post_price['regular']

        points = api.get_points(self.streamlabs_oauth, ctx.author.name)

        if points < price:
            asyncio.ensure_future(ctx.send(f"У вас недостаточно багов для отправки почты - вам нужно минимум "
                                           f" {price}. Проверить баги: !баги"))
        else:
            res = api.sub_points(self.streamlabs_oauth, ctx.author.name, price)
            logger.debug(res)
            self.play_sound("pochta.mp3")

    @commands.command(name='sos', aliases=['alarm'])
    async def sos(self, ctx: Context):
        if not (self.is_mod(ctx.author.name) or ctx.author.name.lower() == 'iarspider'):
            asyncio.ensure_future(ctx.send("Эта кнопочка - не для тебя. Руки убрал, ЖИВО!"))
            return

        self.play_sound("matmatmat.mp3")

    @commands.command(name='vmod')
    async def vmod(self, ctx: Context):
        if ctx.author.name.lower() != 'iarspider':
            return

        await self.activate_voicemod()

    @commands.command(name='help', aliases=('помощь', 'справка'))
    async def help(self, ctx: Context):
        asyncio.ensure_future(ctx.send(f"Никто тебе не поможет, {ctx.author.name}!"))

    @commands.command(name='spin')
    async def spin(self, ctx: Context):
        if ctx.author.name.lower() != 'iarspider':
            return

        # points = api.get_points(self.streamlabs_oauth, ctx.author.name)
        httpclient_logging_patch()
        requests.post('https://streamlabs.com/api/v1.0/wheel/spin',
                      data={'access_token': self.streamlabs_oauth.access_token})
        httpclient_logging_patch(logging.INFO)

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


async def on_ready():
    global discord_channel, discord_role
    # print("Discord | on_ready")
    guild = discord.utils.find(lambda g: g.name == discord_guild_name, discord_bot.guilds)

    if guild is None:
        raise RuntimeError(f"Failed to join Discord guild {discord_guild_name}!")

    discord_channel = discord.utils.find(lambda c: c.name == discord_channel_name, guild.channels)
    if discord_channel is None:
        raise RuntimeError(f"Failed to join Discord channel {discord_channel_name}!")

    logger.info(f"Ready | {discord_bot.user} @ {guild.name}")

    discord_role = discord.utils.find(lambda r: r.name == discord_role_name, guild.roles)
    if discord_role is None:
        raise RuntimeError(f"No role {discord_role_name} in guild {discord_guild_name}!")


if __name__ == '__main__':
    import logging

    setup_logging("bot.log", color=True, debug=False, http_debug=False)

    # logger.setLevel(logging.DEBUG)
    # Run bot
    _loop = asyncio.get_event_loop()
    twitch_bot = Bot()
    discord_bot = discord.Client()
    discord_bot.event(on_ready)

    invalid = list(twitchio.dataclasses.Messageable.__invalid__)
    invalid.remove('w')
    twitchio.dataclasses.Messageable.__invalid__ = tuple(invalid)

    # noinspection PyUnboundLocalVariable
    sl_client = socketio.AsyncClient(logger=logger)


    @sl_client.on('connect')
    async def sl_client_connected():
        logger.info('SL client connected!')


    @sl_client.on('disconnect')
    async def sl_client_disconnected():
        logger.warning('SL client disconnected!')


    # @sl_client.on('message')
    # async def sl_client_message(data):
    #     logger.info(f'SL message: {data}')

    @sl_client.on('event')
    async def sl_client_event(data):
        logger.info(f'SL event: {data}')
        pick_keys = []
        if data['type'] == 'donation':
            pick_keys.extend(('from', 'message', 'formatted_amount'))
        elif data['type'] == 'follow':
            pick_keys.extend(('name',))
        elif data['type'] == 'subscription':
            pick_keys.extend(('name', 'months', 'message', 'sub_plan'))
        elif data['type'] == 'resub':
            pick_keys.extend(('name', 'months', 'streak_months', 'message', 'sub_plan'))
        elif data['type'] == 'host':
            pick_keys.extend(('name', 'viewers'))
        elif data['type'] == 'bits':
            pick_keys.extend(('name', 'amount', 'message'))
        elif data['type'] == 'raid':
            pick_keys.extend(('name', 'raiders'))
        elif data['type'] == 'alertPlaying':
            return
        else:
            logger.warning(f'Unknown SL event type: {data["type"]}')
            return

        def copy_keys(from_, to_, keys_):
            for k_ in keys_:
                if k_ in from_:
                    to_[k_] = from_[k_]
                else:
                    logger.warning(f'Event {data["type"]} missing key {k_}')
                    to_[k_] = 'UNKNOWN'

        message = {'action': 'event', 'value': {'type': data['type']}}
        for k in pick_keys:
            if isinstance(data['message'], list):
                for msg in data['message']:
                    copy_keys(msg, message['value'], pick_keys)
            else:
                copy_keys(data['message'], message['value'], pick_keys)

        await twitch_bot.queue.put(message)


    token = api.get_socket_token(twitch_bot.streamlabs_oauth)
    asyncio.ensure_future(sl_client.connect(f'https://sockets.streamlabs.com?token={token}'))
    # # noinspection PyUnusedLocal
    # async def on_ws_connected(websocket, path):
    #     logger.info(f"connected! websocket is f{websocket}")
    #     try:
    #         global twitch_bot
    #         twitch_bot.dashboard = websocket
    #         while True:
    #             try:
    #                 item = twitch_bot.queue.get_nowait()
    #                 logger.info(f"send item {item}")
    #                 await websocket.send(simplejson.dumps(item))
    #                 logger.info("sent")
    #             except asyncio.QueueEmpty:
    #                 # logger.info("get item failed")
    #                 await asyncio.sleep(1)
    #     except Exception as ex:
    #         logger.error('on_ws_connected failed: ' + str(ex))

    # start_server = websockets.serve(on_ws_connected, "0.0.0.0", 8081)
    # asyncio.ensure_future(start_server, loop=_loop)

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
    # twitch_bot.run()
    _loop.run_until_complete(server.serve())
    _loop.run_until_complete(discord_bot.close())
    _loop.stop()
    # _loop.run_forever()
    #
    # data = {'type': 'donation', 'message': [
    #     {'priority': 10, '_id': '5f8b50e98d327', 'from': 'IARSpider', 'fromId': '', 'to': 'IARSpider',
    #      'message': 'test', 'amount': 182.29372533261795, 'currency': 'RUB',
    #      'payload': {'id': 139660587, 'name': 'IARSpider', 'amount': 182.29372533261795,
    #                  'formatted_amount': 'RUB182.29', 'formattedAmount': 'RUB182.29', 'message': 'test',
    #                  'currency': 'RUB', 'emotes': '', 'iconClassName': 'fab paypal', 'to': {'name': 'IARSpider'},
    #                  'from': 'IARSpider', 'from_user_id': 567482, 'donation_currency': 'EUR', 'source': 'paypal',
    #                  '_id': '348f90f1504bdefc4caeba4bc9f4f122', 'priority': 10}, 'formattedAmount': 'RUB182.29',
    #      'gif': None, 'facemask': None, 'mask_name': None, 'mask_rarity': None, 'pro': None, 'pro_extras': None,
    #    'senderId': 567482, 'emotes': None, 'wishListItem': None, 'name': 'IARSpider', 'isTest': False, 'repeat': True,
    #      'alert_status': 1, 'createdAt': '2020-10-17 20:15:37', 'type': 'donation', 'source': '',
    #      'donation_id': 139660587, 'legacyHash': 'donation:IARSpider:test:182',
    #      'hash': 'donation:IARSpider:test:182:139660587', 'read': False, 'donationCurrency': 'EUR', 'wotcCode': None,
    #      'crate_item': None, 'attachments': [], 'clippingEnabled': True, 'charity': False, 'forceShow': False,
    #      'success': False, 'forceRepeat': True, 'formatted_amount': 'RUB182.29'}], 'for': 'streamlabs',
    #         'event_id': 'evt_5f3a05e3a2cc8f83de5fc370ab81b418'}
    # data = {'type': 'follow', 'message': [
    #     {'name': 'IARSpider', 'isTest': True, '_id': '9352d1aa1d906f58ae03f9b2c24ea914', 'priority': 10}],
    #         'for': 'twitch_account', 'event_id': 'evt_6e26e104fcdd177b7aaae63a713fef23'}
    # data = {'type': 'subscription', 'message': [
    #     {'name': 'IARSpider', 'isTest': True, 'months': 1, 'message': 'This is a test', 'emotes': None,
    #      'sub_plan': '1000', '_id': '5795dadcad7dcc72118f0e6341dc2d9d', 'priority': 10}], 'for': 'twitch_account',
    #         'event_id': 'evt_b54938504b840037d859230f78b00b43'}
    # data = {'type': 'resub', 'message': [
    #     {'name': 'IARSpider', 'isTest': True, 'months': 8, 'streak_months': 4, 'message': 'This is a test',
    #     'emotes': None, 'sub_plan': '1000', 'amount': 83, '_id': '6a0b7fea57cea9f0ba2d042f70262e9b', 'priority': 10}],
    #         'for': 'twitch_account', 'event_id': 'evt_2ec7e5362bc09b718da51ca272b9cc6c'}
    # data = {'type': 'host', 'message': [
    #     {'name': 'IARSpider', 'isTest': True, 'viewers': 491, '_id': 'b4d53a67175b33b695cc9ea543aa279f',
    #      'priority': 10}], 'for': 'twitch_account', 'event_id': 'evt_7ca1ded5b02edc82614998b9ceb54b20'}
    # data = {'type': 'bits', 'message': [
    #     {'name': 'IARSpider', 'isTest': True, 'amount': '1', 'message': 'cheer1 this is a test bit alert',
    #      'currency': 'RUB', '_id': 'ac935c1ccd3ff8e2bf3430f5feeaa4ad', 'priority': 10}], 'for': 'twitch_account',
    #         'event_id': 'evt_210f4638a5a82b20a3bcd7ffb0f79a7b'}
    # data = {'type': 'raid', 'message': [
    #     {'name': 'IARSpider', 'isTest': True, 'raiders': 927, '_id': '98d84f5070c7457d5ef2b57c11b42883',
    #      'priority': 10}], 'for': 'twitch_account', 'event_id': 'evt_35b84e788985457d2688fc5e824aa065'}
    # data = {'type': 'subscription', 'message': [
    #     {'priority': 10, '_id': '5f8c454af356b', 'from': 'barabusik022', 'from_display_name': 'Barabusik022',
    #      'emotes': None, 'months': 1, 'streak_months': None, 'message': '', 'payload': [], 'name': 'barabusik022',
    #      'display_name': 'Barabusik022', 'subPlan': '1000', 'sub_plan': '1000', 'subscriber_twitch_id': 137911875,
    #    'gifter': 'nickopolidiss', 'gifter_display_name': 'Nickopolidiss', 'count': 1, 'repeat': True, 'isTest': False,
    #      'createdAt': '2020-10-18 13:38:18', 'platform': 'twitch_account', 'planName': '', 'type': 'subscription',
    #      'hash': 'subscription:barabusik022:', 'read': False, 'amount': None, 'membershipLevel': None,
    #      'membershipLevelName': None, 'massSubGiftChildAlerts': [], 'isSubgiftExpanded': True,
    #      'benefit_end_month': None, 'historical': True, 'forceShow': False, 'success': False, 'forceRepeat': False}],
    #         'for': 'twitch_account', 'event_id': 'evt_42b3a8e30aa06d763f430d08c794de27'}
