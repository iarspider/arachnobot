import asyncio
import codecs
import datetime
import fnmatch
import glob
import os
import random
import re
import sys
import time
import traceback
import typing

import requests
from Xlib import X, display
from Xlib.error import XError
from loguru import logger
from obswebsocket import obsws
from obswebsocket import requests as obsws_requests
from pytils import numeral
from twitchio.ext import commands
from twitchio.ext.commands import Component
from twitchio.ext.commands import is_broadcaster

from newbot import SourceConfig
from twitch_commands import twitch_command_aliased

sys.path.append("..")
from config import trailer_root, trailer_default


#
# def ws_call(self, obj):
#     """
#     Make a call to the OBS server through the Websocket.
#
#     :param obj: Request (class from obswebsocket.requests module) to send
#         to the server.
#     :return: Request object populated with response data.
#     """
#     if not isinstance(obj, base_classes.Baserequests):
#         raise exceptions.ObjectError("Call parameter is not a request object")
#     data = obj.data()
#
#     message_id = str(self.id)
#     self.id += 1
#     event = threading.Event()
#     self.events[message_id] = event
#
#     if self.legacy:
#         payload = {"message-id": message_id, "request-type": obj.name}
#         payload.update(data)
#     else:
#         payload = {
#             "op": 6,
#             "d": {
#                 "requestId": message_id,
#                 "requestType": obj.name,
#                 "requestData": data,
#             },
#         }
#     # IARSpider: send UTF-8 encoded data
#     payload_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
#     LOG.debug("Sending message id {}: {}".format(message_id, payload_body))
#     self.ws.send(payload_body)
#     # end
#
#     event.wait(self.timeout)
#     self.events.pop(message_id)
#
#     if message_id in self.answers:
#         r = self.answers.pop(message_id)
#         if self.legacy:
#             obj.input(r, r["status"] == "ok")
#         else:
#             obj.input(r.get("responseData", {}), r["requestStatus"]["result"])
#         return obj
#     raise exceptions.MessageTimeout("No answer for message {}".format(message_id))
#


