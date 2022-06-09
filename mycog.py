class MyCog:
    def setup(self):
        pass

    def update(self):
        pass

    def __getattr__(self, item):
        if item != '__bases__':
            self.logger.warning(f"[{self.__class__}] Failed to get attribute {item}, redirecting to self.bot!")
        return self.bot.__getattribute__(item)
