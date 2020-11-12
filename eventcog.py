import asyncio
import datetime
from collections import deque

import simplejson
from twitchio import User
from twitchio.ext import commands

import twitch_api
from config import *

@commands.cog()
class EventCog:
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger
        self.pubsub_nonce = ''

    async def event_ready(self):
        self.logger.info(f'Ready | {self.nick}')
        self.bot.user_id = self.my_get_users(self.initial_channels[0].lstrip('#'))['id']
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
                self.bot.last_messages[message.author.name].append(message.content)
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

        self.logger.debug("handle_command start")
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
            await self.bot.queue.put({'action': 'event', 'value': {'type': 'hugs', 'from': requestor}})

        if reward_key == "Стримлер! Не горбись!".replace(' ', ''):
            self.logger.debug(f"Queued redepmtion: sit, {requestor}")
            await self.bot.queue.put({'action': 'event', 'value': {'type': 'sit', 'from': requestor}})

        if reward_key == "Добавить упорину".replace(' ', ''):
            self.logger.debug(f"Queued redepmtion: fun, {requestor}")
            await self.bot.queue.put({'action': 'event', 'value': {'type': 'fun', 'from': requestor}})

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
