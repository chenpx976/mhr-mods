"""Local, reversible MHR mod switches. No shell commands or executable downloads."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

APP_ID = 1446780
SPECS = {
    "framework": ("REFramework", "脚本框架；关闭前请先关闭依赖它的 Mod", "Nightly 1433", []),
    "overlay": ("MHR Overlay", "怪物血量、伤害统计与状态显示", "2.7.4", ["framework"]),
    "d2d": ("Direct2D", "文字与图形绘制；本机已修复运行库，建议保持开启", "1.4.1", ["framework"]),
    "birds": ("SpiritBirds", "任务开始自动生成虹色鬼火鸟；保留现有设置", "1.9", ["framework"]),
    "skip_dango": ("跳过团子动画", "Skip Dango Song", "1.5.0", ["framework"]),
    "fast_return": ("跳过任务结束倒计时", "L3 跳过返程倒计时，R3 跳过结束动画；手动触发", "1.5.1hotfix2", ["framework"]),
    "killcam": ("去击杀镜头与终结慢动作", "移除击杀镜头；慢动作已关闭，保留正常游戏界面", "2.6", ["framework"]),
    "weakness": ("怪物弱点图标", "Monster Weakness Icon Indicator", "Final", []),
    "all_dango": ("团子每日常驻", "All Dango All the Time", "1.0", []),
    "vip_dango": ("VIP 团子券", "原文件在游戏根目录；首次开启会修正加载位置", "1.3.1", ["framework"]),
}
FIXED = {
    "framework": ["dinput8.dll"],
    "d2d": ["reframework/autorun/reframework-d2d.lua", "reframework/plugins/reframework-d2d.dll"],
    "birds": ["reframework/autorun/SpiritBirds.lua"],
    "skip_dango": ["reframework/autorun/skip_dango_song.lua", "reframework/autorun/Skip Dango Song/mod_utils.lua"],
    "fast_return": [
        "reframework/autorun/bth.lua",
        "reframework/autorun/bth/keyboardkeys.lua",
        "reframework/autorun/bth/nintendokeys.lua",
        "reframework/autorun/bth/padkeys.lua",
        "reframework/autorun/bth/playstationkeys.lua",
        "reframework/autorun/bth/xboxkeys.lua",
        "reframework/images/mhrpopup.png",
    ],
    "weakness": ["re_chunk_000.pak.patch_007.pak"],
    "killcam": ["reframework/autorun/NoKillCam+SlowMo.lua"],
    "all_dango": ["natives/STM/data/Define/Lobby/Facility/Kitchen/DangoBaseData.user.2"],
    "vip_dango": ["reframework/autorun/VIP_Dango_Ticket.lua"],
}


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    previous = path.stat() if path.exists() else None
    with tmp.open("w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        if previous is not None:
            os.fchmod(f.fileno(), previous.st_mode & 0o777)
            if hasattr(os, "fchown"):
                os.fchown(f.fileno(), previous.st_uid, previous.st_gid)
        os.fsync(f.fileno())
    os.replace(tmp, path)


def fluffy_running(proc=Path("/proc")):
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            args = (p / "cmdline").read_bytes().split(b"\0")
            if any(Path(x.decode(errors="ignore")).name.lower() == "modmanager.exe" for x in args):
                return True
        except OSError:
            continue
    return False


def game_running(proc=Path("/proc")):
    # Proton comm names are truncated; cmdline and environment cover both Wine and Proton.
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            cmd = (p / "cmdline").read_bytes().split(b"\0")
            if any(Path(x.decode(errors="ignore")).name.lower() == "monsterhunterrise.exe" for x in cmd):
                return True
            env = (p / "environ").read_bytes().split(b"\0")
            if b"SteamAppId=1446780" in env or b"SteamGameId=1446780" in env:
                return True
        except (OSError, PermissionError):
            continue
    return False


class ModManager:
    def __init__(self, root: Path, backup_root: Path, running=game_running, other_running=fluffy_running):
        self.root = root.resolve()
        self.backup_root = backup_root
        self.running = running
        self.other_running = other_running
        self.store = self.root / ".mhrmods"
        self.state_file = self.store / "state.json"
        self.journal = self.store / "transaction.json"

    def safe(self, base: Path, rel: str):
        p = base / rel
        if Path(rel).is_absolute() or ".." in Path(rel).parts or not p.resolve().is_relative_to(base.resolve()):
            raise ValueError("不安全的 Mod 路径")
        # Do not follow symlinks, including parent directories, even within the game.
        cursor = p
        while cursor != base:
            if cursor.is_symlink():
                raise ValueError("Mod 路径不能是符号链接")
            cursor = cursor.parent
        return p

    def load(self):
        if not (self.root / "MonsterHunterRise.exe").is_file():
            raise ValueError("没有找到 Monster Hunter Rise 游戏目录")
        state = json.loads(self.state_file.read_text()) if self.state_file.exists() else {"files": {}, "last_backup": ""}
        for key, files in FIXED.items():
            state["files"].setdefault(key, files)
        if "overlay" not in state["files"]:
            files = []
            for path in [self.root / "reframework/autorun/MHR_Overlay", self.root / "reframework/data/MHR Overlay/languages", self.root / "reframework/fonts"]:
                if path.is_dir():
                    files += [str(p.relative_to(self.root)) for p in path.rglob("*") if p.is_file() and not p.name.startswith(".")]
            if (self.root / "reframework/autorun/MHR_Overlay.lua").exists():
                files.append("reframework/autorun/MHR_Overlay.lua")
            state["files"]["overlay"] = sorted(files)
        # Only known assets may ever be moved. User configs are deliberately excluded.
        for key, paths in state["files"].items():
            if key not in SPECS:
                raise ValueError("未知 Mod 状态")
            for rel in paths:
                if key == "overlay":
                    valid = rel == "reframework/autorun/MHR_Overlay.lua" or any(rel.startswith(prefix) for prefix in ["reframework/autorun/MHR_Overlay/", "reframework/data/MHR Overlay/languages/", "reframework/fonts/"])
                else:
                    valid = rel in FIXED[key]
                if not valid:
                    raise ValueError("Mod 清单包含非管理文件")
                self.safe(self.root, rel)
                self.safe(self.store / "disabled" / key, rel)
        return state

    def recover(self):
        if not self.journal.exists():
            return
        if self.running():
            raise ValueError("有未完成的切换，请退出 MHR 后刷新以恢复")
        data = json.loads(self.journal.read_text())
        # Validate every journal path before changing any file.
        moves = []
        for move in data["moves"]:
            a, b = self.safe(self.root, move[0]), self.safe(self.root, move[1])
            if not (str(a.relative_to(self.root)).startswith(".mhrmods/") or str(b.relative_to(self.root)).startswith(".mhrmods/")):
                raise ValueError("无效的恢复记录")
            moves.append((a, b))
        for a, b in reversed(moves):
            if b.exists() and not a.exists():
                a.parent.mkdir(parents=True, exist_ok=True)
                os.replace(b, a)
            elif b.exists() and a.exists():
                raise ValueError("恢复时发现冲突文件，请保留备份并人工检查")
        self.journal.unlink()

    def status(self):
        self.recover()
        state = self.load()
        mods = []
        for key, (name, description, version, requires) in SPECS.items():
            files = state["files"][key]
            live = sum(self.safe(self.root, p).is_file() for p in files)
            parked = sum(self.safe(self.store / "disabled" / key, p).is_file() for p in files)
            legacy = key == "vip_dango" and self.safe(self.root, "VIP_Dango_Ticket.lua").is_file()
            enabled = bool(files) and live == len(files) and parked == 0
            off = bool(files) and live == 0 and parked == len(files)
            available = enabled or off or (legacy and live == 0 and parked == 0)
            mods.append(dict(id=key, name=name, description=description, version=version,
                             enabled=enabled, available=available, requires=requires,
                             detail="" if available else "文件缺失或状态混合，已锁定；请先检查安装"))
        return dict(ok=True, game_path=str(self.root), running=self.running(), mods=mods,
                    last_backup=state.get("last_backup", ""))

    def snapshot(self, state):
        target = self.backup_root / (time.strftime("decky-%Y%m%d-%H%M%S") + "-" + str(time.time_ns() % 1000000))
        target.mkdir(parents=True, exist_ok=False)
        entries = ["reframework", "natives", ".mhrmods", "dinput8.dll", "VIP_Dango_Ticket.lua", "re2_fw_config.txt", "ref_ui.ini", "config.ini", "re_chunk_000.pak.patch_007.pak"]
        for rel in entries:
            src = self.safe(self.root, rel)
            if src.is_dir():
                shutil.copytree(src, target / rel, symlinks=True)
            elif src.is_file():
                shutil.copy2(src, target / rel)
        # A path/hash manifest makes every automatic backup auditable.
        hashes = {str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob("*") if p.is_file() and not p.is_symlink()}
        atomic_json(target / "sha256.json", hashes)
        state["last_backup"] = str(target)
        return target

    def set_enabled(self, mod_id: str, enabled: bool):
        if type(enabled) is not bool or mod_id not in SPECS:
            raise ValueError("无效的 Mod 或开关值")
        if self.running():
            raise ValueError("请先退出 Monster Hunter Rise，再切换 Mod")
        if self.other_running():
            raise ValueError("请先关闭 Fluffy Mod Manager，再切换 Mod")
        self.recover()
        state = self.load()
        status = self.status()
        mods = {m["id"]: m for m in status["mods"]}
        mod = mods[mod_id]
        if not mod["available"]:
            raise ValueError(mod["detail"])
        if mod["enabled"] == enabled:
            return status
        if enabled:
            missing = [mods[k]["name"] for k in mod["requires"] if not mods[k]["enabled"]]
            if missing:
                raise ValueError("请先开启：" + "、".join(missing))
        else:
            dependents = [m["name"] for m in mods.values() if m["enabled"] and mod_id in m["requires"]]
            if dependents:
                raise ValueError("请先关闭：" + "、".join(dependents))
        moves = []
        for rel in state["files"][mod_id]:
            live = self.safe(self.root, rel)
            parked = self.safe(self.store / "disabled" / mod_id, rel)
            a, b = (parked, live) if enabled else (live, parked)
            if enabled and mod_id == "vip_dango" and not a.exists():
                a = self.safe(self.root, "VIP_Dango_Ticket.lua")
            if not a.is_file() or b.exists():
                raise ValueError("文件状态已变化，请刷新后重试")
            moves.append((a, b))
        # Backup and preflight before the first mutation; check for a launch during backup.
        self.snapshot(state)
        if self.running():
            raise ValueError("MHR 刚刚启动，已取消切换")
        atomic_json(self.journal, {"moves": [[str(a.relative_to(self.root)), str(b.relative_to(self.root))] for a, b in moves]})
        try:
            for a, b in moves:
                b.parent.mkdir(parents=True, exist_ok=True)
                os.replace(a, b)
            atomic_json(self.state_file, state)
        except Exception:
            self.recover()
            raise
        self.journal.unlink()
        return self.status()
