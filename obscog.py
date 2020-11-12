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


@commands.core.cog()
class OBSCog:
    def __init__(self, bot):
        self.bot: Bot = bot
        self.logger: logging.Logger = bot.logger
        self.vr: bool = False
        self.player = None
        self.htmlfile = r'e:\__Stream\web\example.html'

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

    def get_player(self):
        if not pywinauto:
            return
        try:
            self.player = pywinauto.Application().connect(title="Pretzel").top_window().wrapper_object()
        except (pywinauto.findwindows.ElementNotFoundError, RuntimeError):
            self.logger.warning('Could not find PretzelRocks window')

    @commands.command(name='setup')
    async def setup(self, ctx: Context):
        if not self.check_sender(ctx, 'iarspider'):
            return

        if not self.ws:
            return

        res: obsws_requests.GetStreamingStatus = self.ws.call(obsws_requests.GetStreamingStatus())
        if res.getStreaming():
            self.logger.error('Already streaming!')
            return

        asyncio.ensure_future(ctx.send('К стриму готов!'))
        self.ws.call(obsws_requests.SetCurrentProfile('Regular games'))
        self.ws.call(obsws_requests.SetCurrentSceneCollection('Twitch'))

    @commands.command(name='countdown', aliases=['preroll', 'cd', 'pr', 'св', 'зк'])
    async def countdown(self, ctx: Context):
        def write_countdown_html():
            args = ctx.message.content.split()[1:]
            parts = tuple(int(x) for x in args[0].split(':'))
            if len(parts) == 2:
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

        if not self.check_sender(ctx, 'iarspider'):
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
        if self.player is not None:
            self.player.type_keys('+%P', set_foreground=False)  # Pause

        asyncio.ensure_future(ctx.send('Начат обратный отсчёт до {0}!'.format(self.countdown_to.strftime('%X'))))
        asyncio.ensure_future(self.my_run_commercial(self.user_id))

        discord_bot = self.bot.get_cog('discord')
        if discord_bot:
            asyncio.ensure_future(discord_bot.announce())

    # noinspection PyUnusedLocal
    @commands.command(name='end', aliases=['fin', 'конец', 'credits'])
    async def end(self, ctx: Context):
        if not self.check_sender(ctx, 'iarspider'):
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
        if not self.check_sender(ctx, 'iarspider'):
            return

        self.vr = not self.vr
        asyncio.ensure_future(ctx.send('VR-режим {0}'.format('включен' if self.vr else 'выключен')))

    def switch_to(self, scene: str):
        res = self.ws.call(obsws_requests.GetStudioModeStatus())
        if res.getStudioMode():
            self.ws.call(obsws_requests.SetPreviewScene(scene))
            self.ws.call(obsws_requests.TransitionToProgram('Stinger'))
        else:
            self.ws.call(obsws_requests.SetCurrentScene(scene))

    @commands.command(name='pause', aliases=('break',))
    async def pause(self, ctx: Context):
        """
            Запускает перерыв

            %%pause
        """
        if not self.check_sender(ctx, 'iarspider'):
            asyncio.ensure_future(ctx.send('/timeout ' + ctx.author.name + ' 1'))
            return

        self.get_player()
        if self.player is not None:
            self.player.type_keys('+%P', set_foreground=False)  # Pause

        if self.ws is not None:
            self.switch_to('Paused')
            if self.vr:
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), True))
            else:
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic1(), True))

        # self.get_chatters()
        asyncio.ensure_future(ctx.send('Начать перепись населения!'))
        asyncio.ensure_future(self.my_run_commercial(self.user_id, 60))

    @commands.command(name='start')
    async def start_(self, ctx: Context):
        """
            Начало трансляции. Аналог resume но без подсчёта зрителей

            %%start
        """
        if not self.check_sender(ctx, 'iarspider'):
            asyncio.ensure_future(ctx.send('/timeout ' + ctx.author.name + ' 1'))
            return

        self.get_player()
        if self.player is not None:
            self.player.type_keys('+%P', set_foreground=False)  # Pause

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
        if not self.check_sender(ctx, 'iarspider'):
            asyncio.ensure_future(ctx.send('/timeout ' + ctx.author.name + ' 1'))
            return

        self.get_player()
        if self.player is not None:
            self.player.type_keys('+%P', set_foreground=False)  # Pause

        if self.ws is not None:
            if self.vr:
                self.switch_to('VR Game')
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), False))
            else:
                self.switch_to('Game')
                self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic1(), False))

        try:
            res = await self.bot.my_get_stream(self.user_id)
            viewers = numeral.get_plural(res['viewer_count'], ('зритель', 'зрителя', 'зрителей'))
            asyncio.ensure_future(
                ctx.send(
                    'Перепись населения завершена успешно! Население стрима составляет {0}'.format(viewers)))
        except (KeyError, TypeError) as exc:
            asyncio.ensure_future(ctx.send('Перепись населения не удалась :('))
            self.logger.error(str(exc))
