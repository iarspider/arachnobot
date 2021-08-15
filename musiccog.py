import asyncio
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
        self.timer: Periodic = Periodic("music", 5, self.post_music, self.bot.loop)
        self.login()
        self.bot.loop.run_until_complete(self.timer.start())
        self.last_song_id = 0

        self.token: typing.Optional[dict] = None

    def get_new_token(self):
        print(">> get_new_token <<")
        response = requests.post("https://www.donateall.online/public/api/v1/authenticate",
                                 json={'username': music_login, 'password': music_password})
        print(">> get_new_token post() done <<")

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
        print(">> refesh_token <<")
        response = requests.post("https://www.donateall.online/public/api/v1/refresh",
                                 json={'refresh_token': self.token['refresh_token']})
        print(">> refesh_token post() done <<")
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
        print(">> ensure_token <<")
        res = True
        refresh_expires = datetime.datetime.fromtimestamp(int(self.token['refresh_token_expires']) / 1000)
        access_expires = datetime.datetime.fromtimestamp(int(self.token['access_token_expires']) / 1000)
        now = datetime.datetime.now()
        if refresh_expires < now:
            print(">> token expired, renew <<")
            res = self.get_new_token()
        else:
            if access_expires < now:
                print(">> token except, refesh <<")
                res = self.refresh_token()

        print(">> ensure_token done <<")
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
        print("<< get_current_song >>")
        try:
            print("<< get_current_song get(...) >>")
            response = self.get("https://www.donateall.online/public/api/v1/songs/current", timeout=(1, 1))
        except requests.Timeout:
            print("<< get_current_song Timeout! >>")
            self.logger.error("API request to donateall timed out!")
            response = None

        if response is not None:
            print("<< get_current_song get(...) done>>")
            if response.status_code == 204:
                print("<< get_current_song no song playing >>")
                self.logger.info("No song playing")
            else:
                if response.status_code == 200:
                    print("<< get_current_song HTTP OK >>")
                    j = response.json()
                    return {'song': j['songName'], 'requestor_display': j['author'] if j['authorized'] else None,
                            'requestor': j['author'], 'id': j['id']}
                else:
                    print(f"<< get_current_song Bad response code {response.status_code}! >>")
                    self.logger.warning(f"Bad response code {response.status_code}!")
        else:
            self.logger.error("self.get() returned none")

        return None

    def post_music(self):
        print(">> post_music start <<")
        channel: Channel = self.bot.get_channel(self.bot.initial_channels[0].lstrip('#'))
        print(">> get_current_song start <<")
        song = self.get_current_song()
        print(">> get_current_song end <<")

        if song and song['id'] != self.last_song_id:
            self.last_song_id = song['id']
            item = {'action': 'song', 'value': song}

            if song["requestor_display"]:
                # await channel.send(f'Спасибо за заказ музыки, @{song["requestor_display"]}!')
                print(f'Спасибо за заказ музыки, @{song["requestor_display"]}!')
            else:
                # await channel.send(f'Спасибо кому-то за заказ музыки!')
                print(f'Спасибо кому-то за заказ музыки!')

            if self.bot.sio_server is not None:
                print(">> sio_server.emit start <<")
                asyncio.ensure_future(self.bot.sio_server.emit(item['action'], item['value']))
                print(">> sio_server.emit end <<")
            else:
                self.logger.warning("sio_server is None!")

        print(">> post_music end <<")