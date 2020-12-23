import asyncio
import datetime

import requests
import socketio.asyncio_client
from twitchio import Context
from requests.structures import CaseInsensitiveDict

import streamlabs_api as api
from twitchio.ext import commands
from config import *
import logging


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
        self.logger.info(f'SL event: {data}')
        pick_keys = []
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
        elif data['type'] == 'alertPlaying':
            return
        else:
            self.logger.warning(f'Unknown SL event type: {data["type"]}')
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

        await self.bot.queue.put(message)


@commands.cog()
class SLCog:
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("arachnobot.sl")
        self.sl_client: SLClient = SLClient(logger=self.logger, bot=bot)
        self.streamlabs_oauth = api.get_streamlabs_session(streamlabs_client_id, streamlabs_client_secret,
                                                           streamlabs_redirect_uri)

        token = api.get_socket_token(self.streamlabs_oauth)
        asyncio.ensure_future(self.sl_client.connect(f'https://sockets.streamlabs.com?token={token}'))
        self.last_post = CaseInsensitiveDict()
        self.post_price = {'regular': 20, 'vip': 10, 'mod': 0}

        # Forwarding functions from bot
        self.is_vip = self.bot.is_vip
        self.is_mod = self.bot.is_mod

    def __getattr__(self, item):
        if item != '__bases__':
            self.logger.warning(f"[OBS] Failed to get attribute {item}, redirecting to self.bot!")
        return self.bot.__getattribute__(item)

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
        lastpost = self.last_post.get(ctx.author.name, None)
        now = datetime.datetime.now()
        if lastpost is not None:
            delta = now - lastpost
            if delta.seconds < 10 * 60:
                asyncio.ensure_future(ctx.send("Не надо так часто отправлять почту!"))
                return

        if self.bot.is_mod(ctx.author.name):
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
            self.last_post[ctx.author.name] = now
            self.logger.debug(res)
            self.bot.play_sound("pochta.mp3")

    @commands.command(name='sos', aliases=['alarm'])
    async def sos(self, ctx: Context):
        if not (self.bot.is_mod(ctx.author.name) or ctx.author.name.lower() == 'iarspider'):
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
