import datetime
import logging

import pika
import simplejson
from pytils import numeral
from twitchio.ext import commands

from config import *


@commands.core.cog()
class DiscordCog:
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("arachnobot.dis")
        self.connection = pika.BlockingConnection(pika.URLParameters(rabbit_url))
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue='discord')

    def __getattr__(self, item):
        if item != '__bases__':
            self.logger.warning(f"[Discord] Failed to get attribute {item}, redirecting to self.bot!")
        return self.bot.__getattribute__(item)

    async def announce(self):
        stream = await self.bot.my_get_stream(self.bot.user_id)
        game = self.bot.my_get_game(stream['game_id'])
        delta = self.bot.countdown_to - datetime.datetime.now()
        delta_m = delta.seconds // 60
        delta_text = numeral.get_plural(delta_m, ('минута', 'минуты', 'минут'))
        announcement = f"@{discord_role} Паучок запустил стрим \"{stream['title']}\" " \
                       f"по игре \"{game['name']}\"! У вас есть примерно {delta_text} чтобы" \
                       " открыть стрим - <https://twitch.tv/iarspider>!"
        self.channel.basic_publish(exchange='',
                                   routing_key='discord',
                                   body=simplejson.dumps({'action': 'send', 'message': announcement,
                                                          'channel': discord_channel}))
