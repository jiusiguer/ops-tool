# ops-tool

中文 Linux 服务器运维工具。当前第一版先实现 Codex CLI 管理模块，后续可以继续扩展 Docker、Nginx、备份、防火墙、用户、监控等任务。

## 设计原则

- `run.sh` 只做入口、Python 选择和参数转发。
- Python 负责交互菜单、命令模式、系统检测、日志、dry-run 和实际运维逻辑。
- 所有系统命令统一从 `src/ops_tool/shell.py` 执行，便于记录日志、超时、dry-run 和错误处理。
- Codex CLI 生命周期和本机 `~/.codex` 文件管理集中在 `src/ops_tool/tasks/codex.py`。
- cc-switch Codex 统一配置面板调用集中在 `src/ops_tool/tasks/ccswitch.py`。
- 认证文件只显示结构和状态，不打印实际密钥或 token。

## 快速开始

一键下载安装到用户目录并启动菜单：

```bash
curl -fsSL https://raw.githubusercontent.com/jiusiguer/ops-tool/main/install.sh | bash
```

如果只安装、不自动启动菜单：

```bash
curl -fsSL https://raw.githubusercontent.com/jiusiguer/ops-tool/main/install.sh | OPS_TOOL_RUN_AFTER_INSTALL=0 bash
```

安装后可以直接运行：

```bash
ops-tool
```

默认安装位置：

```text
~/.local/share/ops-tool
~/.local/bin/ops-tool
```

也可以手动运行本地目录：

```bash
cd /home/yuyo/桌面/ops-tool
chmod +x run.sh
./run.sh
```

无参数运行会进入中文交互菜单。主菜单先进入 `Codex 管理`，然后再展开 Codex CLI、认证文件、配置文件和 cc-switch 统一配置面板。

## Codex 管理命令

查看状态：

```bash
./run.sh codex status
./run.sh codex panel
```

安装最新版：

```bash
./run.sh codex install
```

更新最新版：

```bash
./run.sh codex update
```

也可以指定更新方式：

```bash
./run.sh codex update --method codex
./run.sh codex update --method npm
```

登录和登出：

```bash
./run.sh codex login
./run.sh codex login --device-auth
./run.sh codex logout
```

配置文件管理：

```bash
./run.sh codex config show
./run.sh codex config show --raw
./run.sh codex config edit
./run.sh codex config set model '"gpt-5.2"'
./run.sh codex config set sandbox_mode '"workspace-write"'
./run.sh codex config backup
./run.sh codex config restore backups/codex-config/config.toml.20260514-120000.bak
```

认证文件管理：

```bash
./run.sh codex auth status
./run.sh codex auth backup
./run.sh codex auth fix-perms
./run.sh codex auth import /path/to/auth.json
```

备份：

```bash
./run.sh codex backup
./run.sh codex backup --all
```

## cc-switch Codex 统一配置面板

