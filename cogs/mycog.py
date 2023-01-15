from loguru import logger
from twitchio.ext import commands


class MyCog(commands.Cog):
    def setup(self):
        pass

    def update(self):
        pass

    def __getattr__(self, item):
        if item != "__bases__":
            logger.warning(
                f"[{self.__class__}] Failed to get attribute {item}, redirecting to "
                f"self.bot!"
            )
        return self.bot.__getattribute__(item)
