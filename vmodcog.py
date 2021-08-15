import asyncio
import warnings

from twitchio.ext import commands
from twitchio.ext.commands import Cog, Context

from singleton import Singleton

warnings.simplefilter("ignore", UserWarning)
try:
    import pywinauto

    warnings.resetwarnings()
except ImportError as e:
    print('Failed to import pywinauto: {0}'.format(e))
    pywinauto = None


class VMcog(Cog, metaclass=Singleton):
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger
        self.vmod = None
        self.vmod_active = False

        if pywinauto:
            self.get_voicemod()

    async def deactivate_voicemod(self):
        await asyncio.sleep(60)
        self.get_voicemod()
        # self.get_discord()
        if self.vmod is not None:
            self.vmod_active = False
            self.vmod.type_keys('%{VK_DIVIDE}', set_foreground=False)  # no voice

            # if self.get_discord() is not None:
            self.vmod.type_keys('%{VK_NUMPAD0}', set_foreground=False)  # unmute

    async def activate_voicemod(self):
        while self.vmod_active:
            await asyncio.sleep(5)

        self.bot.play_sound('vmod.mp3')

        self.get_voicemod()

        if self.vmod is not None:
            self.vmod.type_keys('%{VK_NUMPAD0}', set_foreground=False)  # mute
            self.vmod_active = True
            self.vmod.type_keys('%{VK_MULTIPLY}', set_foreground=False)  # random voice

        asyncio.ensure_future(self.deactivate_voicemod())

    def get_voicemod(self):
        if not pywinauto:
            return
        try:
            self.vmod = pywinauto.Application().connect(title="Voicemod Desktop").top_window().wrapper_object()
        except (pywinauto.findwindows.ElementNotFoundError, RuntimeError):
            self.logger.warning('Could not find VoiceMod Desktop window')

    @commands.command(name='vmod')
    async def vmod(self, ctx: Context):
        if ctx.author.name.lower() != 'iarspider':
            return

        await self.activate_voicemod()
