import asyncio
import os
import sys

from loguru import logger
from twitchio import Stream
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
        await self.announce(await self.bot.get_announce_text(True))

    # noinspection PyMethodMayBeStatic
    async def announce(self, text):
        announcement = f"@{discord_role} " + text
        delta = self.bot.countdown_to - datetime.datetime.now()

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
