import asyncio
import datetime
import logging
import typing

import requests
import json
from twitchio import Channel, Context
from twitchio.ext import commands

from aio_timer import Periodic
from bot import Bot
from config import *

import requests

# from obscog import OBSCog
from obswebsocket import requests as obsws_requests

from mycog import MyCog


@commands.core.cog()
class MusicCog(MyCog):
    def __init__(self, bot):
        self.obscog = None
        self.bot: Bot = bot
        self.logger = logging.getLogger("arachnobot.music")
        self.last_song_id = 0

        self.token: typing.Optional[dict] = None
        self.login()
        self.timer: Periodic = Periodic("music", 2, self.post_music, self.bot.loop)
        self.bot.loop.run_until_complete(self.timer.start())

        # noinspection PyUnresolvedReferences

    def setup(self):
        self.obscog = self.bot.get_cog('OBSCog')

    def set_music(self, enabled: bool):
        r = requests.post('https://donateall.online/api/authenticate', json={'username': music_login, 'password':
            music_password, 'rememberMe': True})
        r.raise_for_status()
        res = r.json()
        token = res['id_token']

        r = requests.get('https://donateall.online/api/account', headers={'Authorization': 'Bearer ' + token})
        r.raise_for_status()
        res = r.json()
        if res.get('login') is None:
            self.logger.error("login failed {0}".format(res))
            return

        r = requests.get('https://donateall.online/api/user-chat-advance-settings',
                         headers={'Authorization': 'Bearer ' + token})
        r.raise_for_status()

        res = r.json()[0]
        id = res['id']

        settings = json.loads(res['settings'])
        settings['musicSettings']['isMusicEnabled'] = enabled

        settings_s = json.dumps(settings)

        r = requests.put('https://donateall.online/api/user-chat-advance-settings',
                         headers={'Authorization': 'Bearer ' + token}, json={"id": id, "settings": settings_s})
        r.raise_for_status()

    def update(self):
        self.set_music(self.bot.game.music_enabled)

    @commands.command(name='yesmusic')
    async def enable_music(self, ctx: Context):
        if not self.check_sender(ctx, 'iarspider'):
            self.logger.info("check_sender failed")
            return

        self.set_music(True)

    @commands.command(name='nomusic')
    async def disable_music(self, ctx: Context):
        if not self.check_sender(ctx, 'iarspider'):
            self.logger.info("check_sender failed")
            return

        self.set_music(False)

    def get_new_token(self):
        res = True
        self.logger.debug("get_new_token() started")
        response = requests.post("https://www.donateall.online/public/api/v1/authenticate",
                                 json={'username': music_login, 'password': music_password})
        self.logger.debug(f"get_new_token post() done, response code is {response.status_code}")

        if response.status_code == 200:
            self.logger.debug("get_new_token post(): writing token")
            with open('music_token.json', 'w') as f:
                f.write(response.text)
            self.token = response.json()
        else:
            self.logger.error("Failed to get new music token: " + str(response.status_code) + " " + response.text)
            self.token = None
            res = False

        self.logger.debug(f"get_new_token() done with result {res}")
        return True

    def refresh_token(self):
        res = True
        self.logger.debug("refresh_token() start")
        response = requests.post("https://www.donateall.online/public/api/v1/refresh",
                                 json={'refresh_token': self.token['refresh_token']})
        self.logger.debug(f"refesh_token post() done, response code is {response.status_code}")
        if response.status_code == 200:
            self.logger.debug(f"refresh_token: writing new token")
            data = response.json()
            self.token['access_token_expires'] = data['access_token_expires']
            self.token['access_token'] = data['access_token']
            with open('music_token.json', 'w') as f:
                json.dump(self.token, f)
        else:
            self.logger.error("Failed to refresh music token: " + str(response.status_code) + " " + response.text)
            self.token = None
            res = False

        self.logger.debug(f"refresh_token() done with result {res}")
        return res

    def load_token(self):
        try:
            with open('music_token.json', 'r') as f:
                self.token = json.load(f)

            return True
        except (IOError, OSError, json.JSONDecodeError) as e:
            print("Failed to get token: " + str(e))
            return False

    def ensure_token(self):
        self.logger.debug("ensure_token() started")
        refresh_expires = datetime.datetime.fromtimestamp(int(self.token['refresh_token_expires']) / 1000)
        access_expires = datetime.datetime.fromtimestamp(int(self.token['access_token_expires']) / 1000)
        now = datetime.datetime.now()
        if access_expires > now:
            self.logger.debug("access token valid")
            res = True
        else:
            self.logger.debug("access token expired")
            if refresh_expires > now:
                self.logger.debug("refresh token valid, try refreshing")
                res = self.refresh_token()
                if not res:
                    self.logger.warning('Failed to refresh using valid token')
                    self.logger.debug('refresh() failed, get new token from scratch')
                    res = self.get_new_token()
            else:
                self.logger.debug("refresh token expired, get new token from scratch")
                res = self.get_new_token()

        self.logger.debug(f"ensure_token() done with result {res}")
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
        self.logger.debug("get_current_song() start")
        try:
            self.logger.debug("get_current_song - do HTTP GET")
            response = self.get("https://www.donateall.online/public/api/v1/songs/current", timeout=(5, 5))
            self.logger.debug(f"get_current_song - HTTP GET returned {response.status_code}")
        except requests.Timeout:
            self.logger.warning("API request to donateall timed out!")
            response = None

        if response is not None:
            self.logger.debug("get_current_song - HTTP GET returned someting")
            if response.status_code == 204:
                self.logger.debug("No song playing")
            else:
                if response.status_code == 200:
                    self.logger.debug("get_current_song - song is playing")
                    j = response.json()
                    return {'song': j['songName'], 'requestor_display': j['author'] if j['authorized'] else None,
                            'requestor': j['author'], 'id': j['id']}
                else:
                    self.logger.error(f"Bad response code {response.status_code}!")
        else:
            self.logger.error("self.get() returned none")

        self.logger.debug("get_current_song() failed")
        return None

    def post_music(self):
        self.logger.debug("post_music() start")
        channel: Channel = self.bot.get_channel(self.bot.initial_channels[0].lstrip('#'))
        self.logger.debug("call get_current_song()")
        song = self.get_current_song()
        self.logger.debug("call get_current_song() done")

        if song:
            if song['id'] != self.last_song_id:
                self.last_song_id = song['id']
                item = {'action': 'song', 'value': song}

                if song["requestor_display"]:
                    asyncio.ensure_future(channel.send(f'Спасибо за заказ музыки, @{song["requestor_display"]}!'))
                    self.logger.info(f'Спасибо за заказ музыки, @{song["requestor_display"]}!')
                else:
                    asyncio.ensure_future(channel.send(f'Спасибо кому-то за заказ музыки!'))
                    self.logger.info(f'Спасибо кому-то за заказ музыки!')

                if self.bot.sio_server is not None:
                    # print(">> sio_server.emit start <<")
                    asyncio.ensure_future(self.bot.sio_server.emit(item['action'], item['value']))
                    # print(">> sio_server.emit end <<")
                else:
                    self.logger.warning("sio_server is None!")

#                if self.obscog.ws:
#                    if self.obscog.ws.call(obsws_requests.GetCurrentScene()).getName() in ('Starting', 'Paused'):
#                        self.obscog.ws.call(obsws_requests.SetMute('Радио', True))
#                        self.obscog.ws.call(obsws_requests.SetSceneItemProperties('Now Playing', visible=False))
#                    self.obscog.ws.call(obsws_requests.SetMute('Музыка', False))
        else:
            pass
#            if self.obscog.ws:
#                self.obscog.ws.call(obsws_requests.SetMute('Музыка', True))
#
#                if self.obscog.ws.call(obsws_requests.GetCurrentScene()).getName() in ('Starting', 'Paused'):
#                    self.obscog.ws.call(obsws_requests.SetMute('Радио', False))
#                    self.obscog.ws.call(obsws_requests.SetSceneItemProperties('Now Playing', visible=True))

        self.logger.debug("post_music done")
