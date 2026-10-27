"""MHR environment health checks and an explicitly requested, backed-up repair."""
from __future__ import annotations
import hashlib
import json
import os
import shlex
import shutil
import struct
import subprocess
import tarfile
from pathlib import Path

from manager import APP_ID, FIXED, atomic_json

TESTED_RUNTIME = (14, 51, 36247, 0)
RUNTIME_DLLS = ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")
ASSET_HASHES = {
    "vc_redist.x64.exe": "843068991daaa1f73ad9f6239bce4d0f6a07a51f18c37ea2a867e9beca71295c",
    "reframework-d2d.dll": "0b64586c8e7903eb9cabd4b5c30c0544b528e3898aed9e44cb8f37e14246aa94",
    "reframework-d2d.lua": "e12acac7928b63c4849a2f5ca3e788be99814d5aac93c7bb5a73385b03909e43",
}


def file_version(path):
    """Read the PE version resource without loading a Windows executable."""
    try:
        data = path.read_bytes()
        start = data.find(struct.pack("<II", 0xFEEF04BD, 0x10000))
        if start < 0:
            return None
        ms, ls = struct.unpack_from("<II", data, start + 8)
        return ms >> 16, ms & 65535, ls >> 16, ls & 65535
    except (OSError, struct.error):
        return None


def version_text(version):
    return ".".join(map(str, version)) if version else "缺失或无法识别"


