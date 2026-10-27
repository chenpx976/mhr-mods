import asyncio
from pathlib import Path
import sys

# Decky launches the backend from a temporary Python loader.
sys.path.insert(0, str(Path(__file__).parent))
from manager import ModManager
from environment import EnvironmentGuard

ROOT = Path("/home/deck/.local/share/Steam/steamapps/common/MonsterHunterRise")
BACKUPS = Path("/home/deck/Downloads/02-GameMods/04-MH-Rise/Backups")


class Plugin:
    def __init__(self):
        self.manager = ModManager(ROOT, BACKUPS)
        self.lock = asyncio.Lock()
        self.environment = EnvironmentGuard(self.manager, Path("/home/deck/.local/share/Steam"),
            Path("/home/deck/.local/share/mhr-mods/repair-assets"))
        self.repair_task = None
        self.repair_job = {"state": "idle", "message": "", "backup": ""}
        self.environment_status = None

    async def get_status(self):
        async with self.lock:
            try:
                status = await asyncio.to_thread(self.manager.status)
                if self.repair_job["state"] != "running":
                    self.environment_status = await asyncio.to_thread(self.environment.status)
                status["environment"] = {**(self.environment_status or {}), "job": dict(self.repair_job)}
                return status
            except Exception as e:
                return {"ok": False, "error": str(e)}

    async def set_enabled(self, mod_id: str, enabled: bool):
        async with self.lock:
            try:
                if self.repair_job["state"] == "running":
                    raise ValueError("正在修复环境，请等待完成后再切换 Mod")
                status = await asyncio.to_thread(self.manager.set_enabled, mod_id, enabled)
                self.environment_status = await asyncio.to_thread(self.environment.status)
                status["environment"] = {**self.environment_status, "job": dict(self.repair_job)}
                return status
            except Exception as e:
                return {"ok": False, "error": str(e)}

    async def repair_environment(self):
        async with self.lock:
            if self.repair_job["state"] != "running":
                try:
                    await asyncio.to_thread(self.environment.assert_idle)
                    self.environment_status = await asyncio.to_thread(self.environment.status)
                    if not self.environment_status["healthy"] and not self.environment_status["can_repair"]:
                        raise ValueError("请先处理检查列表中需要人工核对的项目")
                    self.repair_job = {"state": "running", "message": "正在准备备份…", "backup": ""}
                    self.repair_task = asyncio.create_task(self._repair_environment())
                except Exception as e:
                    return {"ok": False, "error": str(e)}
        return await self.get_status()

    async def _repair_environment(self):
        loop = asyncio.get_running_loop()
        def progress(**update):
            loop.call_soon_threadsafe(self.repair_job.update, update)
        try:
            message = await asyncio.to_thread(self.environment.repair, progress)
            self.repair_job.update(state="done", message=message)
        except Exception as e:
            self.repair_job.update(state="failed", message=str(e))

    async def _main(self):
        pass

    async def _unload(self):
        if self.repair_task and not self.repair_task.done():
            await asyncio.shield(self.repair_task)
