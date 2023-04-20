import os
import sys

sys.path.append("..")
from config import discord_channel, discord_role

import datetime
import json

import pika
from pytils import numeral
from twitchio.ext import commands

from cogs.mycog import MyCog


class DiscordCog(MyCog):
    def __init__(self, bot):
        self.bot = bot
        self.check_sender = self.bot.check_sender

    @commands.command(name="announce")
    async def cmd_announce(self, ctx: commands.Context):
        if not self.check_sender(ctx, "iarspider"):
            return

        await self.announce(True)

    async def announce(self, now_ = False):
        stream = await self.bot.my_get_stream(self.bot.streamer_id)
        game = self.bot.my_get_game(stream["game_id"])
        delta = self.bot.countdown_to - datetime.datetime.now()
        delta_m = delta.seconds // 60
        if delta_m > 0 and not now_:
            delta_text = "примерно " + numeral.get_plural(delta_m, ("минута", "минуты", "минут"))
        else:
            delta_text = "меньше минуты"

        announcement = (
            f"@{discord_role} Паучок запустил стрим \"{stream['title']}\" "
            f"по игре \"{game['name']}\"! У вас есть {delta_text} чтобы"
            " открыть стрим - <https://twitch.tv/iarspider>!"
        )

        connection = pika.BlockingConnection(
            pika.URLParameters(os.getenv("RABBIT_URL"))
        )
        channel = connection.channel()
        channel.queue_declare(queue="discord")
        channel.basic_publish(
            exchange="",
            routing_key="discord",
            body=json.dumps(
                {"action": "send", "message": announcement, "channel": discord_channel}
            ).encode("utf-8"),
        )
        channel.close()
        connection.close()


def prepare(bot: commands.Bot):
    bot.add_cog(DiscordCog(bot))
