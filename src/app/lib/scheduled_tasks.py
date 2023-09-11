import asyncio
import threading
from abc import ABC, abstractmethod

from app.lib.db.base import get_connection
from app.lib.settings import get_settings

settings = get_settings()


class ScheduledTask(ABC):
    keep_running: bool

    def __init__(self) -> None:
        self.keep_running = True
        self.name = self.__class__.__name__

    def stop(self) -> None:
        print(f"Stopping {self.name} ...")
        self.keep_running = False

    async def run(self) -> None:
        t = threading.Thread(target=asyncio.run, args=(self._execute_loop(),), name=self.name, daemon=True)
        t.start()
        print(f"Starting Scheduler {self.name} - {self.keep_running=}")

    async def run_once(self) -> None:
        """Run the scheduled task once and quit.

        Mostly used for testing.
        """
        await self._execute()

    @abstractmethod
    async def _execute_loop(self) -> None:
        pass

    @abstractmethod
    async def _execute(self) -> None:
        pass


class TaskDeleteExpired(ScheduledTask):
    async def _execute_loop(self) -> None:
        try:
            while self.keep_running:
                await self._execute()
                await asyncio.sleep(settings.SCHEDULER_DELETE_EXPIRED_INTERVAL)
        except KeyboardInterrupt:
            self.keep_running = False

    async def _execute(self) -> None:
        """Delete expired CIDRs."""
        async for conn in get_connection():
            async with conn.transaction():
                res = await conn.execute("delete from cidr where expires_at < now()")
                print(f"Delete expired CIDRs task: {res}")


class Scheduler:
    """Scheduled tasks."""

    tasks: list[ScheduledTask]

    def __init__(self):
        self.tasks = [TaskDeleteExpired()]

    def stop(self):
        print("Stopping Scheduler.")
        for task in self.tasks:
            task.stop()

    async def run(self) -> None:
        """Start scheduled threads."""
        for task in self.tasks:
            await task.run()