本工具集成了 [cc-switch-cli](https://github.com/SaladDay/cc-switch-cli)。`cc-switch` 是 Claude Code、Codex、Gemini、OpenCode 等 CLI 的统一配置管理工具，本项目当前按 Codex 模式调用它。

安装或更新 cc-switch：

```bash
./run.sh ccswitch install
./run.sh ccswitch update
```

打开 Codex 配置统一管理面板：

```bash
./run.sh ccswitch launch
```

也可以从 Codex 命令入口直接跳转：

```bash
./run.sh codex panel
```

常用 cc-switch Codex 命令：

```bash
./run.sh ccswitch status
./run.sh ccswitch provider-current
./run.sh ccswitch provider-list
./run.sh ccswitch provider-switch <provider-id>
./run.sh ccswitch mcp-list
./run.sh ccswitch mcp-import
./run.sh ccswitch mcp-sync
./run.sh ccswitch prompts-list
./run.sh ccswitch skills-list
./run.sh ccswitch skills-sync
./run.sh ccswitch env-check
./run.sh ccswitch env-tools
```

`cc-switch` 自己的配置目录默认是 `~/.cc-switch`。它管理 Codex 时会面向 Codex live 配置文件 `~/.codex/config.toml` 和 `~/.codex/auth.json`。

## 代理服务搭建

主菜单里选择 `代理服务搭建` 可以进入 Xray / sing-box 的一键部署功能。当前第一批支持：

- `VLESS + REALITY + XHTTP`：使用 Xray core，写入 `/usr/local/etc/xray/config.json`。
- `Hysteria2 / HY2`：使用 sing-box core，写入 `/etc/sing-box/config.json`，默认生成自签证书和 salamander 混淆。

查看状态和文档来源：

```bash
./run.sh proxy status
./run.sh proxy docs
```

安装核心：

```bash
./run.sh proxy install-xray
./run.sh proxy install-sing-box
./run.sh proxy repair-xray-perms
```

安装和部署不要求整个工具必须用 root 启动。当前用户如果已经是 root，会直接执行系统安装和写入；如果是普通用户，会在需要写 `/etc`、安装核心、重启服务或调整防火墙时自动使用 `sudo` 提权。

如果 Xray 官方安装脚本提示 `warning: Failed to enable and start the Xray service`，常见原因是默认 `/usr/local/etc/xray/config.json` 被安装成 `0600 root:root`，而服务以非 root 用户读取配置。运行 `./run.sh proxy repair-xray-perms` 会修正为服务可读的 `0644` 并重启。

试跑部署，不实际写入 `/etc`、不安装核心、不启动服务：

```bash
./run.sh --dry-run --yes proxy deploy-vless-default
./run.sh --dry-run --yes proxy deploy-hy2-default

./run.sh --dry-run --yes proxy deploy-vless-reality-xhttp \
  --server example.com \
  --no-install-core \
  --no-start

./run.sh --dry-run --yes proxy deploy-hy2 \
  --server example.com \
  --no-install-core \
  --no-start
```

真实部署示例：

```bash
./run.sh proxy deploy-vless-default
./run.sh proxy deploy-hy2-default

./run.sh proxy deploy-vless-reality-xhttp \
  --server your-domain-or-ip.example \
  --port 443 \
  --server-name www.microsoft.com \
  --reality-target www.microsoft.com:443 \
  --path /xhttp \
  --open-firewall

./run.sh proxy deploy-hy2 \
  --server your-domain-or-ip.example \
  --port 443 \
  --server-name your-domain-or-ip.example \
  --open-firewall
```

`deploy-vless-default` 默认使用 `443/tcp`、`www.microsoft.com` 作为 REALITY SNI、`/xhttp` 作为 XHTTP path，并自动生成 UUID、REALITY key、shortId。

`deploy-hy2-default` 默认使用 `443/udp`、自签证书、随机密码、salamander 混淆和随机混淆密码。

默认部署会先尝试自动检测公网 IP。检测失败时会回退到本机主机名。部署完成会打印对应的分享链接，并把客户端信息保存到 `/etc/ops-tool/proxy-clients/`。HY2 使用 UDP，除了本机防火墙，还要在云厂商安全组里放行对应 UDP 端口。

卸载：

```bash
./run.sh codex uninstall
```

默认卸载只移除 npm 包，不删除 `~/.codex`。如果需要同时删除配置和认证文件：

```bash
./run.sh codex uninstall --purge-config
```

该模式会先备份整个 Codex 目录，并要求输入确认文本。

## 全局参数

```bash
./run.sh --dry-run codex install
./run.sh --yes codex update
./run.sh --verbose codex status
```

`--dry-run` 会展示将执行的命令，但不实际修改系统。

`--yes` 只自动确认普通提示；删除配置和认证文件这类危险操作仍需输入确认文本。

## 文件位置

- 工具日志：`/home/yuyo/桌面/ops-tool/logs/`
- 工具备份：`/home/yuyo/桌面/ops-tool/backups/`
- Codex 配置：默认 `~/.codex/config.toml`
- Codex 认证：默认 `~/.codex/auth.json`

可以通过 `CODEX_HOME` 环境变量管理其它 Codex 配置目录：

```bash
CODEX_HOME=/tmp/test-codex ./run.sh codex status
```
