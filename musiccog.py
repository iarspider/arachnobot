import asyncio
import datetime
import logging
import typing

import requests
import json
from twitchio import Channel
from twitchio.ext import routines
from twitchio.ext.commands import Cog

from bot import Bot
from config import *
from singleton import Singleton


class MusicCog(Cog, metaclass=Singleton):
    def __init__(self, bot):
        self.bot: Bot = bot
        self.logger = logging.getLogger("arachnobot.music")
        self.token: typing.Optional[dict] = None
        self.login()
        self.last_song_id = 0

    def get_new_token(self):
        self.logger.debug(">> get_new_token post() <<")
        response = requests.post("https://www.donateall.online/public/api/v1/authenticate",
                                 json={'username': music_login, 'password': music_password})
        self.logger.debug(">> get_new_token post() done <<")

        if response.status_code == 200:
            with open('music_token.json', 'w') as f:
                f.write(response.text)
        else:
            self.logger.debug("Failed to get new music token: " + str(response.status_code) + " " + response.text)
            self.token = None
            return False

        self.token = response.json()
        return True

    def refresh_token(self):
        self.logger.debug(">> refesh_token <<")
        response = requests.post("https://www.donateall.online/public/api/v1/refresh",
                                 json={'refresh_token': self.token['refresh_token']})
        self.logger.debug(">> refesh_token post() done <<")
        if response.status_code == 200:
            data = response.json()
            print(data)
            self.token['access_token_expires'] = data['access_token_expires']
            self.token['access_token'] = data['access_token']
            with open('music_token.json', 'w') as f:
                json.dump(self.token, f)
        else:
            self.logger.debug("Failed to refresh music token: " + str(response.status_code) + " " + response.text)
            self.token = None
            return False

        return True

    def load_token(self):
        try:
            with open('music_token.json', 'r') as f:
                self.token = json.load(f)

            return True
        except (IOError, OSError, json.JSONDecodeError) as e:
            self.logger.debug("Failed to get token: " + str(e))
            return False

    def ensure_token(self):
        self.logger.debug(">> ensure_token <<")
        res = True
        refresh_expires = datetime.datetime.fromtimestamp(int(self.token['refresh_token_expires']) / 1000)
        access_expires = datetime.datetime.fromtimestamp(int(self.token['access_token_expires']) / 1000)
        now = datetime.datetime.now()
        if refresh_expires < now:
            self.logger.debug(">> token expired, renew <<")
            res = self.get_new_token()
        else:
            if access_expires < now:
                self.logger.debug(">> token except, refesh <<")
                res = self.refresh_token()

        self.logger.debug(">> ensure_token done <<")
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
        self.logger.debug("<< get_current_song >>")
        try:
            self.logger.debug("<< get_current_song get(...) >>")
            response = self.get("https://www.donateall.online/public/api/v1/songs/current", timeout=(1, 1))
        except requests.Timeout:
            self.logger.debug("<< get_current_song Timeout! >>")
            self.logger.error("API request to donateall timed out!")
            response = None

        if response is not None:
            self.logger.debug("<< get_current_song get(...) done>>")
            if response.status_code == 204:
                self.logger.debug("<< get_current_song no song playing >>")
                self.logger.info("No song playing")
            else:
                if response.status_code == 200:
                    self.logger.debug("<< get_current_song HTTP OK >>")
                    j = response.json()
                    return {'song': j['songName'], 'requestor_display': j['author'] if j['authorized'] else None,
                            'requestor': j['author'], 'id': j['id']}
                else:
                    self.logger.debug(f"<< get_current_song Bad response code {response.status_code}! >>")
                    self.logger.warning(f"Bad response code {response.status_code}!")
        else:
            self.logger.error("self.get() returned none")

        return None

    @routines.routine(seconds=5.0, iterations=None)
    async def post_music(self):
        self.logger.debug(">> post_music start <<")
        # channel: Channel = self.bot.get_channel(self.bot.initial_channels[0].lstrip('#'))
        channel: Channel = self.bot.connected_channels[0]
        self.logger.debug(">> get_current_song start <<")
        song = self.get_current_song()
        self.logger.debug(">> get_current_song end <<")

        if song and song['id'] != self.last_song_id:
            self.last_song_id = song['id']
            item = {'action': 'song', 'value': song}

            if song["requestor_display"]:
                # await channel.send(f'Спасибо за заказ музыки, @{song["requestor_display"]}!')
                self.logger.debug(f'Спасибо за заказ музыки, @{song["requestor_display"]}!')
            else:
                # await channel.send(f'Спасибо кому-то за заказ музыки!')
                self.logger.debug(f'Спасибо кому-то за заказ музыки!')

            if self.bot.sio_server is not None:
                self.logger.debug(">> sio_server.emit start <<")
                asyncio.ensure_future(self.bot.sio_server.emit(item['action'], item['value']))
                self.logger.debug(">> sio_server.emit end <<")
            else:
                self.logger.warning("sio_server is None!")

        self.logger.debug(">> post_music end <<")
