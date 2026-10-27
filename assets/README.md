# 已验证的离线修复材料

这些文件来自 2026-10-27 本机成功修复时使用的安装材料。SHA-256 固定在 `environment.py` 的 `ASSET_HASHES`，部署前及执行修复前均检查。不会自动下载新版覆盖缓存。

- `vc_redist.x64.exe`：Microsoft Visual C++ x64 Redistributable 14.51.36247.0，原下载地址 https://aka.ms/vc14/vc_redist.x64.exe 。
- `reframework-d2d.dll`、`reframework-d2d.lua`：REFramework Direct2D 1.4.1，与本机安装版本一致。项目 https://github.com/cursey/reframework-d2d ，Nexus 页面 https://www.nexusmods.com/monsterhunterrise/mods/134 。

运行库由微软安装器在 MHR 自己的 Proton 环境中安装；不会替换 SteamOS 系统库。文件保留各原作者的权利，仅用于这台设备的维护缓存。
