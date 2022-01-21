import asyncio
from contextlib import suppress


class Timer:
    def __init__(self, timeout, callback, loop):
        self._timeout = timeout
        self._callback = callback
        self._task = asyncio.ensure_future(self._job(), loop=loop)

    async def _job(self):
        await asyncio.sleep(self._timeout)
        await self._callback()

    def cancel(self):
        self._task.cancel()

class Periodic:
    def __init__(self, name, timeout, callback, loop):
        self.func = callback
        self.time = timeout
        self.is_started = False
        self._task = None
        self.loop = loop
        self.name = name
        # if autostart:
        #     asyncio.ensure_future(self.start(), loop=self.loop)

    async def start(self):
        print(f">> start {self.name} <<")
        if not self.is_started:
            self.is_started = True
            print(f">> starting {self.name} <<")
            # Start task to call func periodically:
            self._task = asyncio.ensure_future(self._run(), loop=self.loop)
            print(f">> started {self.name} <<")

    async def stop(self):
        if self.is_started:
            self.is_started = False
            # Stop task and await it stopped:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _run(self):
        # print(f">> run {self.name} <<")
        while True:
            await asyncio.sleep(self.time)
            # print(f">> exec {self.name} <<")
            # await self.func
            self.func()
            # print(f">> sleep {self.name} <<")

