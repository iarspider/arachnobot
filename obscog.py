import asyncio
import codecs
import datetime
import logging

try:
    import pywinauto
except ImportError as e:
    print('Failed to load pywinauto: {0}'.format(e))
    pywinauto = None

import requests
from pytils import numeral
from twitchio import Context
from twitchio.ext import commands
from obswebsocket import obsws
from obswebsocket import requests as obsws_requests

from bot import Bot
from config import *
# from lxml import etree


@commands.core.cog()
class OBSCog:
    def __init__(self, bot):
        self.bot: Bot = bot
        self.logger: logging.Logger = logging.getLogger("arachnobot.obs")
        self.vr: bool = False
        self.pretzel = None
        self.mplayer = None
        self.htmlfile = r'e:\__Stream\web\example.html'
        self.session = requests.Session()

        try:
            # noinspection PyStatementEffect
            # noinspection PyUnresolvedReferences
            obsws_address
            # noinspection PyStatementEffect
            # noinspection PyUnresolvedReferences
            obsws_port
            # noinspection PyStatementEffect
            # noinspection PyUnresolvedReferences
            obsws_password
        except NameError:
            self.ws = None
        else:
            # noinspection PyUnresolvedReferences
            self.ws = obsws(obsws_address, int(obsws_port), obsws_password)
            self.ws.connect()
            self.aud_sources = self.ws.call(obsws_requests.GetSpecialSources())

        if pywinauto:
            self.get_player()

    def __getattr__(self, item):
        if item != '__bases__':
            self.logger.warning(f"[OBS] Failed to get attribute {item}, redirecting to self.bot!")
        return self.bot.__getattribute__(item)

    def get_player(self, kind: str = None):
        if not pywinauto:
            return

        if self.mplayer or self.pretzel:
            logging.info("Player already detected")
            return

        if kind is None or kind == 'pretzel':
            self.get_pretzel()

        if (kind is None and self.pretzel is None) or kind == 'mplayer':
            self.get_mplayer()

    def get_mplayer(self):
        if not pywinauto:
            return

        try:
            self.mplayer = pywinauto.Application().connect(
                title="rock_128 - MPC-BE 1.5.5 x64").top_window().wrapper_object()
        except (pywinauto.findwindows.ElementNotFoundError, RuntimeError):
            self.logger.warning('Could not find MPC-BE window')
        else:
            self.session.get('http://localhost:13579/controls.html')
            self.logger.info(f"Got MPC, session cookies are {str(dict(self.session.cookies))}")

    def get_pretzel(self):
        if not pywinauto:
            return
        try:
            self.pretzel = pywinauto.Application().connect(title="Pretzel Rocks").top_window().wrapper_object()
        except (pywinauto.findwindows.ElementNotFoundError, RuntimeError):
            self.logger.warning('Could not find PretzelRocks window')

    def player_play_pause(self):
        if self.pretzel:
            self.logger.info("Toggling Pretzel")
            self.pretzel.type_keys('+%P', set_foreground=False)  # Pause
        elif self.mplayer:
            self.logger.info("Toggling mplayer")
            # self.mplayer.type_keys('{VK_PLAY}', set_foreground=False)
            # r = self.session.get('http://localhost:13579/controls.html')
            # if not r.ok:
            #     self.logger.error("Request to mplayer failed!")
            #     self.logger.debug("%s: %s", (r.status_code, r.text))
            #     return
            #
            # htmlparser = etree.HTMLParser()
            # tree = etree.fromstring(r.text, htmlparser)
            # try:
            #     status = tree.xpath("/html/body/table[1]/tr[2]/td[1]/text()")[0].strip()
            # except IndexError:
            #     self.logger.error("Can't find player status!")
            #     return
            #
            # self.logger.info(f"Play status: {status}")
            #
            # if status == 'Status: Playing':
            #     self.logger.debug('Sending STOP...')
            #     r = self.session.post("http://localhost:13579/command.html", data="wm_command=890&null=0")
            #     if not r.ok:
            #         self.logger.error(f"Sending STOP to player failed: {r.status_code}, {r.text}")
            # else:
            #     print('Sending PLAY...')
            #     r = self.session.post("http://localhost:13579/command.html", data="wm_command=887&null=0")
            #     if not r.ok:
            #         self.logger.debug(f"Sending PLAY to player failed: {r.status_code}, {r.text}")
            r = self.session.post("http://localhost:13579/command.html", data="wm_command=909&null=0")
            if not r.ok:
                self.logger.debug(f"Sending MUTE to player failed: {r.status_code}, {r.text}")

    @commands.command(name='play')
    async def play(self, ctx: Context):
        if not self.bot.check_sender(ctx, 'iarspider'):
            return

        self.player_play_pause()

    @commands.command(name='setup')
    async def setup(self, ctx: Context):
        if not self.bot.check_sender(ctx, 'iarspider'):
            self.logger.info('Wrong sender!')
            return

        if not self.ws:
            self.logger.info('OBS not connected!')
            return

        res: obsws_requests.GetStreamingStatus = self.ws.call(obsws_requests.GetStreamingStatus())
        if res.getStreaming():
            self.logger.error('Already streaming!')
            return

        self.aud_sources = self.ws.call(obsws_requests.GetSpecialSources())
        self.ws.call(obsws_requests.SetCurrentProfile('Regular games'))
        self.ws.call(obsws_requests.SetCurrentSceneCollection('Twitch'))
        self.ws.call(obsws_requests.SetSceneItemProperties(scene_name="Paused", item="ужин", visible=False))

        asyncio.ensure_future(ctx.send('К стриму готов!'))

    @commands.command(name='countdown', aliases=['preroll', 'cd', 'pr', 'св', 'зк'])
    async def countdown(self, ctx: Context):
        def write_countdown_html():
            args = ctx.message.content.split()[1:]
            parts = tuple(int(x) for x in args[0].split(':'))
            if len(parts) == 2:
                m, s = parts
                m, s = parts
                # noinspection PyShadowingNames
                delta = datetime.timedelta(minutes=m, seconds=s)
                dt = datetime.datetime.now() + delta
            elif len(parts) == 3:
                h, m, s = parts
                dt = datetime.datetime.now().replace(hour=h, minute=m, second=s)
            else:
                self.botlogger.error("Invalid call to countdown: {0}".format(args[0]))
                return

            self.bot.countdown_to = dt

            with codecs.open(self.htmlfile.replace('html', 'template'), encoding='UTF-8') as f:
                lines = f.read()

            lines = lines.replace('@@date@@', dt.isoformat())
            with codecs.open(self.htmlfile, 'w', encoding='UTF-8') as f:
                f.write(lines)

        if not self.bot.check_sender(ctx, 'iarspider'):
            return

        if not self.ws:
            return

        res: obsws_requests.GetStreamingStatus = self.ws.call(obsws_requests.GetStreamingStatus())
        if res.getStreaming():
            self.logger.error('Already streaming!')
            return

        write_countdown_html()

        self.ws.call(obsws_requests.DisableStudioMode())

        # Refresh countdown
        self.ws.call(obsws_requests.SetCurrentScene('Starting'))

        try:
            self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), True))
        except KeyError:
            self.logger.warning("[WARN] Can't mute mic-2, please check!")
        self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic1(), True))

        self.ws.call(obsws_requests.EnableStudioMode())

        self.ws.call(obsws_requests.StartStopStreaming())
        self.get_player()
        self.player_play_pause()

        asyncio.ensure_future(ctx.send('Начат обратный отсчёт до {0}!'.format(self.bot.countdown_to.strftime('%X'))))
        asyncio.ensure_future(self.bot.my_run_commercial(self.bot.user_id))

        self.logger.info("Getting Discord cog...")
        discord_bot = self.bot.get_cog('DiscordCog')
        if discord_bot:
            self.logger.info("Got it, sending announce...")
            asyncio.ensure_future(discord_bot.announce())
        else:
            self.logger.warning("Discord cog not found")

    # noinspection PyUnusedLocal
    @commands.command(name='end', aliases=['fin', 'конец', 'credits'])
    async def end(self, ctx: Context):
        if not self.bot.check_sender(ctx, 'iarspider'):
            return

        api = self.bot.get_cog("SLCog")
        if not api:
            return

        self.ws.call(obsws_requests.SetCurrentScene('End'))
        try:
            api.roll_credits(self.streamlabs_oauth)
        except requests.HTTPError as exc:
            self.logger.error("Can't roll credits! " + str(exc))
            pass

    @commands.command(name='vr')
    async def toggle_vr(self, ctx: Context):
        if not self.bot.check_sender(ctx, 'iarspider'):
            return

        self.vr = not self.vr
        asyncio.ensure_future(ctx.send('VR-режим {0}'.format('включен' if self.vr else 'выключен')))

    def switch_to(self, scene: str):
        res = self.ws.call(obsws_requests.GetStudioModeStatus())
        if not res.getStudioMode():
            self.ws.call(obsws_requests.EnableStudioMode())

        self.ws.call(obsws_requests.SetPreviewScene(scene))
        self.ws.call(obsws_requests.TransitionToProgram('Stinger'))

        self.ws.call(obsws_requests.DisableStudioMode())

    def do_pause(self, ctx: Context, is_dinner: bool):
        self.get_player()
        self.player_play_pause()

        if self.ws is not None:
            self.ws.call(obsws_requests.SetSceneItemProperties(scene_name="Paused", item="ужин", visible=is_dinner))
            self.switch_to('Paused')
            if self.vr:
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), True))
            else:
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic1(), True))

        # self.get_chatters()
        asyncio.ensure_future(ctx.send('Начать перепись населения!'))
        asyncio.ensure_future(self.bot.my_run_commercial(self.bot.user_id, 60))

    @commands.command(name='start')
    async def start_(self, ctx: Context):
        """
            Начало трансляции. Аналог resume но без подсчёта зрителей

            %%start
        """
        if not self.bot.check_sender(ctx, 'iarspider'):
            asyncio.ensure_future(ctx.send('/timeout ' + ctx.author.name + ' 1'))
            return

        self.get_player()
        self.player_play_pause()

        if self.ws is not None:
            if self.vr:
                self.switch_to('VR Game')
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), False))
            else:
                self.switch_to('Game')
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic1(), False))

    @commands.command(name='resume')
    async def resume(self, ctx: Context):
        """
            Отменяет перерыв

            %%resume
        """
        if not self.bot.check_sender(ctx, 'iarspider'):
            asyncio.ensure_future(ctx.send('/timeout ' + ctx.author.name + ' 1'))
            return

        self.logger.info("get_player()")
        self.get_player()
        self.logger.info("player_play_pause()")
        self.player_play_pause()

        if self.ws is not None:
            if self.vr:
                self.switch_to('VR Game')
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), False))
            else:
                self.logger.info("switch to game")
                self.switch_to('Game')
                self.logger.info("unmute mic")
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic1(), False))

        try:
            self.logger.info("get stream")
            res = await self.bot.my_get_stream(self.bot.user_id)
            self.logger.info("got stream")
            viewers = numeral.get_plural(res['viewer_count'], ('зритель', 'зрителя', 'зрителей'))
            self.logger.info("prepared message")
            asyncio.ensure_future(ctx.send('Перепись населения завершена успешно! '
                                           f'Население стрима составляет {viewers}'))
            self.logger.info("sent message")
        except (KeyError, TypeError) as exc:
            asyncio.ensure_future(ctx.send('Перепись населения не удалась :('))
            self.logger.error(str(exc))

    @commands.command(name='pause', aliases=('break',))
    async def pause(self, ctx: Context):
        """
            Запускает перерыв

            %%pause
        """
        if not self.bot.check_sender(ctx, 'iarspider'):
            asyncio.ensure_future(ctx.send('/timeout ' + ctx.author.name + ' 1'))
            return

        self.do_pause(ctx, False)

    @commands.command(name='ужин')
    async def dinner(self, ctx: Context):
        """
            Ужин - особый тип перерыва, при котором показывается сообщение об ужине

            %%ужин
        """
        if not self.bot.check_sender(ctx, 'iarspider'):
            asyncio.ensure_future(ctx.send('/timeout ' + ctx.author.name + ' 1'))
            return

        self.do_pause(ctx, True)
