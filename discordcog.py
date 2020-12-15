import asyncio
import datetime
from typing import Optional
import warnings

import discord
from pytils import numeral
from twitchio.ext import commands
from config import *


@commands.core.cog()
class DiscordCog:
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger
        self.discord_bot: Optional[discord.Client] = None
        self.discord_channel: Optional[discord.TextChannel] = None
        self.discord_role: Optional[discord.Role] = None

        self.main()

    def __getattr__(self, item):
        if item != '__bases__':
            self.logger.warning(f"[Discord] Failed to get attribute {item}, redirecting to self.bot!")
        return self.bot.__getattribute__(item)

    async def start_bot(self):
        # Only needed until discord.py updates it's dependencies
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            await self.discord_bot.start(discord_bot_token)

    def main(self):
        self.discord_bot = discord.Client()
        self.discord_bot.event(self.on_ready)
        asyncio.ensure_future(self.start_bot())

    async def on_ready(self):
        # print("Discord | on_ready")
        guild = discord.utils.find(lambda g: g.name == discord_guild_name, self.discord_bot.guilds)

        if guild is None:
            raise RuntimeError(f"Failed to join Discord guild {discord_guild_name}!")

        discord_channel = discord.utils.find(lambda c: c.name == discord_channel_name, guild.channels)
        if discord_channel is None:
            raise RuntimeError(f"Failed to join Discord channel {discord_channel_name}!")

        self.logger.info(f"Ready | {self.discord_bot.user} @ {guild.name}")

        discord_role = discord.utils.find(lambda r: r.name == discord_role_name, guild.roles)
        if discord_role is None:
            raise RuntimeError(f"No role {discord_role_name} in guild {discord_guild_name}!")

    async def announce(self):
        if self.discord_bot is not None and self.discord_channel is not None:
            stream = await self.bot.my_get_stream(self.bot.user_id)
            game = self.bot.my_get_game(stream['game_id'])
            delta = self.bot.countdown_to - datetime.datetime.now()
            delta_m = delta.seconds // 60
            delta_text = numeral.get_plural(delta_m, ('минута', 'минуты', 'минут'))
            announcement = f"<@&{self.discord_role.id}> Паучок запустил стрим \"{stream['title']}\" " \
                           f"по игре \"{game['name']}\"! У вас есть примерно {delta_text} чтобы" \
                           " открыть стрим - <https://twitch.tv/iarspider>!"
            await self.discord_channel.send(announcement)
            self.logger.info("Discord notification sent!")

