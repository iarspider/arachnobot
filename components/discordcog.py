import os
import sys

from twitchio.ext.commands import Component, is_broadcaster

sys.path.append("..")
from config import discord_channel, discord_role

import datetime
import json

import pika
from pytils import numeral
from twitch_commands import twitch_command_aliased, check_sender
from twitchio.ext import commands


class DiscordCog(Component):
    def __init__(self, bot):
        self.bot = bot

    @is_broadcaster()
    @twitch_command_aliased(name="announce")
    async def cmd_announce(self, ctx: commands.Context):
        await self.announce(True)

    async def announce(self, now_=False):
        stream = await self.bot.fetch_streams(user_ids=[self.bot.streamer_id])
        stream = stream[0]
        game = self.bot.fetch_game(id=stream["game_id"])
        #        game = {"name": "Just Chatting"}
        #        stream = {"title": "Проверка оповещений"}
        delta = self.bot.countdown_to - datetime.datetime.now()
        delta_m = delta.seconds // 60
        if delta_m > 0 and not now_:
            delta_text = "примерно " + numeral.get_plural(
                delta_m, ("минута", "минуты", "минут")
            )
        else:
            delta_text = "меньше минуты"

        #        delta_text = "всё время мира"

        announcement = (
            f'@{discord_role} Паучок запустил стрим "{stream.title}" '
            f'по игре "{game.name}"! У вас есть {delta_text} чтобы'
            " открыть стрим - <https://twitch.tv/iarspider>!"
        )

        connection = pika.BlockingConnection(
            pika.URLParameters(os.getenv("RABBIT_URL"))
        )
        channel = connection.channel()
        channel.queue_declare(
            queue="discord", durable=True, arguments={"x-message-ttl": 60000}
        )
        channel.basic_publish(
            exchange="",
            routing_key="discord",
            body=json.dumps(
                {"action": "send", "message": announcement, "channel": discord_channel}
            ).encode("utf-8"),
            properties=pika.BasicProperties(expiration=str(delta.seconds * 1000)),
        )
        channel.close()
        connection.close()


async def setup(bot: commands.Bot):
    await bot.add_component(DiscordCog(bot))
