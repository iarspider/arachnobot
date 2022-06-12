import asyncio
import datetime
import logging
import time
from tempfile import NamedTemporaryFile

import requests
import socketio.asyncio_client
from bs4 import BeautifulSoup
from requests.structures import CaseInsensitiveDict
from twitchio import Context
from twitchio.ext import commands

import streamlabs_api as api
from config import *
from mycog import MyCog


class SLClient(socketio.asyncio_client.AsyncClient):
    def __init__(self, **kwargs):
        self.bot = kwargs.pop('bot')
        super().__init__(**kwargs)
        self.on('connect', self.sl_client_connected)
        self.on('disconnect', self.sl_client_disconnected)
        self.on('event', self.sl_client_event)

    async def sl_client_connected(self):
        self.logger.info("SL client connected")

    async def sl_client_disconnected(self):
        self.logger.warning("SL client disconnected")

    async def sl_client_event(self, data):
        pick_keys = []
        self.logger.info(f'SL event: {data["type"]}')
        if data['type'] == 'donation':
            pick_keys.extend(('from', 'message', 'formatted_amount'))
        elif data['type'] == 'follow':
            pick_keys.extend(('name',))
        elif data['type'] == 'subscription':
            pick_keys.extend(('name', 'months', 'message', 'sub_plan', 'sub_type'))
            if data['message'][0]['sub_type'] == 'subgift':
                pick_keys.extend(('gifter_display_name',))
        elif data['type'] == 'resub':
            pick_keys.extend(('name', 'months', 'streak_months', 'message', 'sub_plan'))
        elif data['type'] == 'host':
            pick_keys.extend(('name', 'viewers'))
        elif data['type'] == 'bits':
            pick_keys.extend(('name', 'amount', 'message'))
        elif data['type'] == 'raid':
            pick_keys.extend(('name', 'raiders'))
        elif data['type'] in ('alertPlaying', 'streamlabels', 'streamlabels.underlying', 'subscription-playing'):
            return
        else:
            self.logger.info(f'SL event: {data["type"]}')
            self.logger.warning(f'Unknown SL event type: {data}')
            return

        def copy_keys(from_, to_, keys_):
            for k_ in keys_:
                if k_ in from_:
                    to_[k_] = from_[k_]
                else:
                    self.logger.warning(f'Event {data["type"]} missing key {k_}')
                    to_[k_] = 'UNKNOWN'

        message = {'action': 'event', 'value': {'type': data['type']}}
        if isinstance(data['message'], list):
            for msg in data['message']:
                copy_keys(msg, message['value'], pick_keys)
        else:
            copy_keys(data['message'], message['value'], pick_keys)

        # await self.bot.queue.put(message)
        # FIXME: send directly


