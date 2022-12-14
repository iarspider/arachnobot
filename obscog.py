import asyncio
import codecs
import datetime
import glob
import logging
import os
import typing

import requests
from obswebsocket import obsws
from obswebsocket import requests as obsws_requests
from pytils import numeral
from twitchio.ext import commands

from aio_timer import Periodic
from bot import Bot
from config import *

# from ripcog import RIPCog
from mycog import MyCog


class OBSCog(MyCog):
    def __init__(self, bot):
        self.bot: Bot = bot
        self.ripcog = None
        self.logger: logging.Logger = logging.getLogger("arachnobot.obs")
        self.vr: bool = False
        self.pretzel = None
        self.mplayer = None
        self.htmlfile = r"e:\__Stream\web\example.html"
        self.session = requests.Session()
        self.obsws_shutdown_timer: typing.Optional[Periodic] = None
        self.countdown_timer: typing.Optional[Periodic] = None

        self.ws: typing.Optional[obsws] = None

        self.game = None
        self.title = None

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
            # self.ws.register(self.obs_on_start_stream, obsws_events.StreamStarted)
            # self.ws.register(self.obs_on_stop_stream, obsws_events.StreamStopped)

        # if pywinauto:
        #     self.get_player()

    def setup(self):
        self.ripcog = self.bot.get_cog("RIPCog")

    def update(self):
        self.game = self.bot.game.game

    async def obsws_shutdown(self):
        self.logger.info("Disconnecting from OBS")
        self.ws.disconnect()
        await self.obsws_shutdown_timer.stop()
        self.obsws_shutdown_timer = None

    # def get_player(self, kind: str = None):
    #     if not pywinauto:
    #         return
    #
    #     if self.mplayer or self.pretzel:
    #         logging.info("Player already detected")
    #         return
    #
    #     if kind is None or kind == 'pretzel':
    #         self.get_pretzel()
    #
    #     if (kind is None and self.pretzel is None) or kind == 'mplayer':
    #         self.get_mplayer()
    #
    # def get_mplayer(self):
    #     if not pywinauto:
    #         return
    #
    #     try:
    #         self.mplayer = pywinauto.Application().connect(
    #             title="rock_128 - MPC-BE 1.5.5 x64").top_window().wrapper_object()
    #     except (pywinauto.findwindows.ElementNotFoundError, RuntimeError):
    #         self.logger.warning('Could not find MPC-BE window')
    #     else:
    #         self.session.get('http://localhost:13579/controls.html')
    #         self.logger.info(f"Got MPC, session cookies are {str(dict(
    #         self.session.cookies))}")
    #
    # def get_pretzel(self):
    #     if not pywinauto:
    #         return
    #     try:
    #         self.pretzel = pywinauto.Application().connect(title="Pretzel
    #         Rocks").top_window().wrapper_object()
    #     except (pywinauto.findwindows.ElementNotFoundError, RuntimeError):
    #         self.logger.warning('Could not find PretzelRocks window')

    # def player_play_pause(self):
    #     if self.pretzel:
    #         self.logger.info("Toggling Pretzel")
    #         self.pretzel.type_keys('+%P', set_foreground=False)  # Pause
    #     elif self.mplayer:
    #         self.logger.info("Toggling mplayer")
    #         # self.mplayer.type_keys('{VK_PLAY}', set_foreground=False)
    #         r = self.session.post("http://localhost:13579/command.html",
    #         data="wm_command=909&null=0")
    #         if not r.ok:
    #             self.logger.debug(f"Sending MUTE to player failed: {r.status_code},
    #             {r.text}")
    #
    # @commands.command(name='play')
    # async def play(self, ctx: commands.Context):
    #     if not self.bot.check_sender(ctx, 'iarspider'):
    #         return
    #
    #     self.player_play_pause()

    @commands.command(name="stat", aliases=["stats", "ыефе", "ыефеы"])
    async def stats(self, ctx: commands.Context):
        if not self.bot.check_sender(ctx, "iarspider"):
            self.logger.info("Wrong sender!")
            return

        res: obsws_requests.GetStats = self.ws.call(obsws_requests.GetStats())
        stats = res.getStats()
        asyncio.ensure_future(
            ctx.send(
                f"FPS: {round(stats['fps'], 2)}, Skipped "
                f"{stats['output-skipped-frames']} "
                f"/ "
                f"{stats['output-total-frames']}, CPU {round(stats['cpu-usage'], 2)}"
            )
        )

    @commands.command(name="setup")
    async def setup_(self, ctx: commands.Context):
        if not self.bot.check_sender(ctx, "iarspider"):
            self.logger.info("Wrong sender!")
            return

        if not self.ws:
            self.logger.info("OBS not present!")
            return

        self.ws.reconnect()
        self.bot.get_game_v5()

        res: obsws_requests.GetStreamingStatus = self.ws.call(
            obsws_requests.GetStreamingStatus()
        )
        if res.getStreaming():
            self.logger.error("Already streaming!")
            return

        self.switch_to("Starting")

        self.aud_sources = self.ws.call(obsws_requests.GetSpecialSources())
        self.ws.call(obsws_requests.SetCurrentProfile("Regular games"))
        self.ws.call(obsws_requests.SetCurrentSceneCollection("Twitch"))
        self.ws.call(
            obsws_requests.SetSceneItemProperties(
                scene_name="Paused", item="ужин", visible=False
            )
        )

        # Load trailer
        game = self.game.replace("?", "_").replace(":", "_")
        files = glob.glob(
            os.path.join(trailer_root, game + " trailer.*"), recursive=False
        )
        if files:
            source: obsws_requests.GetSourceSettings = self.ws.call(
                obsws_requests.GetSourceSettings("Trailer", "ffmpeg_source")
            )
            settings = source.getSourceSettings()
            self.logger.info(f"Trailer will use the following file: {files[0]}")
            settings["local_file"] = files[0].replace("\\", "/")
            res: obsws_requests.SetSourceSettings = self.ws.call(
                obsws_requests.SetSourceSettings("Trailer", settings, "ffmpeg_source")
            )

            self.ws.call(
                obsws_requests.SetSceneItemProperties(
                    scene_name="Starting", item="Trailer", visible=True
                )
            )
            self.ws.call(
                obsws_requests.SetSceneItemProperties(
                    scene_name="Starting", item="Screensaver", visible=False
                )
            )
        else:
            self.logger.info(f"No trailer found")
            self.ws.call(
                obsws_requests.SetSceneItemProperties(
                    scene_name="Starting", item="Trailer", visible=False
                )
            )
            self.ws.call(
                obsws_requests.SetSceneItemProperties(
                    scene_name="Starting", item="Screensaver", visible=True
                )
            )

        if self.bot.game.window != "X":
            self.logger.info(f"Setting window to capture to {self.bot.game.window}")
            source: obsws_requests.GetSourceSettings = self.ws.call(
                obsws_requests.GetSourceSettings("Game Capture", "game_capture")
            )
            settings = source.getSourceSettings()
            settings["capture_mode"] = "window"
            settings["window"] = self.bot.game.window
            self.ws.call(
                obsws_requests.SetSourceSettings(
                    "Game Capture", settings, "game_capture"
                )
            )

        asyncio.ensure_future(
            ctx.send(
                "К стриму готов! | {0}... | {1}".format(
                    self.bot.title.split()[0], self.game
                )
            )
        )

    async def hide_zeroes(self):
        self.ws.call(
            obsws_requests.SetSceneItemProperties(
                scene_name="Starting", item="Ожидание", visible=True
            )
        )
        self.ws.call(
            obsws_requests.SetSceneItemProperties(
                scene_name="Starting", item="Countdown v3", visible=False
            )
        )
        await self.countdown_timer.stop()

    @commands.command(name="countdown", aliases=["preroll", "cd", "pr", "св", "зк"])
    async def countdown(self, ctx: commands.Context):
        def write_countdown_html():
            args = ctx.message.content.split()[1:]
            parts = tuple(int(x) for x in args[0].split(":"))
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

            with codecs.open(
                self.htmlfile.replace("html", "template"), encoding="UTF-8"
            ) as f:
                lines = f.read()

            lines = lines.replace("@@date@@", dt.isoformat())
            with codecs.open(self.htmlfile, "w", encoding="UTF-8") as f:
                f.write(lines)

        if not self.bot.check_sender(ctx, "iarspider"):
            return

        if not self.ws:
            return

        res: obsws_requests.GetStreamingStatus = self.ws.call(
            obsws_requests.GetStreamingStatus()
        )
        # if res.getStreaming():
        #     self.logger.error('Already streaming!')
        #     return

        write_countdown_html()

        # self.ws.call(obsws_requests.DisableStudioMode())

        # Refresh countdown
        self.ws.call(obsws_requests.SetCurrentScene("Starting"))
        self.ws.call(
            obsws_requests.SetSceneItemProperties(
                scene_name="Starting", item="Countdown v3", visible=False
            )
        )

        self.ws.call(
            obsws_requests.SetSceneItemProperties(
                scene_name="Starting", item="Countdown v3", visible=True
            )
        )

        # TODO
        # try:
        #     self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), True))
        # except KeyError:
        #     self.logger.warning("[WARN] Can't mute mic-2, please check!")
        self.ws.call(obsws_requests.SetMute("Mic", True))

        # self.ws.call(obsws_requests.EnableStudioMode())

        self.ws.call(obsws_requests.StartStopStreaming())
        now = datetime.datetime.now()
        dt = self.bot.countdown_to - now
        self.countdown_timer = Periodic(
            "countdown_to", dt.seconds, self.hide_zeroes, self.bot.loop
        )
        # time.sleep(1)
        # self.ws.call(obsws_requests.PauseRecording())
        # self.get_player()
        # self.player_play_pause()
        self.ws.call(obsws_requests.SetMute("Радио", False))

        self.ws.call(
            obsws_requests.SetSceneItemProperties(
                scene_name="Starting", item="Ожидание", visible=False
            )
        )
        self.ws.call(
            obsws_requests.SetSceneItemProperties(
                scene_name="Starting", item="Countdown v3", visible=True
            )
        )

        self.ws.call(obsws_requests.TransitionToProgram())

        asyncio.ensure_future(
            ctx.send(
                "Начат обратный отсчёт до {0}!".format(
                    self.bot.countdown_to.strftime("%X")
                )
            )
        )
        asyncio.ensure_future(self.bot.my_run_commercial(self.bot.streamer_id))

        self.logger.info("Getting Discord cog...")
        discord_bot = self.bot.get_cog("DiscordCog")
        if discord_bot:
            self.logger.info("Got it, requesting announce...")
            # noinspection PyUnresolvedReferences
            asyncio.ensure_future(discord_bot.announce())
        else:
            self.logger.warning("Discord cog not found")

    # noinspection PyUnusedLocal
    @commands.command(name="end", aliases=["fin", "конец", "credits"])
    async def end(self, ctx: commands.Context):
        if not self.bot.check_sender(ctx, "iarspider"):
            return

        api = self.bot.get_cog("SLCog")
        if not api:
            return

        self.ws.call(obsws_requests.SetCurrentScene("End"))
        try:
            # noinspection PyUnresolvedReferences
            api.roll_credits(self.streamlabs_oauth)
        except requests.HTTPError as exc:
            self.logger.error("Can't roll credits! " + str(exc))
            pass

    @commands.command(name="vr")
    async def toggle_vr(self, ctx: commands.Context):
        if not self.bot.check_sender(ctx, "iarspider"):
            return

        self.vr = not self.vr
        asyncio.ensure_future(
            ctx.send("VR-режим {0}".format("включен" if self.vr else "выключен"))
        )

    def switch_to(self, scene: str):
        res = self.ws.call(obsws_requests.GetStudioModeStatus())
        if not res.getStudioMode():
            self.ws.call(obsws_requests.EnableStudioMode())

        self.ws.call(obsws_requests.SetPreviewScene(scene))
        self.ws.call(obsws_requests.TransitionToProgram("Stinger"))

        self.ws.call(obsws_requests.DisableStudioMode())

    def do_pause(self, ctx: typing.Optional[commands.Context], is_dinner: bool):
        # self.get_player()
        # self.player_play_pause()

        if self.ws is not None:
            self.ws.call(obsws_requests.PauseRecording())
            self.ws.call(
                obsws_requests.SetSceneItemProperties(
                    scene_name="Paused", item="ужин", visible=is_dinner
                )
            )
            self.switch_to("Paused")
            # if self.vr:
            #     self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), True))
            # else:
            self.ws.call(obsws_requests.SetMute("Mic", True))

            self.ws.call(obsws_requests.SetMute("Радио", False))
        # self.get_chatters()
        if ctx:
            asyncio.ensure_future(ctx.send("Начать перепись населения!"))

        asyncio.ensure_future(self.bot.my_run_commercial(self.bot.streamer_id, 60))

    @commands.command(name="start")
    async def start_(self, ctx: commands.Context):
        """
        Начало трансляции. Аналог resume но без подсчёта зрителей

        %%start
        """
        if not self.bot.check_sender(ctx, "iarspider"):
            asyncio.ensure_future(ctx.send("/timeout " + ctx.author.name + " 1"))
            return

        # self.get_player()
        # self.player_play_pause()

        if self.ws is not None:
            if self.vr:
                self.switch_to("VR Game")
                # self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(),
                # False))
            else:
                self.switch_to("Game")
                self.ws.call(obsws_requests.SetMute("Mic", False))
            self.ws.call(obsws_requests.SetMute("Радио", True))

        self.ws.call(obsws_requests.StartRecording())

    async def do_resume(self, ctx: typing.Optional[commands.Context]):
        if self.ws is not None:
            old_screne = self.ws.call(obsws_requests.GetCurrentScene())

            if self.vr:
                self.switch_to("VR Game")
                # self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(),
                # False))
            else:
                self.logger.info("switch to game")
                self.switch_to("Game")
                self.logger.info("unmute mic")
                self.ws.call(obsws_requests.SetMute("Mic", False))

            self.ws.call(obsws_requests.SetMute("Радио", True))
            self.ws.call(obsws_requests.ResumeRecording())

            if old_screne.name == "Battle":
                return

        try:
            self.logger.debug("get stream")
            res = await self.bot.my_get_stream(self.bot.streamer_id)
            self.logger.debug("got stream")
            viewers = numeral.get_plural(
                res["viewer_count"], ("зритель", "зрителя", "зрителей")
            )
            self.logger.debug("prepared message")
            msg = (
                f"Перепись населения завершена успешно! Население стрима "
                f"составляет {viewers}"
            )

            if ctx:
                asyncio.ensure_future(ctx.send(msg))

            self.logger.debug("sent message")
            return msg
        except (KeyError, TypeError) as exc:
            msg = "Перепись населения не удалась :("
            if ctx:
                asyncio.ensure_future(ctx.send(msg))
            self.logger.error(str(exc))
            return msg

    @commands.command(name="resume")
    async def resume(self, ctx: commands.Context):
        """
        Отменяет перерыв

        %%resume
        """
        if not self.bot.check_sender(ctx, "iarspider"):
            asyncio.ensure_future(
                ctx.send(
                    "@" + ctx.author.name + ", у тебя нет прав на выполнение этой "
                    "команды!"
                )
            )
            return

        await self.do_resume(ctx)

    @commands.command(name="pause", aliases=("break",))
    async def pause(self, ctx: commands.Context):
        """
        Запускает перерыв

        %%pause
        """
        if not self.bot.check_sender(ctx, "iarspider"):
            asyncio.ensure_future(ctx.send("/timeout " + ctx.author.name + " 1"))
            return

        self.do_pause(ctx, False)

    @commands.command(name="ужин")
    async def dinner(self, ctx: commands.Context):
        """
        Ужин - особый тип перерыва, при котором показывается сообщение об ужине

        %%ужин
        """
        if not self.bot.check_sender(ctx, "iarspider"):
            asyncio.ensure_future(ctx.send("/timeout " + ctx.author.name + " 1"))
            return

        try:
            arg = ctx.message.content.split()[1]
        except ValueError:
            dt = datetime.datetime.now()
            dt += datetime.timedelta(hours=1)
            arg = dt.strftime("%H:%M")

        self.ws.call(
            obsws_requests.SetTextGDIPlusProperties(
                source="ужин", text=f"Ужин, продолжим " f"примерно в " f"{arg} мск"
            )
        )

        self.do_pause(ctx, True)

    @commands.command(name="обед")
    async def lunch(self, ctx: commands.Context):
        """
        Обед - особый тип перерыва, при котором показывается сообщение об обеде

        %%обед
        """
        if not self.bot.check_sender(ctx, "iarspider"):
            asyncio.ensure_future(ctx.send("/timeout " + ctx.author.name + " 1"))
            return

        try:
            arg = ctx.message.content.split()[1]
        except ValueError:
            dt = datetime.datetime.now()
            dt += datetime.timedelta(hours=1)
            arg = dt.strftime("%H:%M")

        self.ws.call(
            obsws_requests.SetTextGDIPlusProperties(
                source="ужин", text=f"Обед, продолжим " f"примерно в " f"{arg} мск"
            )
        )

        self.do_pause(ctx, True)

    async def enable_rip(self, state):
        self.ws.call(
            obsws_requests.SetSceneItemProperties(
                scene_name="Game", item="RIP", visible=state
            )
        )

    @commands.command(name="save")
    async def save_window(self, ctx: commands.Context):
        if self.bot.game is None:
            self.bot.get_game_v5()

        source: obsws_requests.GetSourceSettings = self.ws.call(
            obsws_requests.GetSourceSettings("Game Capture", "game_capture")
        )

        settings = source.getSourceSettings()
        if settings["capture_mode"] != "window":
            await ctx.send("Неправильный режим захвата!")
            return

        self.bot.game.window = settings["window"]
        self.bot.game.save()
        # if self.bot.game.window == 'X':
        #     return
        #
        # source: obsws_requests.GetSourceSettings = self.ws.call(
        # obsws_requests.GetSourceSettings('Game Capture',
        #                                                                                          'game_capture'))
        # settings = source.getSourceSettings()
        # settings['capture_mode'] = 'window'
        # settings['window'] = self.bot.game.window
        # self.ws.call(obsws_requests.SetSourceSettings('Game Capture', settings,
        # 'game_capture'))


def prepare(bot: commands.Bot):
    bot.add_cog(OBSCog(bot))