class OBSCog(Component):
    def __init__(self, bot):
        self.bot = bot
        self.ripcog: "RIPCog" = None
        self.vr: bool = False
        self.pretzel = None
        self.mplayer = None
        self.htmlfile = r"/home/razumov/__Stream/web/example.html"
        self.session = requests.Session()

        self.ws: typing.Optional[obsws] = None
        self.teleport_ws: typing.Optional[obsws] = None

        self.title = None

        obsws_address = os.getenv("OBSWS_ADDRESS")
        obsws_port = os.getenv("OBSWS_PORT")
        obsws_password = os.getenv("OBSWS_PASSWORD")

        if all((obsws_address, obsws_port, obsws_password)):
            self.ws = obsws(
                obsws_address, int(obsws_port), obsws_password, legacy=False
            )
            self.ws.connect()
            self._aud_sources = self.ws.call(obsws_requests.GetSpecialInputs())
            # obsws.call = ws_call
        else:
            self.ws = None

        obsws_address = os.getenv("OBSWS_TELEPORT_ADDRESS")
        obsws_port = os.getenv("OBSWS_TELEPORT_PORT")
        obsws_password = os.getenv("OBSWS_TELEPORT_PASSWORD")

        if all((obsws_address, obsws_port, obsws_password)):
            self.teleport_ws = obsws(
                obsws_address, int(obsws_port), obsws_password, legacy=False
            )
            self.teleport_ws.connect()
            # self.aud_sources = self.ws.call(obsws_requests.GetSpecialInputs())
        else:
            self.teleport_ws = None

        self.use_teleport = False
        self.event = asyncio.Event()

    @property
    def game(self):
        return self.bot.game

    @property
    def aud_sources(self):
        for _ in range(10):
            try:
                self._aud_sources.getMic1()
                return self._aud_sources
            except KeyError:
                self._aud_sources = self.ws.call(obsws_requests.GetSpecialInputs())

        asyncio.ensure_future(self.bot.send_message("Failed to setup audio sources"))
        exit(1)

    @staticmethod
    def find_window_by_title_and_class(target_title, target_class, inexact=False):
        # Connect to the X server
        disp = display.Display()
        root = disp.screen().root

        # Get all child windows recursively
        def get_all_windows(window_):
            children = window_.query_tree().children
            all_windows_ = []
            for child in children:
                all_windows_.append(child)
                all_windows_.extend(get_all_windows(child))
            return all_windows_

        all_windows = get_all_windows(root)

        title_match = False

        for window in all_windows:
            try:
                # Get the window's title
                title_atom = disp.intern_atom("_NET_WM_NAME")
                title = window.get_property(title_atom, X.AnyPropertyType, 0, 1024)
                if title:
                    title = title.value.decode("utf-8")
                    if title == target_title and not inexact:
                        logger.debug(f"Found window with matching title")
                        title_match = True
                    else:
                        if fnmatch.fnmatch(title, target_title) and inexact:
                            logger.debug(
                                f"Found window with matching title (wildcard match)"
                            )
                            title_match = True

                # Get the window's class
                class_atom = disp.intern_atom("WM_CLASS")
                window_class = window.get_property(
                    class_atom, X.AnyPropertyType, 0, 1024
                )
                if window_class:
                    window_class = window_class.value.decode("utf-8").split("\0")
                    if target_class in window_class:
                        logger.debug("Found window with matching class")

                if title_match and window_class and (target_class in window_class):
                    logger.debug(
                        f"Found window with title '{title}' and class '{window_class}'"
                    )
                    return window
            except (XError, UnicodeDecodeError, AttributeError) as e:
                logger.debug(f"Ignored window due to exception: {e}")
                continue  # Ignore inaccessible windows or decoding errors

        logger.debug(
            f"Window with title '{target_title}' and class '{target_class}' not found"
        )
        return None

    def ws_call(self, request: obsws_requests.Baserequests):
        if self.use_teleport:
            return self.teleport_ws.call(request)
        else:
            return self.ws.call(request)

    def show_hide_scene_item(self, scene_name, item, visible):
        res = self.ws.call(
            obsws_requests.GetSceneItemId(sceneName=scene_name, sourceName=item)
        )
        if res.status:
            scene_item_id = res.getSceneItemId()
            self.ws.call(
                obsws_requests.SetSceneItemEnabled(
                    sceneName=scene_name,
                    sceneItemId=scene_item_id,
                    sceneItemEnabled=visible,
                )
            )

    def setup(self):
        self.ripcog = self.bot.get_component("RIPCog")

    @is_broadcaster()
    @twitch_command_aliased(name="stat", aliases=("stats",))
    async def stats(self, ctx: commands.Context):
        res: obsws_requests.GetStats = self.ws_call(obsws_requests.GetStats())
        asyncio.ensure_future(
            ctx.send(
                f"FPS: {round(res.getActiveFps(), 2)}, Skipped "
                f"{res.getOutputSkippedFrames()} "
                f"/ "
                f"{res.getOutputTotalFrames}, CPU "
                f"{round(res.GetCpuUsage(), 2)}"
            )
        )

    # noinspection PyUnusedLocal
    @is_broadcaster()
    @twitch_command_aliased(name="teleport", aliases=("tp",))
    async def teleport(self, ctx: commands.Context):
        if not self.ws:
            return

        if not self.use_teleport:
            self.teleport_ws.connect()
            logger.info("Will use teleport!")
            self.use_teleport = True
        else:
            self.teleport_ws.disconnect()
            logger.info("Will use local OBS")
            self.use_teleport = False

    @is_broadcaster()
    @twitch_command_aliased(name="setup")
    async def setup_(self, ctx: commands.Context):
        def sanitize_filename(filename):
            invalid_chars = r'[<>:"/\\|?*\x00-\x1F]'
            sanitized_name = re.sub(invalid_chars, "_", filename)
            return sanitized_name.strip()

        if not self.ws:
            logger.info("OBS not present!")
            return

        self.ws.reconnect()
        if self.use_teleport:
            self.teleport_ws.reconnect()

        await self.bot.get_game_v5()

        self.ws.call(obsws_requests.SetCurrentProfile(profileName="Twitch"))
        self.ws.call(
            obsws_requests.SetCurrentSceneCollection(sceneCollectionName="Twitch")
        )
        self.switch_to("Starting")
        self.show_hide_scene_item("Paused", "ужин", False)

        res: obsws_requests.GetStreamStatus = self.ws_call(
            obsws_requests.GetStreamStatus()
        )
        if res.getOutputActive():
            logger.error("Already streaming!")
            return

        # Load trailer
        game_trailer_glob = sanitize_filename(self.bot.game.game) + " trailer.*"
        logger.info("Looking for trailer named " + game_trailer_glob)
        files = glob.glob(
            os.path.join(trailer_root, game_trailer_glob), recursive=False
        )
        if not files:
            logger.info(f"No trailer found, will use screensaver")
            files = [trailer_default]
        else:
            logger.info(f"Trailer will use the following file: {files[0]}")

        self.ws.call(
            obsws_requests.SetInputSettings(
                inputName="Screensaver",
                inputSettings={"local_file": files[0].replace("\\", "/")},
                overlay=True,
            )
        )

        self.show_hide_scene_item("Starting", "Screensaver", False)
        time.sleep(1)
        self.show_hide_scene_item("Starting", "Screensaver", True)
        tags = [x for x in self.game.tags.split(";") if x]

        if tags:
            logger.debug("Set tags", tags)
            await ctx.broadcaster.modify_channel(tags=tags)

        await ctx.reply(
            "К стриму готов! | {0}... | {1}".format(
                self.bot.title.split("|")[0], self.bot.game.game
            )
        )

        self.event.set()

    @is_broadcaster()
    @twitch_command_aliased(name="countdown", aliases=("preroll", "cd", "pr"))
    async def countdown(self, ctx: commands.Context):
        def write_countdown_html():
            args = ctx.message.text.split()[1:]
            parts = tuple(int(x) for x in args[0].split(":"))
            if len(parts) == 2:
                m, s = parts
                # noinspection PyShadowingNames
                end_time = datetime.timedelta(minutes=m, seconds=s)
                end_time = datetime.datetime.now() + end_time
            elif len(parts) == 3:
                h, m, s = parts
                end_time = datetime.datetime.now().replace(hour=h, minute=m, second=s)
            else:
                self.bot.logger.error("Invalid call to countdown: {0}".format(args[0]))
                return

            self.bot.countdown_to = end_time

            with codecs.open(
                self.htmlfile.replace("html", "template"), encoding="UTF-8"
            ) as f:
                lines = f.read()

            lines = lines.replace("@@date@@", end_time.isoformat())
            with codecs.open(self.htmlfile, "w", encoding="UTF-8") as f:
                f.write(lines)

        write_countdown_html()
        logger.info("Waiting for setup_() to complete...")
        await self.event.wait()
        logger.info("Done waiting for setup_()")

        self.ws.call(obsws_requests.SetStudioModeEnabled(studioModeEnabled=False))

        # Refresh countdown
        self.ws.call(obsws_requests.SetCurrentProgramScene(sceneName="Starting"))
        self.show_hide_scene_item("Starting", "Countdown v3", False)
        time.sleep(1)
        self.show_hide_scene_item("Starting", "Countdown v3", True)

        # TODO: VR
        # try:
        #     self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), True))
        # except KeyError:
        #     logger.warning("[WARN] Can't mute mic-2, please check!")
        # self.ws.call(obsws_requests.SetMute(source="Mic", mute=True))

        self.ws.call(
            obsws_requests.SetInputMute(
                inputName=self.aud_sources.getMic1(), inputMuted=True
            )
        )

        #        self.ws.call(
        #            obsws_requests.SetInputMute(
        #                inputName=self.aud_sources.getDesktop1(), inputMuted=True
        #            )
        #        )

        self.ws.call(
            obsws_requests.SetInputVolume(inputName="Радио", inputVolumeDb=-7.0)
        )
        self.ws.call(obsws_requests.SetInputMute(inputName="Радио", inputMuted=False))

        self.show_hide_scene_item("Starting", "Ожидание", False)
        self.show_hide_scene_item("Starting", "Ожидание 2", False)
        self.show_hide_scene_item("Starting", "Countdown v3", True)

        self.ws_call(obsws_requests.StartStream())

        await ctx.reply(
            "Начат обратный отсчёт до {0}!".format(self.bot.countdown_to.strftime("%X"))
        )

        asyncio.ensure_future(self.bot.my_run_commercial(self.bot.owner_id))

        now = datetime.datetime.now()
        dt = self.bot.countdown_to - now

        asyncio.ensure_future(self.hide_zeroes(dt.seconds))
        # @routines.routine(seconds=s, minutes=m, hours=h, wait_first=True,
        # iterations=1)

    async def hide_zeroes(self, seconds: int):
        await asyncio.sleep(seconds)
        if (
            self.ws.call(
                obsws_requests.GetCurrentProgramScene()
            ).getCurrentProgramSceneName()
            != "Starting"
        ):
            return

        self.show_hide_scene_item("Starting", "Ожидание", True)
        self.show_hide_scene_item("Starting", "Countdown v3", False)

    # noinspection PyUnusedLocal
    #    @is_broadcaster()
    #    @twitch_command_aliased(name="end", aliases=["fin", "конец", "credits"])
    #   async def end(self, ctx: commands.Context):
    #       api = self.bot.get_component("SLCog")
    #       if not api:
    #           return

    #       self.switch_to("End")
    #       try:
    # noinspection PyUnresolvedReferences
    #           api.roll_credits(self.streamlabs_oauth)
    #       except requests.HTTPError as exc:
    #           logger.error("Can't roll credits! " + str(exc))
    #           pass

    @is_broadcaster()
    @twitch_command_aliased(name="vr")
    async def toggle_vr(self, ctx: commands.Context):
        self.vr = not self.vr
        asyncio.ensure_future(
            ctx.send("VR-режим {0}".format("включен" if self.vr else "выключен"))
        )

    def switch_to(self, scene: str):
        # self.ws.call(obsws_requests.SetStudioModeEnabled(studioModeEnabled=True))
        self.ws.call(obsws_requests.SetCurrentProgramScene(sceneName=scene))
        # self.ws.call(obsws_requests.TriggerStudioModeTransition())
        time.sleep(5)
        # self.ws.call(obsws_requests.SetStudioModeEnabled(studioModeEnabled=False))

    def do_pause(self, ctx: typing.Optional[commands.Context], is_dinner: bool):
        # self.get_player()
        # self.player_play_pause()

        if self.ws is None:
            return

        self.ws_call(obsws_requests.PauseRecord())
        self.show_hide_scene_item("Paused", "ужин", is_dinner)
        self.ws.call(
            obsws_requests.SetInputSettings(
                inputName="Eating",
                inputSettings={
                    "file": (
                        r"/home/razumov/__Stream/Eating.PNG"
                        if is_dinner
                        else r"/home/razumov/__Stream/Обэд.png"
                    )
                },
                overlay=True,
            )
        )

        self.switch_to("Paused")
        # if self.vr:
        #     self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(), True))
        # else:
        self.ws.call(
            obsws_requests.SetInputMute(
                inputName=self.aud_sources.getMic1(), inputMuted=True
            )
        )

        self.ws.call(obsws_requests.SetInputMute(inputName="Радио", inputMuted=False))
        # self.get_chatters()
        if ctx:
            asyncio.ensure_future(ctx.send("Начать перепись населения!"))

        asyncio.ensure_future(self.bot.my_run_commercial(ctx.broadcaster.id, 60))

    @is_broadcaster()
    @twitch_command_aliased(name="start")
    async def start_(self, ctx: commands.Context):
        """
        Начало трансляции. Аналог resume но без подсчёта зрителей

        %%start
        """
        if self.ws is None:
            return

        self.ws.call(obsws_requests.SetInputMute(inputName="Радио", inputMuted=True))

        if self.bot.game.use_game_capture:
            self.show_hide_scene_item("Game", "Game Capture", True)
            self.show_hide_scene_item("Game", "Window Capture", False)
            if self.bot.game.window != "X":
                source: obsws_requests.GetInputSettings = self.ws.call(
                    obsws_requests.GetInputSettings(inputName="Game Capture")
                )
                settings = source.getInputSettings()
                parts = self.bot.game.window.split("\r\n")
                while len(parts) < 3:
                    parts.append("")

                win = OBSCog.find_window_by_title_and_class(
                    parts[1], parts[2], self.bot.game.window_inexact
                )
                if win is None:
                    logger.error(
                        f"Can't find window title={parts[1]}, class={parts[2]}!"
                    )
                    await ctx.send("Окно игры не найдено")
                else:
                    settings["capture_window"] = f"{win.id}"
                    self.ws.call(
                        obsws_requests.SetInputSettings(
                            inputName="Game Capture",
                            inputSettings=settings,
                            overlay=False,
                        )
                    )
                    await ctx.send("Захват окна настроен")
                    logger.debug(f"Set capture window to {settings['capture_window']}")
        else:
            self.show_hide_scene_item("Game", "Game Capture", False)
            self.show_hide_scene_item("Game", "Window Capture", True)

        scene_obj: SourceConfig
        for scene_obj in SourceConfig.select():
            self.show_hide_scene_item(scene_obj.scene, scene_obj.source, False)

        for scene_obj in self.bot.game.sources:
            self.show_hide_scene_item(
                scene_obj.scene, scene_obj.source, scene_obj.state
            )

        # if self.vr:
        #     self.switch_to("VR Game")
        # self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(),
        #                                     False))
        # else:
        if True:
            self.switch_to("Game")
            # self.ws.call(obsws_requests.SetMute(source="Mic", mute=False))
            self.ws.call(
                obsws_requests.SetInputMute(
                    inputName=self.aud_sources.getMic1(), inputMuted=False
                )
            )
        self.ws.call(
            obsws_requests.SetInputMute(
                inputName=self.aud_sources.getDesktop1(), inputMuted=False
            )
        )

        await asyncio.sleep(5)

        self.ws_call(obsws_requests.StartRecord())

    async def do_resume(self, ctx: typing.Optional[commands.Context]):
        if self.ws is None:
            return

        old_screne = self.ws.call(obsws_requests.GetCurrentProgramScene())

        self.show_hide_scene_item("Paused", "ужин", False)

        # TO DO: VR
        # if self.vr:
        #     self.switch_to("VR Game")
        #     # self.ws.call(obsws_requests.SetMute(self.aud_sources.getMic2(),
        #     # False))
        # else:
        self.ws.call(obsws_requests.SetInputMute(inputName="Радио", inputMuted=True))

        self.ws.call(
            obsws_requests.SetInputMute(
                inputName=self.aud_sources.getMic1(), inputMuted=False
            )
        )

        self.ws.call(
            obsws_requests.SetInputMute(
                inputName=self.aud_sources.getDesktop1(), inputMuted=False
            )
        )

        res = self.ws.call(obsws_requests.GetRecordStatus())
        # If recording was stopped, start it again,
        # Otherwise, resume it
        if res.getOutputActive():
            self.ws_call(obsws_requests.ResumeRecord())
        else:
            self.ws_call(obsws_requests.StartRecord())

        if old_screne.name == "Battle":
            return

        self.switch_to("Game")

        try:
            res = await self.bot.my_get_stream()
            viewers = numeral.get_plural(
                res.viewer_count, ("зритель", "зрителя", "зрителей")
            )
            msg = (
                f"Перепись населения завершена успешно! Население стрима "
                f"составляет {viewers}"
            )

            if ctx:
                asyncio.ensure_future(ctx.send(msg))

            # self.bot.get_game_v5()
            return msg
        except (KeyError, TypeError) as exc:
            print(traceback.format_exc())
            msg = "Перепись населения не удалась :("
            if ctx:
                asyncio.ensure_future(ctx.send(msg))
            logger.error(str(exc))
            return msg

    @is_broadcaster()
    @twitch_command_aliased(name="resume")
    async def resume(self, ctx: commands.Context):
        """
        Отменяет перерыв

        %%resume
        """

        await self.do_resume(ctx)

    @is_broadcaster()
    @twitch_command_aliased(name="pause", aliases=("break",))
    async def pause(self, ctx: commands.Context):
        """
        Запускает перерыв

        %%pause
        """

        self.show_hide_scene_item("Paused", "Eating", False)
        self.show_hide_scene_item("Paused", "Pause", True)
        self.do_pause(ctx, False)

    @is_broadcaster()
    @twitch_command_aliased(name="ужин")
    async def dinner(self, ctx: commands.Context):
        """
        Ужин - особый тип перерыва, при котором показывается сообщение об ужине

        %%ужин
        """

        try:
            arg = ctx.message.text.split()[1]
        except IndexError:
            dt = datetime.datetime.now()
            dt += datetime.timedelta(hours=1)
            arg = dt.strftime("%H:%M")

        self.ws.call(
            obsws_requests.SetInputSettings(
                inputName="ужин",
                inputSettings={"text": f"Ужин, продолжим примерно в {arg} мск"},
                overlay=True,
            )
        )

        self.ws.call(
            obsws_requests.SetInputSettings(
                inputName="Eating",
                inputSettings={"file": "/home/razumov/__Stream/Eating.PNG"},
                overlay=True,
            )
        )

        self.show_hide_scene_item("Paused", "Eating", True)
        self.show_hide_scene_item("Paused", "Pause", False)

        self.do_pause(ctx, True)

    @is_broadcaster()
    @twitch_command_aliased(name="обед")
    async def lunch(self, ctx: commands.Context):
        """
        Обед - особый тип перерыва, при котором показывается сообщение об обеде

        %%обед
        """

        try:
            arg = ctx.message.text.split()[1]
        except IndexError:
            dt = datetime.datetime.now()
            dt += datetime.timedelta(hours=1)
            arg = dt.strftime("%H:%M")

        self.ws.call(
            obsws_requests.SetInputSettings(
                inputName="ужин",
                inputSettings={"text": f"Обед, продолжим примерно в " f"{arg} мск"},
                overlay=True,
            )
        )

        self.ws.call(
            obsws_requests.SetInputSettings(
                inputName="Eating",
                inputSettings={"file": "/home/razumov/__Stream/Обэд.png"},
                overlay=True,
            )
        )

        self.show_hide_scene_item("Paused", "Eating", True)
        self.show_hide_scene_item("Paused", "Pause", False)

        self.do_pause(ctx, True)

    async def enable_rip(self, state):
        # self.show_hide_scene_item("Game", "RIP", state)
        pass

    @is_broadcaster()
    @twitch_command_aliased(name="save")
    async def save_window(self, ctx: commands.Context):
        if self.bot.game is None:
            self.bot.get_game_v5()

        source = self.ws.call(obsws_requests.GetInputSettings(inputName="Game Capture"))

        settings = source.getInputSettings()

        self.bot.game.window = settings["capture_window"]
        self.bot.game.save()
        asyncio.ensure_future(ctx.send(f"Настройки захвата {self.game} сохранены"))

    @is_broadcaster()
    @twitch_command_aliased(name="глаза", aliases=["eyes", "глоза"])
    async def eyes(self, ctx: commands.Context):
        await ctx.send("ГЛАЗААААА!!!")
        await self.bot.play_sound("my_sound//EYES1.mp3")

    @twitch_command_aliased(name="камень", aliases=["stone", "rock"])
    async def stone(self, ctx: commands.Context):
        await self.bot.play_sound("my_sound//Камень я не дам.mp3")

    @twitch_command_aliased(name="непонимаю", aliases=["колобки", "колобок"])
    async def confused(self, ctx: commands.Context):
        await self.bot.play_sound("my_sound//Ничего не понимаю.mp3")

    @is_broadcaster()
    @twitch_command_aliased(name="end", aliases=["shutdown", "shitdown"])
    async def end_(self, ctx: commands.Context):
        await ctx.reply("💤")
        open("shutdown", "w").close()

    # noinspection PyMethodMayBeStatic
    async def sante_custom_key(ctx: commands.Context) -> typing.Hashable | None:
        return 1

    @twitch_command_aliased(
        name="sante", aliases=("буд", "будь", "будароф", "бударофф")
    )
    @commands.cooldown(rate=1, per=30, key=sante_custom_key)
    async def sante(self, ctx: commands.Context):
        await self.bot.play_sound("my_sound//Sante.mp3")

    @twitch_command_aliased(name="эксперименты")
    @commands.cooldown(rate=1, per=60, key=sante_custom_key)
    async def experiment(self, ctx: commands.Context):
        # await self.bot.play_sound("my_sound//Sante.mp3")
        i = random.randint(1, 8)

        await self.bot.play_sound(f"my_sound//experiments_{i}.mp3")


async def setup(bot: commands.Bot):
    await bot.add_component(OBSCog(bot))
