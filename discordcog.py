import datetime
import json
import logging

import pika
from pytils import numeral
from twitchio.ext import commands

from config import *
from mycog import MyCog


class DiscordCog(MyCog):
    def __init__(self, bot):
        self.bot = bot
        self.check_sender = self.bot.check_sender
        self.logger = logging.getLogger("arachnobot.dis")

    @commands.command(name="announce")
    async def cmd_announce(self, ctx: commands.Context):
        if not self.check_sender(ctx, "iarspider"):
            return

        await self.announce()

    async def announce(self):
        stream = await self.bot.my_get_stream(self.bot.streamer_id)
        game = self.bot.my_get_game(stream["game_id"])
        delta = self.bot.countdown_to - datetime.datetime.now()
        delta_m = delta.seconds // 60
        if delta_m > 0:
            delta_text = numeral.get_plural(delta_m, ("минута", "минуты", "минут"))
        else:
            delta_text = "одна минута"

        announcement = (
            f"@{discord_role} Паучок запустил стрим \"{stream['title']}\" "
            f"по игре \"{game['name']}\"! У вас есть примерно {delta_text} чтобы"
            " открыть стрим - <https://twitch.tv/iarspider>!"
        )

        connection = pika.BlockingConnection(pika.URLParameters(rabbit_url))
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
