import os
import sys
from typing import Literal, Annotated

from pydantic import BaseModel, Base64Bytes, field_validator, AwareDatetime
from twitchio.ext.commands import Component, is_broadcaster

sys.path.append("..")
from config import discord_channel, discord_role

import datetime

import pika
from twitch_commands import twitch_command_aliased
from twitchio.ext import commands


class Attachment(BaseModel):
    filename: str
    data: Base64Bytes

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        if not v or v.strip() == "":
            raise ValueError("filename cannot be empty")

        # prevent path tricks
        if os.path.basename(v) != v:
            raise ValueError("filename must not contain path components")

        return v


class SendDiscordMessage(BaseModel):
    expires_at: Annotated[datetime.datetime, AwareDatetime]
    action: Literal["send"]
    attachment: Attachment | None = None
    body: str
    channel: str | None = None


class DiscordCog(Component):
    def __init__(self, bot):
        self.bot = bot

    @is_broadcaster()
    @twitch_command_aliased(name="announce")
    async def cmd_announce(self, ctx: commands.Context):
        await self.announce(await self.bot.get_announce_text(True)[0])

    # noinspection PyMethodMayBeStatic
    async def announce(self, text):
        announcement = f"@{discord_role} " + text
        delta = self.bot.countdown_to - datetime.datetime.now().astimezone()

        connection = pika.BlockingConnection(
            pika.URLParameters(os.getenv("RABBIT_URL"))
        )
        channel = connection.channel()
        channel.queue_declare(
            queue="discord", durable=True, arguments={"x-message-ttl": 60000}
        )
        msg = SendDiscordMessage(
            expires_at=self.bot.countdown_to,
            action="send",
            attachment=None,
            body=announcement,
            channel=discord_channel,
        )
        channel.basic_publish(
            exchange="",
            routing_key="discord",
            body=msg.model_dump_json(ensure_ascii=False),
            properties=pika.BasicProperties(expiration=str(delta.seconds * 1000)),
        )
        channel.close()
        connection.close()


async def setup(bot: commands.Bot):
    await bot.add_component(DiscordCog(bot))
