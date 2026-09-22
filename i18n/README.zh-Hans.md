<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu 桥接器

**通过网易 UU 远程查看并完整控制 Ubuntu GNOME 桌面。**

<p>
  <a href="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp">
    <img src="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp" alt="通过 UU Remote Ubuntu Bridge，从 macOS 连接 Ubuntu GNOME 桌面的实际画面。" width="1120">
  </a>
  <br>
  <sub>通过 UU Remote Ubuntu Bridge，从 macOS 连接 Ubuntu GNOME 桌面的实际画面。</sub>
</p>

</div>

> **关于此 Fork：**本仓库基于
> [Lachlan Chen 的 UU Remote Ubuntu Bridge 原项目](https://github.com/lachlanchen/uu-remote-ubuntu-bridge)。
> Wine/Xvfb、RDP/VNC 中继、输入代理、无人值守及升级架构属于原项目。本分支的
> 工作进行中改动涉及输入路由、静音音频隔离、TigerVNC 中继及 Ubuntu 26.04
> 支持。本分支以 Ubuntu 26.04 为主要目标，24.04 保留上游兼容路径；26.04 的
> 控制端和 UU 4.41 **仍属实验性功能**，不是已广泛验证的
> 正式版本。保留原作者署名与 MIT 许可证；下文主要继承上游文档，只有明确
> 标出的部分是此 Fork 的改动。

这个实验性桥接器在独立 Wine 前缀中运行官方 Windows 客户端，并通过本机
RDP 中继呈现真实的 GNOME Wayland 会话。画面、鼠标、键盘、重新连接和服务
自动恢复均已验证。

当前版本有意锁定为 UU 远程 `4.33.0.8907`；上游 24.04 / GNOME 46
路径保留，本分支主要针对 Ubuntu 26.04 / GNOME 50。任何未知二进制文件
都会被拒绝，绝不会直接套用旧补丁。

此 fork 以 Ubuntu 26.04 / GNOME 50 为主要目标：它会使用并
验证系统的新版 `libei`，不会把 24.04 的旧兼容库载入 GNOME 50。它尚未完成与
24.04 基线相同的真实控制端验收；部署前请阅读
[26.04 移植说明](../docs/ubuntu-26-04-port.md)，并先完成其中的六项验收。

UU 只从网易官方域名 [uuyc.163.com](https://uuyc.163.com/) 下载。官方页面
目前没有列出 Linux 被控端；本桥使用官方 Windows 客户端并核对安装包完整哈希。
不要从仿冒下载页安装未经验证的 `.deb`、`.rpm` 或 AppImage。

正在使用或需要其他 Ubuntu 版本、桌面/会话、CPU 架构、UU 版本或控制端平台？
请[提交一条兼容性反馈或需求](https://github.com/lachlanchen/uu-remote-ubuntu-bridge/issues/new?template=compatibility.yml)。
提交免费且内容公开，但不构成支持承诺。请勿附加或链接专有二进制文件、凭据、
账号或设备 ID、原始日志、截图或私有配置。

如果想先弄清 Wine、中继、真实 GNOME 桌面和输入链路怎样接在一起，可以读这篇
[完整中文指南](https://blog.lazying.art/html/computer_internet/3818/use-uu-remote-on-ubuntu-with-a-reproducible-bridge.html?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=zh_hans_guide)。
它也说明了已验证范围、上游更新为何需要重新审查，以及什么时候不适合使用这座桥。

## 快速安装

在 x86-64 Ubuntu 26.04 GNOME 桌面上，从
[本分支 Releases](https://github.com/cnsunfishegg/uu-remote-ubuntu-bridge/releases)
下载 `amd64` 的 `.deb`。Ubuntu 24.04 也保留支持。打开下载目录中的终端，执行：

```bash
sudo apt install ./uu-remote-ubuntu-bridge-installer_0.3.0-rc3-1_amd64.deb
```

然后从应用菜单打开 **UU Remote 设置**，保持弹出的终端窗口开启，按提示完成
依赖安装和官方 UU 账号登录。完成后，应用菜单中的同一入口会变成 **UU Remote**：
既可管理本机，也可控制另一台电脑；别人连接本机不要求打开这个窗口。
如果应用菜单里找不到设置入口，在已登录的 GNOME 桌面终端以普通用户运行
`uu-remote-bridge-setup`，**不要**加 `sudo`。从源码检出安装的开发者仍可运行
`./install.sh`。

`.deb` 是仅含源码的安装器包，不包含网易程序或账号，也不代表安装包后立即可远控。
设置仍需联网安装依赖、下载并校验官方 UU 安装包。该固定源码快照不支持
依赖 Git 仓库的自动升级；详情见[Debian 包说明](../packaging/README.Debian)。

安装后，桌面只用桥接器生成的 **UU Remote**：既能查看本机账号/设备，也可尝试
从本机控制其他电脑。远控窗口变大或全屏时，画面转发会跟随当前 UU 窗口改变尺寸，
本地查看窗口也会跟随进入全屏；
关闭查看窗口不会停止这台 Ubuntu 的被控服务。旧版桥接器或 Wine 生成的重复
桌面快捷方式会移到 `~/.local/share/uu-remote-bridge/old-shortcuts/`，可恢复。
若当前版本的窗口转发仍失败，高级备用命令 `uu-remote control` 会询问是否暂时
停止被控服务，然后在可见 Ubuntu 桌面直接打开 Wine 中的 UU，关闭后再恢复服务。
如果你是通过 UU 连进这台 Ubuntu 的，不能确认这个备用切换，否则会断开自己。
让别人连接这台 Ubuntu 不需要一直打开查看窗口：登录过官方 UU 账号后，桥接服务
在后台运行。
若对方看不到设备，先运行 `uu-remote status` 检查本机服务；在线与否仍需
另一台设备确认。控制端的真实远控画面也仍需两台电脑验收；弹窗、鼠标和键盘的
本地测试通过，不代表远控视频已经验证通过。
如果 UU 自己的原始画面里就有黑边，放大本地查看窗口也不能消除；改变另一台
Windows 电脑的显示分辨率是另外的选择，本桥接器不会擅自替你修改。

这个幂等安装脚本会安装依赖、校验上游文件、编译所有兼容组件、配置 GNOME
Remote Desktop、把 RDP 密码保存到 GNOME Keyring，并启动用户级 systemd
服务。重复运行不会破坏已有账户状态。

## 控制链路

```text
UU 控制端 -> Wine 中的 UU -> 输入代理 -> SDL FreeRDP
           -> GNOME Remote Desktop -> GNOME Wayland 桌面
```

## 如何适配上游更新

新的维护工具把“自动寻找候选位置”和“人工语义批准”严格分开。它会生成 PE
映射、语义地标、候选签名和定点反汇编，但在逐项审阅并对一次性副本完成测试
前，草稿清单无法被补丁器或安装器使用。

- [完整上游维护流程](../docs/upstream-maintenance.md)
- [解决方法与工具清单](../docs/methodology-and-toolkit.md)
- [精确逆向工程记录](../docs/reverse-engineering.md)
- [安全边界](../docs/security.md)
- [故障排查](../docs/troubleshooting.md)
- [原生 Ubuntu 终端](../docs/native-ubuntu-terminal.md)
- [SSH 别名与双机端口映射](../docs/ssh-and-port-mapping.md)

仓库不包含密码、令牌、设备标识、网易可执行文件或私人日志。上游项目属于
[The Art of Lazying](https://lazying.art)。

如果你更需要独立于厂商的方案，[LazyRemote 中文页](https://remote.lazying.art/zh-Hans/?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=independent_option_zh_hans#review) 由另一套开源 [LazyTunnel](https://github.com/lachlanchen/LazyTunnel) 核心提供自托管的 SSH、终端与 noVNC 访问。这是不同的工具；本仓库仍专注于兼容官方 UU 客户端。

如果已有一台可连接的中继和最多三台电脑，但希望在改动前先核对端口暴露与密钥
角色，可以先看[完整中文样例](https://remote.lazying.art/zh-Hans/sample-report.html?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=network_review_sample_zh_hans)。
可选的固定评估服务为 USD 250，先做[免费的纯元数据适配确认](https://lazying.art/lazyremote/fit-check/zh-Hans/?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=network_review_fit_check_zh_hans)，
不包含部署、硬件和持续支持。

## 支持项目

如果这个桥接器帮你节省了时间，可以支持我们继续维护兼容性：

| GitHub Sponsors | LazyingArt Donate | PayPal | Stripe |
| --- | --- | --- | --- |
| [![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsor-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen) | [![Donate](https://img.shields.io/badge/LazyingArt-Donate-0EA5E9?style=for-the-badge&logo=ko-fi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

> 完整技术参考保留英文版本，以确保命令、哈希和字节记录只有一个精确来源。
