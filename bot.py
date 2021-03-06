import asyncio
import datetime
import pathlib
import random
from collections import defaultdict, deque
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
from requests.structures import CaseInsensitiveDict
# For typing
from twitchio.dataclasses import Context, User
from twitchio.ext import commands

import twitch_api
from aio_timer import Timer
from config import *

import logging
import http.client as http_client


httpclient_logger = logging.getLogger("http.client")
logger: logging.Logger
proc: Process
dashboard_timer: Timer
sl_client: socketio.AsyncClient


def setup_logging(logfile, debug, color, http_debug):
    global logger
    logger = logging.getLogger('arachnobot')
    logger.propagate = False
    ws_logger = logging.getLogger('websockets.server')
    uvicorn_logger = logging.getLogger('uvicorn.error')
    obsws_logger = logging.getLogger('obswebsocket.core')

    bot_handler = logging.StreamHandler()
    if color:
        bot_handler.setFormatter(
            colorlog.ColoredFormatter(
                '%(asctime)s %(log_color)s[%(name)s:%(levelname)s:%(lineno)s]%(reset)s %(message)s',
                datefmt='%H:%M:%S'))
    else:
        bot_handler.setFormatter(
            logging.Formatter(fmt="%(asctime)s [%(name)s:%(levelname)s:%(lineno)s] %(message)s",
                              datefmt='%H:%M:%S'))

    file_handler = logging.FileHandler(logfile, "w")
    file_handler.setFormatter(
        logging.Formatter(fmt="%(asctime)s [%(name)s:%(levelname)s:%(lineno)s] %(message)s"))

    logger.addHandler(bot_handler)
    logger.addHandler(file_handler)

    ws_logger.addHandler(bot_handler)
    ws_logger.addHandler(file_handler)

    uvicorn_logger.addHandler(bot_handler)
    uvicorn_logger.addHandler(file_handler)

    obsws_logger.addHandler(bot_handler)
    obsws_logger.addHandler(file_handler)

    if not debug:
        logger.setLevel(logging.INFO)
        logging.getLogger('discord').setLevel(logging.INFO)
        ws_logger.setLevel(logging.WARN)
        uvicorn_logger.setLevel(logging.WARN)
        obsws_logger.setLevel(logging.WARN)
    else:
        logger.info("Debug logging is ON")
        logger.setLevel(logging.DEBUG)
        logging.getLogger('discord').setLevel(logging.DEBUG)
        ws_logger.setLevel(logging.DEBUG)
        uvicorn_logger.setLevel(logging.DEBUG)
        obsws_logger.setLevel(logging.DEBUG)

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


