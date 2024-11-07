import asyncio
import os
import sys
from pathlib import Path

from loguru import logger
from twitchio.ext import commands
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from cogs.mycog import MyCog
from twitch_commands import twitch_command_aliased

sys.path.append("..")
from config import rippers


class CustomFileChangeHandler(FileSystemEventHandler):
    def __init__(self, cog, file_to_watch):
        self.cog = cog
        self.file_to_watch = file_to_watch

    def on_modified(self, event):
        # Check if the event corresponds to the file we are watching
        if event.src_path == self.file_to_watch:
            self.cog.on_watchdog()


class RIPCog(MyCog):
    def __init__(self, bot):
        self.bot = bot

        # Forwarding functions from bot
        self.check_sender = self.bot.check_sender

        self.deaths = {"today": 0, "total": 0}
        self.rip_emoji = ""

        self.obscog = None
        self.observer = None

    def setup(self):
        self.obscog = self.bot.get_cog("OBSCog")

    def update(self):
        self.deaths = {"today": 0, "total": self.bot.game.rip_total}
        self.rip_emoji = self.bot.game.rip_emoji
        enabled = self.bot.game.rip_enabled
        asyncio.ensure_future(self.obscog.enable_rip(enabled))
        asyncio.ensure_future(self.display_rip())
        if self.observer and not self.bot.game.watchfile:
            self.observer.stop()
            self.observer.join()
            self.observer = None

        if self.bot.game.watchfile and os.path.exists(self.bot.game.watchfile):
            if self.observer:
                self.observer.stop()
                self.observer.join()
            event_handler = CustomFileChangeHandler(self, self.bot.game.watchfile)
            self.observer = Observer()
            self.observer.schedule(
                event_handler,
                path=Path(self.file_to_watch).parent,
                recursive=False,
            )

    def on_watchdog(self):
        with open(self.bot.game.watchfile) as f:
            tmp = int(f.readline().strip())

        new_deaths = tmp - self.deaths[1]
        self.deaths[0] += new_deaths
        self.write_rip()

    async def display_rip(self, n=0):
        if self.game.inexact:
            text = f"{self.rip_emoji}: {{today}}+ (всего: ≈{{total}})".format(
                **self.deaths
            )
        else:
            if self.game.infinite:
                text = f"{self.rip_emoji}: ∞"
            else:
                text = f"{self.rip_emoji}: {{today}} (всего: {{total}})".format(
                    **self.deaths
                )

        with open("rip_display.txt", "w", encoding="utf8") as f:
            f.write(text)

        logger.info(f"animation {n} {0 if n == 0 else n // abs(n)}")
        if self.bot.sio_server:
            data = {
                "text": text,
                "animation": 0 if n == 0 else n // abs(n),
            }
            await self.sio_server.emit("update_death_count", data)

    async def write_rip(self, n=0):
        await self.display_rip(n)
        self.game.rip_total = self.deaths["total"]
        self.game.save()

    async def do_rip(self, n=1):
        self.deaths["today"] += n
        self.deaths["total"] += n

        await self.write_rip(n)

        return (
            "iarspiRip {today}".format(**self.deaths)
            if n > 0
            else "MercyWing1 PinkMercy MercyWing2"
        )

    @twitch_command_aliased(name="infrip", aliases=("ripinf", "infinity"))
    async def infrip(self, ctx: commands.Context):
        """
        "бесконечные" смерти (если стример сдался и включил читы)
        """
        if not self.check_sender(ctx, "iarspider"):
            return

        self.game.infinite = True
        asyncio.ensure_future(ctx.send(f"{self.rip_emoji} → ∞"))
        await self.write_rip()

    @twitch_command_aliased(name="xrip", aliases=("ripx",))
    async def inexrip(self, ctx: commands.Context):
        """
        "неточные" смерти (если чатик сдался и перестал считать читы)
        """
        if not self.check_sender(ctx, "iarspider"):
            return

        self.game.inexact = True
        asyncio.ensure_future(ctx.send(f"{self.rip_emoji} x много"))

    @twitch_command_aliased(name="rip", aliases=("смерть", "рып", "рип"))
    async def rip(self, ctx: commands.Context):
        """
        Счётчик смертей

        %% rip
        """
        args = ctx.message.content.split()[1:]
        if args and (args[0] == "who" or args[0] == "?"):
            ans = "Счетоводы: " + ", ".join(rippers)
            asyncio.ensure_future(ctx.send(ans))
            return

        if not (
            ctx.author.is_mod or ctx.author.is_vip or ctx.author.name.lower() in rippers
        ):
            asyncio.ensure_future(ctx.send("Эту кнопку не трожь!"))
            return

        if args and args[0].startswith("+"):
            try:
                n_rip = int(args[0])
            except ValueError:
                n_rip = 1
        else:
            n_rip = 1

        n_rip = max(1, n_rip)
        ans = await self.do_rip(n=n_rip)
        asyncio.ensure_future(ctx.send(ans))

    @twitch_command_aliased(name="unrip")
    async def unrip(self, ctx: commands.Context):
        """
        Отмена смерти
        """
        if not self.check_sender(ctx, "iarspider"):
            return

        msg = await self.do_rip(n=-1)

        asyncio.ensure_future(ctx.send(msg))

    @twitch_command_aliased(name="enrip")
    async def enrip(self, ctx: commands.Context):
        """
        Временно (до перезапуска бота) добавляет пользователя в rip-список
        """
        if not self.check_sender(ctx, "iarspider"):
            return

        args = ctx.message.content.split()[1:]
        if len(args) != 1:
            asyncio.ensure_future(ctx.send("Неправильный запрос"))
        rippers.append(args[0].lower())

        asyncio.ensure_future(ctx.send("{0} TwitchVotes ".format(args[0])))

    @twitch_command_aliased(name="lrip")
    async def lrip(self, ctx: commands.Context):
        """
        Перезагружает счётчик смертей (в случае смены игры)
        """
        if not self.check_sender(ctx, "iarspider"):
            logger.info("check_sender failed")
            return

        self.get_game_v5()
        await ctx.send("Счётчик смертей обновлён")

    @twitch_command_aliased(name="setrip")
    async def setrip(self, ctx: commands.Context):
        """
        Устанавливает значение счётчика смертей за сегодня
        """
        if not self.check_sender(ctx, "iarspider"):
            logger.info("check_sender failed")
            return

        try:
            arg = int(ctx.message.content.split()[1])
        except (IndexError, ValueError):
            await ctx.send("Usage: !setrip <N>")
            return
        else:
            self.deaths["today"] = arg
            if self.deaths["total"] == 0:
                self.deaths["total"] = arg
            await self.display_rip()

    @twitch_command_aliased(name="yesrip")
    async def yesrip(self, ctx: commands.Context):
        """
        Включает отображение смертей
        """
        if not self.check_sender(ctx, "iarspider"):
            logger.info("check_sender failed")
            return

        self.bot.game.rip_enabled = True
        self.bot.game.save()

        if self.bot.sio_server:
            await self.bot.sio_server.emit("toggle_death_counter", 1)
        else:
            await self.obscog.enable_rip(True)

        await ctx.send("Счётчик смертей активирован")

    @twitch_command_aliased(name="norip")
    async def norip(self, ctx: commands.Context):
        """
        Выключает отображение смертей
        """
        if not self.check_sender(ctx, "iarspider"):
            logger.info("check_sender failed")
            return

        self.bot.game.rip_enabled = False
        self.bot.game.save()

        if self.bot.sio_server:
            await self.bot.sio_server.emit("toggle_death_counter", 0)
        else:
            await self.obscog.enable_rip(False)
        await ctx.send("Счётчик смертей отключён")

    # @twitch_command_aliased(name='ripz')
    # async def ripz(self, ctx: commands.Context):
    #     """
    #         Счётчик смертей
    #
    #         %% ripz
    #     """
    #     await self.do_rip(ctx, "#Отзомбячено!")
    #
    # @twitch_command_aliased(name='riph')
    # async def riph(self, ctx: commands.Context):
    #     """
    #         Счётчик смертей
    #
    #         %% riph
    #     """
    #     await self.do_rip(ctx, "#Захедкраблено")
    #
    # @twitch_command_aliased(name='ripc')
    # async def ripc(self, ctx: commands.Context):
    #     """
    #         Счётчик смертей
    #
    #         %% ripc
    #     """
    #     await self.do_rip(ctx, "#Укомбайнено")
    #
    # @twitch_command_aliased(name='ripb')
    # async def ripb(self, ctx: commands.Context):
    #     """
    #         Счётчик смертей
    #
    #         %% ripb
    #     """
    #     await self.do_rip(ctx, "#Барнакнуто")
    #
    # @twitch_command_aliased(name='ripn', aliases=('nom', 'omnomnom', 'ном', 'ням',
    # 'омномном'))
    # async def nom(self, ctx: commands.Context):
    #     await self.do_rip(ctx, 'Ом-ном-ном!')


def prepare(bot: commands.Bot):
    bot.add_cog(RIPCog(bot))
