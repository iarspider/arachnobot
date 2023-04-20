import asyncio
import codecs
import datetime
import glob
from loguru import logger
import os
import typing

import requests
from obswebsocket import obsws
from obswebsocket import requests as obsws_requests
from pytils import numeral
from twitchio.ext import commands, routines

from aio_timer import Periodic
from bot import Bot
from cogs.mycog import MyCog

import sys

sys.path.append("..")
from config import trailer_root


class OBSCog(MyCog):
    def __init__(self, bot):
        self.bot: Bot = bot
        self.ripcog: "RIPCog" = None
        self.vr: bool = False
        self.pretzel = None
        self.mplayer = None
        self.htmlfile = r"e:\__Stream\web\example.html"
        self.session = requests.Session()
        self.obsws_shutdown_timer: typing.Optional[Periodic] = None

        self.ws: typing.Optional[obsws] = None

        self.game = None
        self.title = None

        obsws_address = os.getenv("OBSWS_ADDRESS")
        obsws_port = os.getenv("OBSWS_PORT")
        obsws_password = os.getenv("OBSWS_PASSWORD")

        if all((obsws_address, obsws_port, obsws_password)):
            self.ws = obsws(obsws_address, int(obsws_port), obsws_password, legacy=True)
            self.ws.connect()
            self.aud_sources = self.ws.call(obsws_requests.GetSpecialSources())
            # self.ws.register(self.obs_on_start_stream, obsws_events.StreamStarted)
            # self.ws.register(self.obs_on_stop_stream, obsws_events.StreamStopped)
        else:
            self.ws = None

        # if pywinauto:
        #     self.get_player()

    def show_hide_scene_item(self, scene_name, item, visible):
        self.ws.call(
            obsws_requests.SetSceneItemProperties(
                **{"scene-name": scene_name, "item": item, "visible": visible}
            )
        )

    def setup(self):
        self.ripcog = self.bot.get_cog("RIPCog")

    def update(self):
        self.game = self.bot.game.game

    async def obsws_shutdown(self):
        logger.info("Disconnecting from OBS")
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
    #         logger.warning('Could not find MPC-BE window')
    #     else:
    #         self.session.get('http://localhost:13579/controls.html')
    #         logger.info(f"Got MPC, session cookies are {str(dict(
    #         self.session.cookies))}")
    #
    # def get_pretzel(self):
    #     if not pywinauto:
    #         return
    #     try:
    #         self.pretzel = pywinauto.Application().connect(title="Pretzel
    #         Rocks").top_window().wrapper_object()
    #     except (pywinauto.findwindows.ElementNotFoundError, RuntimeError):
    #         logger.warning('Could not find PretzelRocks window')

    # def player_play_pause(self):
    #     if self.pretzel:
    #         logger.info("Toggling Pretzel")
    #         self.pretzel.type_keys('+%P', set_foreground=False)  # Pause
    #     elif self.mplayer:
    #         logger.info("Toggling mplayer")
    #         # self.mplayer.type_keys('{VK_PLAY}', set_foreground=False)
    #         r = self.session.post("http://localhost:13579/command.html",
    #         data="wm_command=909&null=0")
    #         if not r.ok:
    #             logger.debug(f"Sending MUTE to player failed: {r.status_code},
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
            logger.info("Wrong sender!")
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
            logger.info("Wrong sender!")
            return

        if not self.ws:
            logger.info("OBS not present!")
            return

        self.ws.reconnect()
        self.bot.get_game_v5()

        res: obsws_requests.GetStreamingStatus = self.ws.call(
            obsws_requests.GetStreamingStatus()
        )
        if res.getStreaming():
            logger.error("Already streaming!")
            return

        self.switch_to("Starting")

        self.aud_sources = self.ws.call(obsws_requests.GetSpecialSources())
        self.ws.call(
            obsws_requests.SetCurrentProfile(**{"profile-name": "Regular games"})
        )
        self.ws.call(obsws_requests.SetCurrentSceneCollection(**{"sc-name": "Twitch"}))
        self.show_hide_scene_item("Paused", "ужин", False)

        # Load trailer
        game = self.game.replace("?", "_").replace(":", "_")
        files = glob.glob(
            os.path.join(trailer_root, game + " trailer.*"), recursive=False
        )
        if files:
            source: obsws_requests.GetSourceSettings = self.ws.call(
                obsws_requests.GetSourceSettings(
                    sourceName="Trailer", sourceType="ffmpeg_source"
                )
            )
            settings = source.getSourceSettings()
            logger.info(f"Trailer will use the following file: {files[0]}")
            settings["local_file"] = files[0].replace("\\", "/")
            res: obsws_requests.SetSourceSettings = self.ws.call(
                obsws_requests.SetSourceSettings(
                    sourceName="Trailer",
                    sourceSettings=settings,
                    sourceType="ffmpeg_source",
                )
            )

            self.show_hide_scene_item("Starting", "Trailer", True)
            self.show_hide_scene_item("Starting", "Screensaver", False)
        else:
            logger.info(f"No trailer found")
            self.show_hide_scene_item("Starting", "Trailer", False)
            self.show_hide_scene_item("Starting", "Screensaver", True)

        asyncio.ensure_future(
            ctx.send(
                "К стриму готов! | {0}... | {1}".format(
                    self.bot.title.split()[0], self.game
                )
            )
        )

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

        write_countdown_html()

        self.ws.call(obsws_requests.DisableStudioMode())

        # Refresh countdown
        self.ws.call(obsws_requests.SetCurrentScene(**{"scene-name": "Starting"}))
        self.show_hide_scene_item("Starting", "Countdown v3", False)
        self.show_hide_scene_item("Starting", "Countdown v3", True)

        # TODO
        # try:
        #     self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), True))
        # except KeyError:
        #     logger.warning("[WARN] Can't mute mic-2, please check!")
        self.ws.call(obsws_requests.SetMute(source="Mic", mute=True))

        self.ws.call(obsws_requests.SetMute(source="Радио", mute=False))

        self.show_hide_scene_item("Starting", "Ожидание", False)
        self.show_hide_scene_item("Starting", "Countdown v3", True)

        self.ws.call(obsws_requests.StartStopStreaming())

        asyncio.ensure_future(
            ctx.send(
                "Начат обратный отсчёт до {0}!".format(
                    self.bot.countdown_to.strftime("%X")
                )
            )
        )
        asyncio.ensure_future(self.bot.my_run_commercial(self.bot.streamer_id))

        logger.info("Getting Discord cog...")
        discord_bot = self.bot.get_cog("DiscordCog")
        if discord_bot:
            logger.info("Got it, requesting announce...")
            # noinspection PyUnresolvedReferences
            asyncio.ensure_future(discord_bot.announce())
        else:
            logger.warning("Discord cog not found")

        now = datetime.datetime.now()
        dt = self.bot.countdown_to - now
        h, ms = divmod(dt.seconds, 3600)
        m, s = divmod(ms, 60)

        @routines.routine(seconds=s, minutes=m, hours=h, wait_first=True, iterations=1)
        async def hide_zeroes(self):
            if self.ws.call(obsws_requests.GetCurrentScene()).getName() != "Starting":
                return

            self.show_or_hide_scene_item("Starting", "Ожидание", True)
            self.show_or_hide_scene_item("Starting", "Countdown v3", False)

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
            logger.error("Can't roll credits! " + str(exc))
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

        self.ws.call(obsws_requests.SetPreviewScene(**{"scene-name": scene}))
        self.ws.call(
            obsws_requests.TransitionToProgram(
                **{"with-transition": {"name": "Stinger"}}
            )
        )

        self.ws.call(obsws_requests.DisableStudioMode())

    def do_pause(self, ctx: typing.Optional[commands.Context], is_dinner: bool):
        # self.get_player()
        # self.player_play_pause()

        if self.ws is not None:
            self.ws.call(obsws_requests.PauseRecording())
            self.show_hide_scene_item("Paused", "ужин", is_dinner)

            self.switch_to("Paused")
            # if self.vr:
            #     self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), True))
            # else:
            self.ws.call(obsws_requests.SetMute(source="Mic", mute=True))

            self.ws.call(obsws_requests.SetMute(source="Радио", mute=False))
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
                self.ws.call(obsws_requests.SetMute(source="Mic", mute=False))
            self.ws.call(obsws_requests.SetMute(source="Радио", mute=True))

        self.ws.call(obsws_requests.StartRecording())

    async def do_resume(self, ctx: typing.Optional[commands.Context]):
        if self.ws is not None:
            old_screne = self.ws.call(obsws_requests.GetCurrentScene())

            self.show_hide_scene_item("Paused", "ужин", False)

            if self.vr:
                self.switch_to("VR Game")
                # self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(),
                # False))
            else:
                logger.info("switch to game")
                self.switch_to("Game")
                logger.info("unmute mic")
                self.ws.call(obsws_requests.SetMute(source="Mic", mute=False))

            self.ws.call(obsws_requests.SetMute(source="Радио", mute=True))
            res: obsws_requests.GetRecordingStatus = self.ws.call(
                obsws_requests.GetRecordingStatus()
            )
            if res.isRecordingPaused:
                self.ws.call(obsws_requests.ResumeRecording())
            else:

                self.ws.call(obsws_requests.StartRecording())

            if old_screne.name == "Battle":
                return

        try:
            logger.debug("get stream")
            res = await self.bot.my_get_stream(self.bot.streamer_id)
            logger.debug("got stream")
            viewers = numeral.get_plural(
                res["viewer_count"], ("зритель", "зрителя", "зрителей")
            )
            logger.debug("prepared message")
            msg = (
                f"Перепись населения завершена успешно! Население стрима "
                f"составляет {viewers}"
            )

            if ctx:
                asyncio.ensure_future(ctx.send(msg))

            logger.debug("sent message")
            return msg
        except (KeyError, TypeError) as exc:
            msg = "Перепись населения не удалась :("
            if ctx:
                asyncio.ensure_future(ctx.send(msg))
            logger.error(str(exc))
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
        await self.ripcog.lrip(ctx)

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
                source="ужин", text=f"Ужин, продолжим примерно в {arg} мск"
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
                source="ужин", text=f"Обед, продолжим примерно в {arg} мск"
            )
        )

        self.do_pause(ctx, True)

    async def enable_rip(self, state):
        self.show_hide_scene_item("Game", "RIP", state)

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
        # obsws_requests.GetSourceSettings('Game Capture', 'game_capture'))
        # settings = source.getSourceSettings()
        # settings['capture_mode'] = 'window'
        # settings['window'] = self.bot.game.window
        # self.ws.call(obsws_requests.SetSourceSettings('Game Capture', settings,
        # 'game_capture'))


def prepare(bot: commands.Bot):
    bot.add_cog(OBSCog(bot))