@commands.cog()
class SLCog(MyCog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("arachnobot.sl")
        self.sl_client: SLClient = SLClient(logger=self.logger, bot=bot)
        self.streamlabs_oauth = api.get_streamlabs_session(streamlabs_client_id, streamlabs_client_secret,
                                                           streamlabs_redirect_uri)

        token = api.get_socket_token(self.streamlabs_oauth)
        asyncio.ensure_future(self.sl_client.connect(f'https://sockets.streamlabs.com?token={token}'))
        self.last_post = CaseInsensitiveDict()
        self.post_timeout = 1 * 60
        self.post_price = {'regular': 50, 'vip': 25, 'mod': 25}

        # Forwarding function from bot
        self.is_vip = self.bot.is_vip

        self.session = requests.Session()
        try:
            res = self.session.get('https://voxworker.com/ru')
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'html.parser')

            textId = soup.select("input[name=textId]")
            sessionId = soup.select("input[name=sessionId]")

            self.logger.debug('Prepare session for VoxWorker')

            self.voxdata = dict(textId=textId[0]['value'],
                                sessionId=sessionId[0]['value'],
                                voice='ya-omazh',
                                speed='1.0',
                                pitch='1.0',
                                text='Вы можете менять ударение знаком плюс. Например: хлоп+ок в ладоши или белый '
                                     'хл+опок.'
                                )
            self.logger.debug('Session ready')
        except requests.HTTPError as e:
            self.logger.exception(msg="Failed to initialize voxworker session", exc_info=e)
            self.voxdata = None
        except (IndexError, KeyError) as e:
            self.logger.exception("Failed to parse voxworker page")
            self.voxdata = None

    def __getattr__(self, item):
        if item != '__bases__':
            self.logger.warning(f"[OBS] Failed to get attribute {item}, redirecting to self.bot!")
        return self.bot.__getattribute__(item)

    def say(self, text):
        if not self.voxdata:
            self.logger.warning('VoxWorker not setup')
            return False
        self.voxdata['text'] = text
        res = self.session.post('https://voxworker.com/ru/ajax/convert', data=self.voxdata)
        if not res.ok:
            self.logger.error(f"Initial request to VoxWorker failed: {res.status_code}")
        resj = res.json()
        self.logger.debug('Sent request to VoxWorker')

        if resj['status'] == 'notify':
            self.logger.error(f"Got status 'notify': {resj['error']}, {resj['errorText']}")
            return False

        statusAttemptCount = 0
        while statusAttemptCount < 60 and resj['status'] == 'queue':
            self.logger.debug(f'VoxWorker: request queued, count: {statusAttemptCount}')
            res = self.session.get(f'https://voxworker.com/ru/ajax/status?id={resj["taskId"]}')
            if not res.ok:
                self.logger.error(f"Status request to VoxWorker failed: {res.status_code}")
                return False
            resj = res.json()
            statusAttemptCount += 1
            time.sleep(1)

        if statusAttemptCount == 60:
            self.logger.error('VoxWorker: Conversion error')
            return False

        if resj['status'] != 'ok':
            self.logger.error(f"VoxWorker bad status '{resj['status']}': {resj['error']}, {resj['errorText']}")
            return False
        else:
            self.logger.debug('Downloading file from VoxWorker')
            self.voxdata['textId'] = resj.get('textId', '')
            res = self.session.get(resj['downloadUrl'])
            if not res.ok:
                self.logger.error(f"Failed to download URL: {res.status_code}")
            with NamedTemporaryFile(delete=False) as tempfile:
                fname = tempfile.name
                tempfile.write(res.content)

            self.bot.play_sound("ding-sound-effect_1.mp3")
            self.bot.play_sound(fname, True)
            return True

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

    @commands.command(name='post', aliases=['почта'])
    async def post(self, ctx: Context):
        try:
            post_message = ctx.message.content.split(None, 1)[1]
        except IndexError:
            return

        lastpost = self.last_post.get(ctx.author.name, None)
        now = datetime.datetime.now()
        if lastpost is not None:
            delta = now - lastpost
            if delta.seconds < 10 * 60:
                asyncio.ensure_future(ctx.send("Не надо так часто отправлять почту!"))
                return

        if ctx.author.is_mod:
            price = self.post_price['mod']
        elif self.is_vip(ctx.author):
            price = self.post_price['vip']
        else:
            price = self.post_price['regular']

        points = api.get_points(self.streamlabs_oauth, ctx.author.name)

        if points < price:
            asyncio.ensure_future(ctx.send(f"У вас недостаточно багов для отправки почты - вам нужно минимум "
                                           f" {price}. Проверить баги: !баги"))
        else:
            res = api.sub_points(self.streamlabs_oauth, ctx.author.name, price)
            self.last_post[ctx.author.name] = now
            self.logger.debug(res)
            if not self.say(post_message):
                self.bot.play_sound("pochta.mp3")

    @commands.command(name='sos', aliases=['alarm'])
    async def sos(self, ctx: Context):
        if not (ctx.author.is_mod or ctx.author.name.lower() == 'iarspider' or ctx.author.name in rippers):
            asyncio.ensure_future(ctx.send("Эта кнопочка - не для тебя. Руки убрал, ЖИВО!"))
            return

        self.bot.play_sound("matmatmat.mp3")

    @commands.command(name='spin')
    async def spin(self, ctx: Context):
        if ctx.author.name.lower() != 'iarspider':
            return

        # points = api.get_points(self.streamlabs_oauth, ctx.author.name)
        # httpclient_logging_patch()
        requests.post('https://streamlabs.com/api/v1.0/wheel/spin',
                      data={'access_token': self.streamlabs_oauth.access_token})
        # httpclient_logging_patch(logging.INFO)