class Bot(commands.Bot):
    def __init__(self, loop: asyncio.AbstractEventLoop = None):
        super().__init__(irc_token='oauth:' + twitch_chat_password,
                         client_id=twitch_client_id, nick='arachnobot',
                         prefix='!',
                         initial_channels=['#iarspider'],
                         loop=loop)

        self.logger = logger

        self.viewers = CaseInsensitiveDict()

        self.db = {}

        self.user_id = -1

        self.vmod = None
        self.vmod_active = False
        self.pubsub_nonce = ''

        self.attacks = defaultdict(list)
        self.bots = (self.nick, 'nightbot', 'pretzelrocks', 'streamlabs', 'commanderroot', 'electricallongboard')
        self.countdown_to: Optional[datetime.datetime] = None  # ! keep this here !
        self.last_messages = CaseInsensitiveDict()  # ! keep this here !

        self.dashboard = None
        self.queue = asyncio.Queue()

        self.setup_mixer()
        self.started = False

    # noinspection PyMethodMayBeStatic
    def is_vip(self, user: User):
        return user.badges.get('vip', 0) == 1

    def add_user(self, user: User):
        name = user.name.lower()
        display_name = user.display_name.lower()
        if name not in self.viewers:
            self.viewers[name] = user

        if display_name not in self.viewers:
            self.viewers[display_name] = user

    async def start(self):
        self.logger.info("Starting bot!")
        if self.started:
            self.logger.error("Already started!")
            raise RuntimeError()

        self.started = True
        await super(Bot, self).start()

    # Fill in missing stuff
    def get_cog(self, name):
        try:
            return self.cogs[name]
        except KeyError:
            logger.error(f"No such cog: {name}, known cogs: {','.join(self.cogs.keys())}")
            return None

    # twitchio, I can and will handle pubsub
    async def event_pubsub(self, data):
        pass

    async def event_ready(self):
        self.logger.info(f'Ready | {self.nick}')
        self.user_id = self.my_get_users(self.initial_channels[0].lstrip('#'))['id']
        sess = twitch_api.get_session(twitch_client_id, twitch_client_secret, twitch_redirect_url)
        self.pubsub_nonce = await self.pubsub_subscribe(sess.token["access_token"],
                                                        'channel-points-channel-v1.{0}'.format(self.user_id))
        # socket_token = api.get_socket_token(self.streamlabs_oauth)
        # self.streamlabs_socket.on('message', self.sl_event)
        # self.streamlabs_socket.on('connect', self.sl_connected)
        #

    async def event_message(self, message):
        # if message.author.name.lower() not in self.viewers:
        await self.send_viewer_joined(message.author)

        self.logger.debug("JOIN sent")
        #
        # self.viewers.add(message.author.name.lower())
        # if message.author.is_mod:
        #     self.mods.add(message.author.name.lower())
        # if message.author.is_subscriber:
        #     self.subs.add(message.author.name.lower())
        #
        # if message.author.badges.get('vip', 0) == 1:
        #     self.vips.add(message.author.name.lower())
        self.add_user(message.author)

        if message.author.name not in self.last_messages:
            self.last_messages[message.author.name] = deque(maxlen=10)

        if message.author.name.lower() not in self.bots:
            if not message.content.startswith('!'):
                self.last_messages[message.author.name].append(message.content)
                self.logger.debug(f"Updated last messages for {message.author.name}, " +
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

        self.logger.debug("handle_command start: %s", message)
        await self.handle_commands(message)
        self.logger.debug("handle_command end: %s", message)

    # async def event_join(self, user):
    #     if user.name.lower() not in self.viewers:
    #         # await self.send_viewer_joined(user.name)
    #         # self.viewers.add(user:wq.name.lower())
    #         logger.info(f"User {user.name} joined! tags {user.tags}, badges {user.badges}")

    async def event_part(self, user: User):
        if user.name.lower() in self.viewers:
            await asyncio.ensure_future(self.send_viewer_left(user))

        try:
            del self.viewers[user.name.lower()]
        except KeyError:
            pass

        try:
            del self.viewers[user.display_name.lower()]
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
            self.logger.error(f"Failed to get reward requestor! Saving reward in {d}.json")
            with open(f'{d}.json', 'w', encoding='utf-8') as f:
                simplejson.dump(data, f)
            requestor = 'Unknown'

        self.logger.debug("Reward:", reward)
        self.logger.debug("Key:", reward_key)
        self.logger.debug("Prompt:", prompt)

        if reward_key == "Смена голоса на 1 минуту".replace(' ', ''):
            vmod = self.get_cog('VMcog')
            asyncio.ensure_future(vmod.activate_voicemod())

        if reward_key == "Обнять стримера".replace(' ', ''):
            self.logger.debug(f"Queued redepmtion: hugs, {requestor}")
            await self.queue.put({'action': 'event', 'value': {'type': 'hugs', 'from': requestor}})

        if reward_key == "Стримлер! Не горбись!".replace(' ', ''):
            self.logger.debug(f"Queued redepmtion: sit, {requestor}")
            await self.queue.put({'action': 'event', 'value': {'type': 'sit', 'from': requestor}})

        if reward_key == "Добавить упорину".replace(' ', ''):
            self.logger.debug(f"Queued redepmtion: fun, {requestor}")
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
        logger.debug("play sound %s", soundfile)
        pygame.mixer.music.load(str(soundfile))
        pygame.mixer.music.play()

    async def send_viewer_joined(self, user: User):
        if user.name.lower() in self.bots:
            return

        femme = (user.name.lower() in twitch_ladies or user.display_name.lower() in twitch_ladies)

        if user.is_subscriber:
            status = 'spider'
        elif user.is_mod:
            status = 'hammer'
        elif self.is_vip(user):
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

    @staticmethod
    def check_sender(ctx: Context, users: Union[str, Iterable[str]]):
        if isinstance(users, str):
            users = (users,)

        return ctx.author.name in users

    # async def event_raw_data(self, data):
    #     lines = data.splitlines(keepends=False)
    #     for line in lines:
    #         print('>', line)

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

    @commands.command(name='bite', aliases=['кусь'])
    async def bite(self, ctx: Context):
        attacker = ctx.author.name.lower()
        attacker_name = ctx.author.display_name
        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            await ctx.send("Использование: !bite <кого>")
            return
        defender = args[0].strip('@')
        last_bite = self.db.get(attacker, 31525200.0)
        now = datetime.datetime.now()

        last_bite = datetime.datetime.fromtimestamp(last_bite)
        if (now - last_bite).seconds < 15 and attacker != 'iarspider':
            await ctx.send("Не кусай так часто, @{0}! Дай моим челюстям отдохнуть!".format(attacker))
            return

        if defender.lower() in self.bots:
            await ctx.timeout(ctx.author.name, 300, 'поКУСЬился на ботика')
            await ctx.send(f'@{ctx.author.display_name} попытался укусить ботика. @{ctx.author.display_name} SMOrc')
            return

        if defender.lower() == 'кусь':
            await ctx.timeout(ctx.author.name, 1)
            await ctx.send(f'@{ctx.author.display_name} попытался сломать систему, но не смог BabyRage')

        if attacker.lower() == defender.lower():
            await ctx.send(f'@{ctx.author.display_name} укусил сам себя за жопь. Как, а главное - зачем он это сделал? '
                           f'Загадка...')
            return

        if defender not in self.viewers:
            await ctx.send('Кто такой или такая @' + defender + '? Я не буду кусать кого попало!')
            return

        try:
            defender_name = self.viewers[defender].display_name
        except KeyError:
            defender_name = defender

        self.db[attacker] = now.timestamp()

        prefix = random.choice((u"нежно ", u"ласково "))
        target = ""
        if defender.lower() == "prayda_alpha":
            target = random.choice((u" за хвостик", u" за ушко"))

        if defender.lower() == "looputaps":
            target = u" за лапку в тапке"

        if defender.lower() in twitch_no_bite:
            if defender.lower() == 'babytigeronthesunflower':
                old_defender = 'Тигру'
            else:
                old_defender = defender

            defender_name = self.viewers[attacker].display_name

            attacker_name = 'стримлера'
            prefix = ""
            with_ = random.choice(("некроёжиком с тентаклями вместо колючек", "зомбокувалдой", "некочайником"))
            target = " {0}, ибо {1} кусать нельзя!".format(with_, old_defender)

        if defender.lower() == "thetestmod":
            await ctx.send(
                "По поручению {0} {1} потрогал @{2} фирменным паучьим трогом".format(ctx.author.display_name, prefix,
                                                                                     defender_name,
                                                                                     target))
        else:
            await ctx.send("По поручению {0} {1} кусаю @{2}{3}".format(attacker_name, prefix, defender_name, target))

    @staticmethod
    def my_get_users(user_name):
        res = requests.get('https://api.twitch.tv/helix/users', params={'login': user_name},
                           headers={'Accept': 'application/vnd.twitchtv.v5+json',
                                    'Authorization': f'Bearer {twitch_chat_password}',
                                    'Client-ID': twitch_client_id_alt})
        res.raise_for_status()
        ress = res.json()['data'][0]
        res.close()
        return ress

    @staticmethod
    async def my_get_stream(user_id) -> dict:
        while True:
            logger.info("Attempting to get stream...")
            res = requests.get('https://api.twitch.tv/helix/streams', params={'user_id': user_id},
                               headers={'Accept': 'application/vnd.twitchtv.v5+json',
                                        'Authorization': f'Bearer {twitch_chat_password}',
                                        'Client-ID': twitch_client_id_alt})

            try:
                res.raise_for_status()
                stream = res.json()['data'][0]
            except IndexError:
                logger.info("Stream not detected yet")
                pass
            except requests.RequestException as e:
                logger.error(f"Request to /helix/streams failed: {str(e)}")
            else:
                logger.info("Got stream")
                res.close()
                return stream

            res.close()
            await asyncio.sleep(60)

    @staticmethod
    def my_get_game(game_id):
        res = requests.get('https://api.twitch.tv/helix/games', params={'id': game_id},
                           headers={'Accept': 'application/vnd.twitchtv.v5+json',
                                    'Authorization': f'Bearer {twitch_chat_password}',
                                    'Client-ID': twitch_client_id_alt})

        ress = res.json()['data'][0]
        res.close()
        return ress

    async def my_run_commercial(self, user_id, length=90):
        await self.my_get_stream(self.user_id)
        sess = twitch_api.get_session(twitch_client_id, twitch_client_secret, twitch_redirect_url)
        res = sess.post('https://api.twitch.tv/helix/channels/commercial',
                        data={'broadcaster_id': user_id, 'length': length},
                        headers={'Client-ID': twitch_client_id})
        try:
            res.raise_for_status()
            res.close()
        except requests.HTTPError:
            logger.error("Failed to run commercial:", res.json())

    @commands.command(name='ping', aliases=['зштп'])
    async def cmd_ping(self, ctx: Context):
        if not self.check_sender(ctx, 'iarspider'):
            return

        await ctx.send('Yeth, Mathter?')

    @commands.command(name='bomb', aliases=['man', 'manual', 'руководство'])
    async def man(self, ctx: Context):
        await ctx.send("Руководство тут - https://bombmanual.com/ru/web/index.html")

    @commands.command(name='help', aliases=('помощь', 'справка'))
    async def help(self, ctx: Context):
        # asyncio.ensure_future(ctx.send(f"Никто тебе не поможет, {ctx.author.display_name}!"))
        asyncio.ensure_future(ctx.send(
            f"@{ctx.author.display_name} Справка по командам ботика: https://iarspider.github.io/arachnobot/help"))


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
    for extension in ('discordcog', 'obscog', 'pluschcog', 'ripcog', 'SLCog',
                      'vmodcog', 'elfcog', 'duelcog'):  # REMOVEME: 'eventcog'
        twitch_bot.load_module(extension)

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
        global twitch_bot, dashboard_timer
        twitch_bot.dashboard = sid
        logger.info(f"Dashboard connected with id f{sid}")
        dashboard_timer = Timer(1, dashboard_loop)


    @sio_server.on('disconnect')
    async def on_ws_disconnected(sid):
        global dashboard_timer, twitch_bot
        if twitch_bot.dashboard == sid:
            logger.warning(f'Dashboard disconnected!')
            twitch_bot.dashboard = None
            dashboard_timer.cancel()


    async def dashboard_loop():
        try:
            item = twitch_bot.queue.get_nowait()
            logger.debug(f"send item {item}")
            # await websocket.send(simplejson.dumps(item))
            await sio_server.emit(item['action'], item['value'])
            logger.debug("sent")
        except asyncio.QueueEmpty:
            # logger.info("get item failed")
            return
        except (ValueError, Exception):
            logger.exception(f'Emit failed!')


    asyncio.ensure_future(twitch_bot.start())
    _loop.run_until_complete(server.serve())
    # _loop.run_until_complete(discord_bot.close())
    # _loop.stop()
