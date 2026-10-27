# MHR Mods

Steam Deck OLED / Decky Loader 3.3.0 本地 Mod 开关插件。

入口：MHR 库页面 → 齿轮 → 属性 → **Mods 管理**。也可从 Decky 侧栏 **MHR Mods** 打开。

管理当前已安装的 10 项：REFramework、MHR Overlay、Direct2D、SpiritBirds、Skip Dango Song、Carve Timer Skip and Fast Return、No Kill-Cam + SlowMo、弱点图标、All Dango All the Time、VIP Dango Ticket。版本标签对应 2026-10-27 已核对的安装版本；不提供在线更新或任意 Mod 安装功能。

- 切换前退出 MHR 和 Fluffy；后端再次检查进程，不依赖前端锁定。
- 先关闭依赖 Mod，再关闭框架；开启时顺序相反。Overlay 上游允许原生绘图；本机按用户要求保持 Direct2D 开启，配置 `use_d2d_if_available=true`。
- 每次切换先完整备份相关 Mod、配置和开关状态到 `/home/deck/Downloads/02-GameMods/04-MH-Rise/Backups/decky-*`，包含 SHA-256 清单。
- 关闭通过原子移动文件实现；停用文件保存在游戏目录的 `.mhrmods/disabled/<id>/`。用户 JSON/INI 配置不随 Mod 移走。
- 事务失败会自动回滚；进程中断后的事务在下次读取状态时恢复。冲突/混合状态不覆盖文件。
- VIP 团子券原先错误安装在游戏根目录，初始显示为关闭。明确开启时移入 `reframework/autorun/`。
- Fluffy 的安装记录保留，不由本插件改写。使用本插件停用 Mod 后，先在本插件重新开启，再使用 Fluffy 卸载或升级对应 Mod，避免两个管理器各自保留文件。
- 当前游戏路径固定为 `/home/deck/.local/share/Steam/steamapps/common/MonsterHunterRise`。卸载 Decky 插件不会删除 `.mhrmods`；卸载前应重新开启想保留的 Mod。

## 跳过返程倒计时

安装作者 godoakos 的 [Carve Timer Skip and Fast Return 1.5.1hotfix2](https://www.nexusmods.com/monsterhunterrise/mods/62)，保留原版脚本和资源。任务完成后按下左摇杆 L3 跳过倒计时，按下右摇杆 R3 跳过结束动画；两项自动跳过均关闭，避免尚未剥取就返程。沿用旧配置关闭 Direct2D 提示窗口，保留任务完成时的按键文字提示，需自定义时在 REFramework 的 `Fast Return Settings` 中修改。配置位于 `reframework/data/bth_settings.json`，Decky 开关不会移动或重置它。联机时仍可能等待其他玩家完成流程。

## 去击杀镜头与终结慢动作

与倒计时 Mod 独立管理。安装 Bolt 作者 [Nexus 93 号 Mod](https://www.nexusmods.com/monsterhunterrise/mods/93) 对应的官方 GitHub 安装包（提交 `c40b27ee10341d50edc5f45800b811049bba0f7d`），保留原版脚本。配置 `NoKillCam+SlowMo_settings.json` 中开启去击杀镜头，按用户要求关闭单人及联机终结慢动作，并关闭击杀时隐藏 UI，保留原有快速旅行和任务结束镜头。Decky 开关保留此配置。

## 开发与验证

### 环境检查与修复（1.1.0）

Mods 管理页自动检查三个 x64 VC++ DLL 的文件版本、Direct2D 两个文件的 SHA-256、当前 Overlay 配置中的 `use_d2d_if_available`，以及 REFramework/Overlay 是否开启。符合当前验证条件时显示正常；这不是对游戏内每种 Mod 行为的保证，也不自动改变 Steam 的 Proton 选择。

点击“备份并一键修复”后，后台先备份 Mod、配置、整个 MHR Proton 环境和各 Steam 用户的 MHR 存档，并生成备份校验值，再按需安装已验证的 VC++ 14.51.36247 x64 运行库、恢复 Direct2D 1.4.1 和开启其绘图配置。修复过程可查看进度；游戏或 Fluffy 运行时禁止修复，修复期间禁止切换 Mod。备份后再次检查进程，修复完成后才应启动游戏。

已验证材料在 `/home/deck/.local/share/mhr-mods/repair-assets/`，独立于 Decky 插件目录，修复可离线执行。插件不在线下载或执行未知文件；Direct2D 文件与验证版本不同、配置损坏、Proton 环境尚未创建时提示人工处理，防止覆盖用户的新版本或配置。VC++ 运行库高于已验证版本时保留，不降级。修复失败时保留备份及日志，不自动覆盖当前环境进行整套回滚；备份的 `repair.json` 记录执行结果，`runtime-install.log` 记录安装过程。

### 2026-10-27 Direct2D 排查结果

当前使用 Steam 默认 Proton（本次实际选择 11.0-2）、REFramework Nightly 1433、Direct2D 1.4.1 和 MHR Overlay 2.7.4。之前的 `on_present` 持续异常定位到 `MSVCP140.dll+0x12EB0` 的互斥锁空指针访问，调用方为 `reframework-d2d.dll`；游戏前缀内 VC++ 运行库仍为 14.28.29334.0。在完整备份前缀与存档后，用微软官方 x64 安装器升级到 14.51.36247.0，安装成功，重启后 Direct2D 正常加载，启动阶段 `APIProxy/on_present` 错误计数为 0；用户已确认任务内血条正常显示。不能据此将问题归因于中文。

Overlay 暂用英文，游戏保留中文。Debug 会保留开场阶段尚无玩家、随从数据时的历史报错；应结合任务加载后的实时状态判断。最终启动参数已恢复为 `WINEDLLOVERRIDES="dinput8=n,b" %command%`，去除临时 Proton/Wine 详细日志参数。运行库升级前备份在设备 `Backups/vcredist-20261027/compatdata-saves-before.tar.gz`。

```sh
npm ci
npm run typecheck
npm run build
npm test
./install.sh
```

离线修复材料不纳入 Git。部署前按 `assets/README.md` 准备三个文件；这台 Deck 的已验证缓存位于 `/home/deck/.local/share/mhr-mods/repair-assets/`，可复制回本地 `assets/`。部署脚本会核对固定 SHA-256，缺失或不匹配时停止。

`dist/index.js` 是可部署产物。后端 `manager.py` 仅管理白名单内的现有文件，不执行下载包、不修改游戏存档或游戏 PAK 内容；`environment.py` 负责显式触发的备份与修复，只运行校验通过的离线运行库安装器。真实设备已验证属性页入口、RPC、SpiritBirds 关闭/恢复与文件哈希/配置不变；用户已确认运行库修复后血条生效。

新增两个 Mod 已在实机分别完成关闭/恢复测试，所有资产 SHA-256 与配置保持一致；重启游戏已确认 `bth.lua`、`NoKillCam+SlowMo.lua` 和 Overlay 加载，未出现新增脚本或 Direct2D 回调报错。任务完成时的按键和慢动作效果尚待游玩验证。安装前备份分别为设备 `Backups/decky-20261027-234518-826700` 与 `Backups/decky-20261027-234702-356708`。