class EnvironmentGuard:
    def __init__(self, manager, steam: Path, assets: Path, installer=None):
        self.manager = manager
        self.steam = steam
        self.prefix = steam / "steamapps/compatdata" / str(APP_ID)
        self.assets = assets
        self.installer = installer or self.install_runtime
        self._hash_cache = {}
        self.last_backup = ""
        self.record_pointer = self.manager.store / "environment-repair.json"

    def digest(self, path):
        try:
            if path.is_symlink():
                return ""
            stat = path.stat()
            key = (str(path), stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            if key not in self._hash_cache:
                self._hash_cache = {k: v for k, v in self._hash_cache.items() if k[0] != str(path)}
                with path.open("rb") as f:
                    self._hash_cache[key] = hashlib.file_digest(f, "sha256").hexdigest()
            return self._hash_cache[key]
        except OSError:
            return ""

    def selected_config(self):
        root = self.manager.root
        selector = self.manager.safe(root, "reframework/data/MHR Overlay/config.json")
        name = json.loads(selector.read_text())["config"]
        if not isinstance(name, str) or not name or Path(name).name != name or name in (".", "..") or "\\" in name:
            raise ValueError("Overlay 配置名称无效")
        path = self.manager.safe(root, f"reframework/data/MHR Overlay/configs/{name}.json")
        config = json.loads(path.read_text())
        # Never replace a malformed user profile with generated defaults.
        if not isinstance(config.get("global_settings"), dict):
            raise ValueError("Overlay 配置结构无效")
        renderer = config["global_settings"].get("renderer", {})
        if not isinstance(renderer, dict):
            raise ValueError("Overlay 绘图配置无效")
        return path, config, renderer

    def status(self):
        if not self.last_backup and self.record_pointer.exists():
            try:
                self.last_backup = str(json.loads(self.record_pointer.read_text()).get("backup", ""))
            except (OSError, ValueError, AttributeError):
                pass
        checks = []
        def add(key, label, good, detail, fixable=False):
            checks.append(dict(id=key, label=label, healthy=good, detail=detail, fixable=fixable))
        exists = (self.prefix / "pfx/system.reg").is_file()
        add("prefix", "Proton 环境", exists, "已创建" if exists else "请先启动一次 MHR 并退出，以创建 Proton 环境")
        versions = {name: file_version(self.prefix / "pfx/drive_c/windows/system32" / name) for name in RUNTIME_DLLS}
        runtime_ok = all(v and v >= TESTED_RUNTIME and v[0] == 14 for v in versions.values())
        add("runtime", "VC++ x64 运行库", runtime_ok,
            "；".join(f"{name}: {version_text(v)}" for name, v in versions.items()), exists)
        for key, label in [("framework", "REFramework"), ("overlay", "MHR Overlay")]:
            rel = "dinput8.dll" if key == "framework" else "reframework/autorun/MHR_Overlay.lua"
            present = self.manager.safe(self.manager.root, rel).is_file()
            add(key, label, present, "已开启" if present else "请先在 Mod 列表开启或恢复此组件")
        for rel in FIXED["d2d"]:
            live = self.manager.safe(self.manager.root, rel)
            parked = self.manager.safe(self.manager.store / "disabled/d2d", rel)
            expected = ASSET_HASHES[live.name]
            unknown = any(p.exists() and self.digest(p) != expected for p in (live, parked))
            good = self.digest(live) == expected and not parked.exists()
            detail = "已开启 · 已验证的 1.4.1 文件" if good else (
                "与已验证版本不同：保留现有文件，请人工核对版本" if unknown else "未开启或文件缺失，可恢复已验证的 1.4.1 文件")
            add(live.name, "Direct2D · " + ("绘图组件" if live.suffix == ".dll" else "脚本"), good, detail, not unknown)
        try:
            path, _, renderer = self.selected_config()
            add("config", "Overlay 使用 Direct2D", renderer.get("use_d2d_if_available") is True, f"当前配置：{path.stem}", True)
        except (ValueError, KeyError, TypeError, OSError) as e:
            add("config", "Overlay 使用 Direct2D", False, "配置缺失或无法读取，请先运行 Overlay：" + str(e))
        assets_ok = all(self.digest(self.assets / name) == expected for name, expected in ASSET_HASHES.items())
        add("assets", "离线修复包", assets_ok, "校验通过，可离线修复" if assets_ok else "修复包缺失或校验失败，请重新安装 MHR Mods 插件")
        issues = [c for c in checks if not c["healthy"]]
        return dict(healthy=not issues, checks=checks, can_repair=bool(issues) and all(c["fixable"] for c in issues),
                    runtime_version=version_text(versions["msvcp140.dll"]), last_backup=self.last_backup,
                    tested_runtime=version_text(TESTED_RUNTIME))

    def assert_idle(self):
        if self.manager.running():
            raise ValueError("请先保存并退出 MHR，再修复环境")
        if self.manager.other_running():
            raise ValueError("请先关闭 Fluffy Mod Manager，再修复环境")

    def install_runtime(self, backup):
        # Use the user's Steam/Flatpak session, never root's prefix. Omit --no-term:
        # Protontricks then logs unavailable old SD libraries without a blocking dialog.
        exe = self.assets / "vc_redist.x64.exe"
        command = "wine " + shlex.quote(str(exe)) + " /install /quiet /norestart /log " + shlex.quote(r"C:\windows\temp\mhrmods-vcredist.log")
        args = ["flatpak", "run", "--env=DISPLAY=:1", "--filesystem=" + str(self.assets) + ":ro",
                "com.github.Matoking.protontricks", "-c", command, str(APP_ID)]
        if os.geteuid() == 0:
            args = ["runuser", "-u", "deck", "--"] + args
        env = {**os.environ, "DISPLAY": ":1", "XDG_RUNTIME_DIR": "/run/user/1000", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"}
        # Do not inherit a Decky/backend-specific HOME, Python or library search path.
        for key in ("PYTHONPATH", "PYTHONHOME", "LD_LIBRARY_PATH", "LD_PRELOAD", "WINEPREFIX", "WINE", "WINESERVER", "PROTON_VERSION"):
            env.pop(key, None)
        with (backup / "runtime-install.log").open("wb") as log:
            result = subprocess.run(args, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300, check=False)
        if result.returncode not in (0, 194):
            raise RuntimeError(f"运行库安装失败（{result.returncode}），请查看备份中的 runtime-install.log")

    def repair(self, progress=lambda **kwargs: None):
        self.assert_idle()
        self.manager.recover()
        before = self.status()
        if before["healthy"]:
            return "环境正常，无需修复"
        if not before["can_repair"]:
            raise ValueError("存在需要人工处理的项目；请先查看环境检查结果")
        state = self.manager.load()
        roots = [(self.prefix, f"compatdata/{APP_ID}")]
        userdata = self.steam / "userdata"
        if userdata.is_dir():
            roots += [(p / str(APP_ID), f"userdata/{p.name}/{APP_ID}") for p in userdata.iterdir()
                      if p.name.isdigit() and (p / str(APP_ID)).is_dir()]
        estimated = sum(p.stat().st_size for root, _ in roots for p in root.rglob("*") if p.is_file() and not p.is_symlink())
        self.manager.backup_root.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.manager.backup_root).free < estimated * 2 + 128 * 1024 * 1024:
            raise ValueError("备份空间不足，已取消修复")
        progress(message="正在备份 Mod、配置、Proton 环境与存档…")
        backup = self.manager.snapshot(state)
        self.last_backup = str(backup)
        progress(backup=str(backup))
        record = dict(state="backing_up", before=before, backup=str(backup))
        atomic_json(backup / "repair.json", record)
        atomic_json(self.record_pointer, record)
        try:
            with tarfile.open(backup / "compatdata-saves-before.tar.gz", "w:gz", dereference=False) as tar:
                for root, arcname in roots:
                    tar.add(root, arcname=arcname)
            with (backup / "compatdata-saves-before.tar.gz").open("rb") as f:
                atomic_json(backup / "prefix-sha256.json", {"compatdata-saves-before.tar.gz": hashlib.file_digest(f, "sha256").hexdigest()})
            # Catch a launch or an asset change while the backup was being made.
            self.assert_idle()
            fresh = self.status()
            if not fresh["can_repair"]:
                raise ValueError("环境状态已变化，请刷新后重试")
            record["state"] = "repairing"
            atomic_json(backup / "repair.json", record)
            atomic_json(self.record_pointer, record)
            if any(c["id"] == "runtime" and not c["healthy"] for c in fresh["checks"]):
                progress(message="备份完成，正在安装已验证的 VC++ x64 运行库…")
                self.installer(backup)
                if any((v := file_version(self.prefix / "pfx/drive_c/windows/system32" / name)) is None or v < TESTED_RUNTIME for name in RUNTIME_DLLS):
                    raise RuntimeError("安装器已结束，但运行库版本复核未通过")
            self.assert_idle()
            progress(message="正在恢复 Direct2D 并保留现有 Overlay 配置…")
            # Revalidate each target before overwriting/removing anything.
            for rel in FIXED["d2d"]:
                live = self.manager.safe(self.manager.root, rel)
                parked = self.manager.safe(self.manager.store / "disabled/d2d", rel)
                expected = ASSET_HASHES[live.name]
                if any(p.exists() and self.digest(p) != expected for p in (live, parked)):
                    raise ValueError("Direct2D 文件发生变化，已停止；备份已保留")
                if not live.exists():
                    live.parent.mkdir(parents=True, exist_ok=True)
                    tmp = live.with_suffix(live.suffix + ".repair-tmp")
                    shutil.copy2(self.assets / live.name, tmp)
                    os.replace(tmp, live)
                if parked.exists():
                    parked.unlink()
            path, config, _ = self.selected_config()
            config["global_settings"].setdefault("renderer", {})["use_d2d_if_available"] = True
            atomic_json(path, config)
            atomic_json(self.manager.state_file, state)
            after = self.status()
            if not after["healthy"]:
                raise RuntimeError("修复后检查仍有异常，请查看检查项目")
            record.update(state="done", after=after)
            atomic_json(backup / "repair.json", record)
            atomic_json(self.record_pointer, record)
            return "环境修复完成，下次启动 MHR 生效"
        except Exception as e:
            record.update(state="failed", error=str(e))
            atomic_json(backup / "repair.json", record)
            atomic_json(self.record_pointer, record)
            raise RuntimeError(f"{e}。修复未完成；原文件与环境备份：{backup}") from e
