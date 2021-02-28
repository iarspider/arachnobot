import datetime
import logging
import typing

import requests
import simplejson
from twitchio import Channel
from twitchio.ext import commands

from aio_timer import Periodic
from bot import Bot
from config import *

import requests


@commands.core.cog()
class MusicCog:
    def __init__(self, bot):
        self.bot: Bot = bot
        self.logger = logging.getLogger("arachnobot.music")
        self.timer: Periodic = Periodic("music", 5, self.post_music(), self.bot.loop)
        self.bot.loop.run_until_complete(self.timer.start())
        self.last_song_id = 0

        self.token: typing.Optional[dict] = None
        self.login()

    def get_new_token(self):
        response = requests.post("https://www.donateall.online/public/api/v1/authenticate",
                                 json={'username': music_login, 'password': music_password})

        if response.status_code == 200:
            with open('music_token.json', 'w') as f:
                f.write(response.text)
        else:
            print("Failed to get new music token: " + str(response.status_code) + " " + response.text)
            self.token = None
            return False

        self.token = response.json()
        return True

    def refresh_token(self):
        response = requests.post("https://www.donateall.online/public/api/v1/refresh",
                                 json={'refresh_token': self.token['refresh_token']})
        if response.status_code == 200:
            data = response.json()
            print (data)
            self.token['access_token_expires'] = data['access_token_expires']
            self.token['access_token'] = data['access_token']
            with open('music_token.json', 'w') as f:
                simplejson.dump(self.token, f)
        else:
            print("Failed to refresh music token: " + str(response.status_code) + " " + response.text)
            self.token = None
            return False

        return True

    def load_token(self):
        try:
            with open('music_token.json', 'r') as f:
                self.token = simplejson.load(f)

            return True
        except (IOError, OSError, simplejson.errors.JSONDecodeError) as e:
            print("Failed to get token: " + str(e))
            return False

    def ensure_token(self):
        res = True
        refresh_expires = datetime.datetime.fromtimestamp(int(self.token['refresh_token_expires']) / 1000)
        access_expires = datetime.datetime.fromtimestamp(int(self.token['access_token_expires']) / 1000)
        now = datetime.datetime.now()
        if refresh_expires < now:
            res = self.get_new_token()
        else:
            if access_expires < now:
                res = self.refresh_token()

        return res

    def login(self):
        res = self.load_token()
        if not res:
            res = self.get_new_token()
        else:
            res = self.ensure_token()

        return res

    def get(self, url, **kwargs) -> typing.Optional[requests.Response]:
        return self.request('GET', url, **kwargs)

    def request(self, method, url, **kwargs) -> typing.Optional[requests.Response]:
        res = self.ensure_token()
        if not res:
            self.logger.error("Token not available!")
            return None

        headers = kwargs.get("headers", {})
        headers['api_token'] = self.token['access_token']
        headers['Content-Type'] = 'application/json'
        kwargs['headers'] = headers

        return requests.request(method, url, **kwargs)

    def get_current_song(self) -> typing.Optional[dict]:
        response = self.get("https://www.donateall.online/public/api/v1/songs/current")
        if response is not None:
            if response.status_code == 204:
                self.logger.info("No song playing")
                return None
            else:
                if response.status_code == 200:
                    j = response.json()
                    return {'song': j['songName'], 'requestor_display': j['author'] if j['authorized'] else None,
                            'requestor': j['author'], 'id': j['id']}
                else:
                    self.logger.warning(f"Bad response code {response.status_code}!")
        else:
            self.logger.error("self.get() returned none")

    async def post_music(self):
        channel: Channel = self.bot.get_channel(self.bot.initial_channels[0].lstrip('#'))
        song = self.get_current_song()

        if song and song['id'] != self.last_song_id:
            self.last_song_id = song['id']
            item = {'action': 'song', 'value': song}

            if song["requestor_display"]:
                await channel.send(f'Спасибо за заказ музыки, @{song["requestor_display"]}!')
            else:
                await channel.send(f'Спасибо кому-то за заказ музыки!')

            if self.bot.sio_server is not None:
                await self.bot.sio_server.emit(item['action'], item['value'])
            else:
                self.logger.warning("sio_server is None!")