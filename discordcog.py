import datetime
import logging

import pika
import simplejson
from pytils import numeral
from twitchio import Context
from twitchio.ext import commands

from config import *


@commands.core.cog()
class DiscordCog:
    def __init__(self, bot):
        self.bot = bot
        self.check_sender = self.bot.check_sender
        self.logger = logging.getLogger("arachnobot.dis")

    def __getattr__(self, item):
        if item != '__bases__':
            self.logger.warning(f"[Discord] Failed to get attribute {item}, redirecting to self.bot!")
        return self.bot.__getattribute__(item)

    @commands.command(name='announce')
    async def cmd_announce(self, ctx: Context):
        if not self.check_sender(ctx, 'iarspider'):
            return

        await self.announce()

    async def announce(self):
        stream = await self.bot.my_get_stream(self.bot.user_id)
        game = self.bot.my_get_game(stream['game_id'])
        delta = self.bot.countdown_to - datetime.datetime.now()
        delta_m = delta.seconds // 60
        if delta_m > 0:
            delta_text = numeral.get_plural(delta_m, ('минута', 'минуты', 'минут'))
        else:
            delta_text = "одна минута"

        announcement = f"@{discord_role} Паучок запустил стрим \"{stream['title']}\" " \
                       f"по игре \"{game['name']}\"! У вас есть примерно {delta_text} чтобы" \
                       " открыть стрим - <https://twitch.tv/iarspider>!"

        connection = pika.BlockingConnection(pika.URLParameters(rabbit_url))
        channel = connection.channel()
        channel.queue_declare(queue='discord')
        channel.basic_publish(exchange='',
                              routing_key='discord',
                              body=simplejson.dumps({'action': 'send', 'message': announcement,
                                                     'channel': discord_channel}))
        channel.close()
        connection.close()
