from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from ..context import RuntimeContext
from ..detect import collect_system_info
from ..shell import CommandResult, run_command
from ..ui import confirm, print_kv, print_step, print_title, print_warning

XRAY_INSTALL_URL = "https://github.com/XTLS/Xray-install/raw/main/install-release.sh"
SING_BOX_INSTALL_URL = "https://sing-box.app/install.sh"

XRAY_CONFIG = Path("/usr/local/etc/xray/config.json")
SING_BOX_CONFIG = Path("/etc/sing-box/config.json")
CLIENT_DIR = Path("/etc/ops-tool/proxy-clients")
HY2_CERT_DIR = Path("/etc/ops-tool/proxy-certs")

DOC_SOURCES = [
    "Xray 安装：https://xtls.github.io/en/document/install",
    "Xray VLESS：https://xtls.github.io/en/config/inbounds/vless.html",
    "Xray 传输 / REALITY / XHTTP：https://xtls.github.io/en/config/transport.html",
    "Xray XHTTP 说明：https://github.com/XTLS/Xray-core/discussions/4113",
    "sing-box 安装：https://sing-box.sagernet.org/installation/package-manager/",
    "sing-box Hysteria2 入站：https://sing-box.sagernet.org/configuration/inbound/hysteria2/",
    "sing-box Hysteria2：https://sing-box.sagernet.org/manual/proxy-protocol/hysteria2/",
]

RANDOM_PORT_MIN = 20000
RANDOM_PORT_MAX = 59999
COMMON_PORTS = {
    20,
    21,
    22,
    25,
    53,
    80,
    110,
    123,
    143,
    161,
    389,
    443,
    465,
    587,
    993,
    995,
    1433,
    1521,
    2049,
    2375,
    2376,
    3000,
    3306,
    3389,
    5432,
    5900,
    6379,
    8000,
    8080,
    8443,
    9000,
    9200,
    11211,
    27017,
}


@dataclass(frozen=True, slots=True)
class VlessRealityXhttpPlan:
    listen: str
    server: str
    port: int
    uuid: str
    email: str
    reality_target: str
    server_name: str
    private_key: str
    public_key: str
    short_id: str
    path: str
    xhttp_mode: str
    remark: str


@dataclass(frozen=True, slots=True)
class Hy2Plan:
    listen: str
    server: str
    port: int
    server_name: str
    user: str
    password: str
    obfs_password: str
    up_mbps: int
    down_mbps: int
    cert_path: Path
    key_path: Path
    self_signed: bool
    insecure_client: bool
    remark: str


@dataclass(frozen=True, slots=True)
class VlessRealityXhttpDefaults:
    listen: str = "0.0.0.0"
    reality_target: str = "www.microsoft.com:443"
    server_name: str = "www.microsoft.com"
    path: str = "/xhttp"
    xhttp_mode: str = "auto"
    email: str = "ops-tool@local"
    remark: str = "ops-vless-reality-xhttp"
    open_firewall: bool = False


@dataclass(frozen=True, slots=True)
class Hy2Defaults:
    listen: str = "::"
    user: str = "default"
    up_mbps: int = 100
    down_mbps: int = 100
    self_signed: bool = True
    open_firewall: bool = False
    remark: str = "ops-hy2"


def _command_path(name: str) -> str | None:
    return shutil.which(name)


def root_cmd(command: list[str]) -> list[str]:
    if os.geteuid() == 0:
        return command
    return ["sudo", *command]


def status(ctx: RuntimeContext) -> int:
    print_title("代理服务搭建状态")
    info = collect_system_info()
    print_kv("系统", info.os_name)
    print_kv("架构", info.arch)
    print_kv("包管理器", info.package_manager)
    print_kv("初始化系统", info.init_system)
    print_kv("Xray 命令", _command_path("xray") or "未安装")
    print_kv("Xray 配置", file_summary(XRAY_CONFIG))
    print_kv("sing-box 命令", _command_path("sing-box") or "未安装")
    print_kv("sing-box 配置", file_summary(SING_BOX_CONFIG))
    print_kv("客户端信息目录", CLIENT_DIR)

    for command in ("xray", "sing-box"):
        binary = _command_path(command)
        if not binary:
            continue
        result = run_command(ctx, [binary, "version"], capture=True, timeout=10, dry_run_execute=True)
        if result.ok:
            print_kv(f"{command} 版本", first_line(result))

    if _command_path("systemctl"):
        print_title("systemd 服务")
        for service in ("xray", "sing-box"):
            result = run_command(
                ctx,
                ["systemctl", "is-active", service],
                capture=True,
                timeout=5,
                dry_run_execute=True,
            )
            print_kv(f"{service}.service", (result.stdout or result.stderr).strip() or f"rc={result.returncode}")
    return 0


def docs(_: RuntimeContext) -> int:
    print_title("代理协议文档来源")
    for source in DOC_SOURCES:
        print(f"- {source}", flush=True)
    return 0


def deploy_vless_default(ctx: RuntimeContext, *, server: str | None = None) -> int:
    defaults = VlessRealityXhttpDefaults()
    selected_server = server or detect_public_server(ctx)
    selected_port = choose_random_port(ctx, "tcp")
    print_title("一键部署默认 VLESS + REALITY + XHTTP")
    print_kv("默认服务器地址", selected_server)
    print_kv("随机端口", f"{selected_port}/tcp")
    print_kv("默认 SNI", defaults.server_name)
    print_kv("默认 XHTTP path", defaults.path)
    return deploy_vless_reality_xhttp(
        ctx,
        server=selected_server,
        port=selected_port,
        reality_target=defaults.reality_target,
        server_name=defaults.server_name,
        path=defaults.path,
        xhttp_mode=defaults.xhttp_mode,
        email=defaults.email,
        listen=defaults.listen,
        open_firewall=defaults.open_firewall,
        remark=defaults.remark,
    )


def deploy_hy2_default(ctx: RuntimeContext, *, server: str | None = None) -> int:
    defaults = Hy2Defaults()
    selected_server = server or detect_public_server(ctx)
    selected_port = choose_random_port(ctx, "udp")
    print_title("一键部署默认 Hysteria2 / HY2")
    print_kv("默认服务器地址", selected_server)
    print_kv("随机端口", f"{selected_port}/udp")
    print_kv("默认证书模式", "自签证书")
    print_kv("默认混淆", "salamander")
    return deploy_hy2(
        ctx,
        server=selected_server,
        port=selected_port,
        server_name=selected_server,
        listen=defaults.listen,
        user=defaults.user,
        up_mbps=defaults.up_mbps,
        down_mbps=defaults.down_mbps,
        self_signed=defaults.self_signed,
        open_firewall=defaults.open_firewall,
        remark=defaults.remark,
    )


def file_summary(path: Path) -> str:
    if not path.exists():
        return f"{path} 不存在"
    mode = stat.S_IMODE(path.stat().st_mode)
    return f"{path} 存在，大小 {path.stat().st_size} 字节，权限 {mode:04o}"


def first_line(result: CommandResult) -> str:
    text = (result.stdout or result.stderr).strip()
    return text.splitlines()[0] if text else ""


def install_xray(ctx: RuntimeContext) -> int:
    print_title("安装 / 更新 Xray")
    print_kv("官方脚本", XRAY_INSTALL_URL)
    if not confirm(ctx, "确认安装或更新 Xray core？"):
        print_step("已取消。")
        return 1
    run_command(
        ctx,
        ["bash", "-lc", root_pipe_install_command(XRAY_INSTALL_URL, "bash", "install")],
        check=True,
        capture=False,
        timeout=900,
    )
    repair_xray_permissions(ctx, restart=True)
    return status(ctx)


def install_sing_box(ctx: RuntimeContext) -> int:
    print_title("安装 / 更新 sing-box")
    print_kv("官方脚本", SING_BOX_INSTALL_URL)
    if not confirm(ctx, "确认安装或更新 sing-box？"):
        print_step("已取消。")
        return 1
    run_command(
        ctx,
        ["bash", "-lc", root_pipe_install_command(SING_BOX_INSTALL_URL, "sh", "")],
        check=True,
        capture=False,
        timeout=900,
    )
    return status(ctx)


def repair_xray_permissions(ctx: RuntimeContext, *, restart: bool = False) -> int:
    print_title("修复 Xray 配置权限")
    print_kv("配置文件", XRAY_CONFIG)
    if not ctx.dry_run and not XRAY_CONFIG.exists():
        print_warning("Xray 配置文件不存在，跳过权限修复。")
        return 1

    run_command(ctx, root_cmd(["install", "-d", "-m", "0755", str(XRAY_CONFIG.parent)]), check=True, capture=True)
    run_command(ctx, root_cmd(["chmod", "644", str(XRAY_CONFIG)]), check=True, capture=True)
    if restart:
        run_command(ctx, root_cmd(["systemctl", "daemon-reload"]), check=False, capture=True, timeout=60)
        run_command(ctx, root_cmd(["systemctl", "restart", "xray"]), check=False, capture=False, timeout=120)
    return 0


def repair_xray_vless_clients(ctx: RuntimeContext, *, restart: bool = True) -> int:
    print_title("修复 Xray VLESS clients 字段")
    print_kv("配置文件", XRAY_CONFIG)
    if not XRAY_CONFIG.exists():
        print_warning("Xray 配置文件不存在。")
        return 1

    text = read_root_file(ctx, XRAY_CONFIG)
    config = json.loads(text)
    changed = migrate_vless_users_to_clients(config)
    if changed == 0:
        print_step("未发现需要迁移的 VLESS settings.users 字段。")
        return 0

    print_step(f"发现并迁移 {changed} 个 VLESS 入站。")
    if not confirm(ctx, "确认写回修复后的 Xray 配置并重启服务？"):
        print_step("已取消。")
        return 1

    backup_root_file(ctx, XRAY_CONFIG)
    write_root_file(ctx, XRAY_CONFIG, json.dumps(config, ensure_ascii=False, indent=2) + "\n", mode="0644")
    if not ctx.dry_run:
        validate_xray_config(ctx)
    if restart:
        restart_service(ctx, "xray")
    return 0


def read_root_file(ctx: RuntimeContext, path: Path) -> str:
    result = run_command(ctx, root_cmd(["cat", str(path)]), check=True, capture=True, dry_run_execute=True)
    return result.stdout


def migrate_vless_users_to_clients(config: dict[str, object]) -> int:
    changed = 0
    inbounds = config.get("inbounds")
    if not isinstance(inbounds, list):
        return changed
    for inbound in inbounds:
        if not isinstance(inbound, dict):
            continue
        if inbound.get("protocol") != "vless":
            continue
        settings = inbound.get("settings")
        if not isinstance(settings, dict):
            continue
        users = settings.pop("users", None)
        if "clients" not in settings and isinstance(users, list):
            settings["clients"] = users
            changed += 1
        elif users is not None:
            changed += 1
    return changed


def root_pipe_install_command(url: str, interpreter: str, args: str) -> str:
    sudo_env = (
        'env "HTTP_PROXY=${HTTP_PROXY-}" "HTTPS_PROXY=${HTTPS_PROXY-}" '
        '"http_proxy=${http_proxy-}" "https_proxy=${https_proxy-}" '
        '"ALL_PROXY=${ALL_PROXY-}" "all_proxy=${all_proxy-}" '
        '"NO_PROXY=${NO_PROXY-}" "no_proxy=${no_proxy-}"'
    )
    suffix = f" -s -- {args}" if args else ""
    root_command = f"curl -fsSL {url} | {interpreter}{suffix}"
    sudo_command = f"curl -fsSL {url} | sudo {sudo_env} {interpreter}{suffix}"
    return (
        "set -e\n"
        'if [ "$(id -u)" -eq 0 ]; then\n'
        f"  {root_command}\n"
        "else\n"
        "  command -v sudo >/dev/null 2>&1 || { echo '错误：当前不是 root，且未找到 sudo，无法提权安装。' >&2; exit 1; }\n"
        f"  {sudo_command}\n"
        "fi"
    )


def deploy_vless_reality_xhttp(
    ctx: RuntimeContext,
    *,
    server: str,
    port: int = 443,
    reality_target: str = "www.microsoft.com:443",
    server_name: str = "www.microsoft.com",
    path: str = "/xhttp",
    xhttp_mode: str = "auto",
    email: str = "ops-tool@local",
    listen: str = "0.0.0.0",
    install_core: bool = True,
    start: bool = True,
    open_firewall: bool = False,
    remark: str = "ops-vless-reality-xhttp",
) -> int:
    print_title("部署 VLESS + REALITY + XHTTP")
    print_warning("将写入 Xray 配置文件，并在确认后重启 xray 服务。")
    print_vless_input_summary(
        listen=listen,
        server=server,
        port=port,
        reality_target=reality_target,
        server_name=server_name,
        path=path,
        xhttp_mode=xhttp_mode,
        remark=remark,
    )
    if not _command_path("xray") and install_core:
        print_warning("当前未检测到 xray；确认部署后会先通过 sudo 安装 Xray core。")
    elif not _command_path("xray") and not ctx.dry_run:
        raise RuntimeError("未找到 xray，且已指定不自动安装核心，无法生成 REALITY 密钥。")

    if not confirm(ctx, "确认部署该 Xray 代理组合？"):
        print_step("已取消。")
        return 1

    if install_core and not _command_path("xray"):
        install_xray(ctx)
    if not _command_path("xray") and not ctx.dry_run:
        raise RuntimeError("Xray 安装后仍未在 PATH 中找到 xray，无法继续部署。")

    plan = build_vless_plan(
        ctx,
        server=server,
        port=port,
        reality_target=reality_target,
        server_name=server_name,
        path=path,
        xhttp_mode=xhttp_mode,
        email=email,
        listen=listen,
        remark=remark,
    )
    print_title("生成的部署参数")
    print_vless_plan(plan)

    config = generate_xray_vless_reality_xhttp_config(plan)
    client_info = generate_vless_client_info(plan)

    backup_root_file(ctx, XRAY_CONFIG)
    write_root_file(ctx, XRAY_CONFIG, json.dumps(config, ensure_ascii=False, indent=2) + "\n", mode="0644")
    client_path = CLIENT_DIR / f"{safe_filename(remark)}-vless-reality-xhttp.txt"
    write_root_file(ctx, client_path, client_info, mode="0600")

    if not ctx.dry_run:
        validate_xray_config(ctx)
    if open_firewall:
        open_port(ctx, port, "tcp")
    if start:
        restart_service(ctx, "xray")

    print_title("客户端信息")
    print_kv("保存路径", client_path)
    print(client_info, flush=True)
    return 0


def deploy_hy2(
    ctx: RuntimeContext,
    *,
    server: str,
    port: int = 443,
    server_name: str | None = None,
    listen: str = "::",
    user: str = "default",
    password: str | None = None,
    obfs_password: str | None = None,
    up_mbps: int = 100,
    down_mbps: int = 100,
    cert_path: Path | None = None,
    key_path: Path | None = None,
    self_signed: bool = True,
    install_core: bool = True,
    start: bool = True,
    open_firewall: bool = False,
    remark: str = "ops-hy2",
) -> int:
    print_title("部署 Hysteria2 / HY2")
    print_warning("HY2 基于 QUIC/UDP。云厂商安全组和服务器防火墙都需要放行 UDP 端口。")
    effective_server_name = server_name or server
    cert = cert_path or HY2_CERT_DIR / f"{safe_filename(effective_server_name)}.crt"
    key = key_path or HY2_CERT_DIR / f"{safe_filename(effective_server_name)}.key"
    plan = Hy2Plan(
        listen=listen,
        server=server,
        port=port,
        server_name=effective_server_name,
        user=user,
        password=password or secrets.token_urlsafe(24),
        obfs_password=obfs_password or secrets.token_urlsafe(18),
        up_mbps=up_mbps,
        down_mbps=down_mbps,
        cert_path=cert,
        key_path=key,
        self_signed=self_signed,
        insecure_client=self_signed,
        remark=remark,
    )
    print_hy2_plan(plan)

    if not confirm(ctx, "确认部署该 HY2 代理组合？"):
        print_step("已取消。")
        return 1

    if install_core and not _command_path("sing-box"):
        install_sing_box(ctx)

    if plan.self_signed:
        ensure_self_signed_cert(ctx, plan)
    elif not (root_path_exists(ctx, plan.cert_path) and root_path_exists(ctx, plan.key_path)):
        raise RuntimeError("未启用自签证书时，必须提供已存在的 cert/key 文件。")

    config = generate_singbox_hy2_config(plan)
    client_info = generate_hy2_client_info(plan)

    backup_root_file(ctx, SING_BOX_CONFIG)
    write_root_file(ctx, SING_BOX_CONFIG, json.dumps(config, ensure_ascii=False, indent=2) + "\n", mode="0644")
    client_path = CLIENT_DIR / f"{safe_filename(remark)}-hy2.txt"
    write_root_file(ctx, client_path, client_info, mode="0600")

    if not ctx.dry_run:
        validate_singbox_config(ctx)
    if open_firewall:
        open_port(ctx, port, "udp")
    if start:
        restart_service(ctx, "sing-box")

    print_title("客户端信息")
    print_kv("保存路径", client_path)
    print(client_info, flush=True)
    return 0


def build_vless_plan(
    ctx: RuntimeContext,
    *,
    server: str,
    port: int,
    reality_target: str,
    server_name: str,
    path: str,
    xhttp_mode: str,
    email: str,
    listen: str,
    remark: str,
) -> VlessRealityXhttpPlan:
    private_key, public_key = generate_xray_x25519(ctx)
    return VlessRealityXhttpPlan(
        listen=listen,
        server=server,
        port=port,
        uuid=str(uuid.uuid4()),
        email=email,
        reality_target=reality_target,
        server_name=server_name,
        private_key=private_key,
        public_key=public_key,
        short_id=secrets.token_hex(8),
        path=normalize_path(path),
        xhttp_mode=xhttp_mode,
        remark=remark,
    )


def generate_xray_x25519(ctx: RuntimeContext) -> tuple[str, str]:
    binary = _command_path("xray")
    if not binary:
        if ctx.dry_run:
            return "DRY_RUN_PRIVATE_KEY", "DRY_RUN_PUBLIC_KEY"
        raise RuntimeError("未找到 xray，无法生成 REALITY x25519 密钥。")
    result = run_command(ctx, [binary, "x25519"], capture=True, timeout=10, dry_run_execute=True)
    if not result.ok:
        raise RuntimeError(result.stderr.strip() or "xray x25519 执行失败。")
    private_key = ""
    public_key = ""
    for line in result.stdout.splitlines():
        lowered = line.lower()
        if "privatekey:" in lowered or "private key:" in lowered:
            private_key = line.split(":", 1)[1].strip()
        elif "publickey" in lowered or "public key" in lowered:
            public_key = line.split(":", 1)[1].strip()
    if not private_key or not public_key:
        raise RuntimeError("无法解析 xray x25519 输出。")
    return private_key, public_key


def normalize_path(path: str) -> str:
    clean = path.strip() or "/xhttp"
    if not clean.startswith("/"):
        clean = "/" + clean
    return clean


def generate_xray_vless_reality_xhttp_config(plan: VlessRealityXhttpPlan) -> dict[str, object]:
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "vless-reality-xhttp-in",
                "listen": plan.listen,
                "port": plan.port,
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {
                            "id": plan.uuid,
                            "email": plan.email,
                            "flow": "",
                        }
                    ],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "xhttp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "target": plan.reality_target,
                        "xver": 0,
                        "serverNames": [plan.server_name],
                        "privateKey": plan.private_key,
                        "shortIds": [plan.short_id],
                    },
                    "xhttpSettings": {
                        "path": plan.path,
                        "mode": plan.xhttp_mode,
                    },
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"],
                },
            }
        ],
        "outbounds": [
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
    }


def generate_vless_client_info(plan: VlessRealityXhttpPlan) -> str:
    query = {
        "type": "xhttp",
        "security": "reality",
        "encryption": "none",
        "pbk": plan.public_key,
        "fp": "chrome",
        "sni": plan.server_name,
        "sid": plan.short_id,
        "path": plan.path,
        "mode": plan.xhttp_mode,
        "flow": "",
    }
    link_query = "&".join(f"{quote(key)}={quote(value)}" for key, value in query.items() if value != "")
    link = f"vless://{plan.uuid}@{plan.server}:{plan.port}?{link_query}#{quote(plan.remark)}"
    return "\n".join(
        [
            "协议组合：VLESS + REALITY + XHTTP",
            f"服务器：{plan.server}",
            f"端口：{plan.port}/tcp",
            f"UUID：{plan.uuid}",
            f"REALITY serverName/SNI：{plan.server_name}",
            f"REALITY publicKey：{plan.public_key}",
            f"REALITY shortId：{plan.short_id}",
            f"XHTTP path：{plan.path}",
            f"XHTTP mode：{plan.xhttp_mode}",
            "",
            "分享链接：",
            link,
            "",
        ]
    )


def generate_singbox_hy2_config(plan: Hy2Plan) -> dict[str, object]:
    return {
        "log": {"level": "info"},
        "inbounds": [
            {
                "type": "hysteria2",
                "tag": "hy2-in",
                "listen": plan.listen,
                "listen_port": plan.port,
                "up_mbps": plan.up_mbps,
                "down_mbps": plan.down_mbps,
                "users": [{"name": plan.user, "password": plan.password}],
                "obfs": {
                    "type": "salamander",
                    "password": plan.obfs_password,
                },
                "tls": {
                    "enabled": True,
                    "server_name": plan.server_name,
                    "key_path": str(plan.key_path),
                    "certificate_path": str(plan.cert_path),
                },
            }
        ],
        "outbounds": [{"type": "direct", "tag": "direct"}],
    }


def generate_hy2_client_info(plan: Hy2Plan) -> str:
    query = {
        "sni": plan.server_name,
        "insecure": "1" if plan.insecure_client else "0",
        "obfs": "salamander",
        "obfs-password": plan.obfs_password,
    }
    link_query = "&".join(f"{quote(key)}={quote(value)}" for key, value in query.items())
    link = f"hysteria2://{quote(plan.password)}@{plan.server}:{plan.port}?{link_query}#{quote(plan.remark)}"
    return "\n".join(
        [
            "协议组合：Hysteria2 / HY2（sing-box）",
            f"服务器：{plan.server}",
            f"端口：{plan.port}/udp",
            f"用户：{plan.user}",
            f"密码：{plan.password}",
            f"混淆：salamander",
            f"混淆密码：{plan.obfs_password}",
            f"SNI：{plan.server_name}",
            f"证书：{plan.cert_path}",
            f"私钥：{plan.key_path}",
            f"客户端 insecure：{'是' if plan.insecure_client else '否'}",
            "",
            "分享链接：",
            link,
            "",
        ]
    )


def print_vless_plan(plan: VlessRealityXhttpPlan) -> None:
    print_vless_input_summary(
        listen=plan.listen,
        server=plan.server,
        port=plan.port,
        reality_target=plan.reality_target,
        server_name=plan.server_name,
        path=plan.path,
        xhttp_mode=plan.xhttp_mode,
        remark=plan.remark,
    )
    print_kv("UUID", plan.uuid)
    print_kv("REALITY shortId", plan.short_id)
    print_kv("REALITY publicKey", plan.public_key)


def print_vless_input_summary(
    *,
    listen: str,
    server: str,
    port: int,
    reality_target: str,
    server_name: str,
    path: str,
    xhttp_mode: str,
    remark: str,
) -> None:
    print_kv("监听", f"{listen}:{port}/tcp")
    print_kv("服务器地址", server)
    print_kv("REALITY target", reality_target)
    print_kv("REALITY SNI", server_name)
    print_kv("XHTTP path", normalize_path(path))
    print_kv("XHTTP mode", xhttp_mode)
    print_kv("备注", remark)


def print_hy2_plan(plan: Hy2Plan) -> None:
    print_kv("监听", f"{plan.listen}:{plan.port}/udp")
    print_kv("服务器地址", plan.server)
    print_kv("SNI", plan.server_name)
    print_kv("上行/下行", f"{plan.up_mbps}/{plan.down_mbps} Mbps")
    print_kv("证书模式", "自签证书" if plan.self_signed else "已有证书")
    print_kv("证书路径", plan.cert_path)
    print_kv("私钥路径", plan.key_path)
    print_kv("备注", plan.remark)


def backup_root_file(ctx: RuntimeContext, path: Path) -> None:
    if not path.exists():
        return
    backup = backup_path(path)
    print_step(f"备份 {path} 到 {backup}")
    if ctx.dry_run:
        return
    run_command(ctx, root_cmd(["install", "-d", "-m", "0755", str(backup.parent)]), check=True, capture=True)
    run_command(ctx, root_cmd(["cp", "-a", str(path), str(backup)]), check=True, capture=True)


def backup_path(path: Path) -> Path:
    stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("/etc/ops-tool/backups") / safe_filename(str(path).strip("/")) / f"{path.name}.{stamp}.bak"


def write_root_file(ctx: RuntimeContext, path: Path, content: str, *, mode: str) -> None:
    print_step(f"写入 {path}")
    if ctx.dry_run:
        print_step(f"[dry-run] 内容长度 {len(content.encode('utf-8'))} 字节，权限 {mode}")
        return
    run_command(ctx, root_cmd(["install", "-d", "-m", "0755", str(path.parent)]), check=True, capture=True)
    run_command(
        ctx,
        root_cmd(["tee", str(path)]),
        check=True,
        capture=True,
        input_text=content,
    )
    run_command(ctx, root_cmd(["chmod", mode, str(path)]), check=True, capture=True)


def validate_xray_config(ctx: RuntimeContext) -> None:
    binary = _command_path("xray") or "xray"
    run_command(ctx, [binary, "run", "-test", "-config", str(XRAY_CONFIG)], check=True, capture=False, timeout=30)


def validate_singbox_config(ctx: RuntimeContext) -> None:
    binary = _command_path("sing-box") or "sing-box"
    run_command(ctx, [binary, "check", "-c", str(SING_BOX_CONFIG)], check=True, capture=False, timeout=30)


def restart_service(ctx: RuntimeContext, service: str) -> None:
    print_step(f"重启并启用服务：{service}")
    run_command(ctx, root_cmd(["systemctl", "enable", "--now", service]), check=True, capture=False, timeout=120)
    run_command(ctx, root_cmd(["systemctl", "restart", service]), check=True, capture=False, timeout=120)
    run_command(ctx, ["systemctl", "is-active", service], check=False, capture=False, timeout=10, dry_run_execute=True)


def open_port(ctx: RuntimeContext, port: int, proto: str) -> None:
    print_step(f"尝试放行防火墙端口：{port}/{proto}")
    if shutil.which("ufw"):
        result = run_command(ctx, root_cmd(["ufw", "status"]), capture=True, timeout=10, dry_run_execute=True)
        if "Status: active" in result.stdout:
            run_command(ctx, root_cmd(["ufw", "allow", f"{port}/{proto}"]), check=True, capture=False, timeout=30)
            return
    if shutil.which("firewall-cmd"):
        result = run_command(ctx, root_cmd(["firewall-cmd", "--state"]), capture=True, timeout=10, dry_run_execute=True)
        if "running" in result.stdout:
            run_command(ctx, root_cmd(["firewall-cmd", "--permanent", f"--add-port={port}/{proto}"]), check=True, capture=False)
            run_command(ctx, root_cmd(["firewall-cmd", "--reload"]), check=True, capture=False)
            return
    print_warning("未检测到活动的 ufw/firewalld。仍需确认云安全组或宿主机防火墙已放行。")


def ensure_self_signed_cert(ctx: RuntimeContext, plan: Hy2Plan) -> None:
    if root_path_exists(ctx, plan.cert_path) and root_path_exists(ctx, plan.key_path):
        return
    if not shutil.which("openssl"):
        raise RuntimeError("生成自签证书需要 openssl，请先安装 openssl。")
    print_step(f"生成自签证书：{plan.cert_path}")
    if ctx.dry_run:
        return
    run_command(ctx, root_cmd(["install", "-d", "-m", "0755", str(plan.cert_path.parent)]), check=True, capture=True)
    run_command(
        ctx,
        root_cmd(
            [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "3650",
            "-keyout",
            str(plan.key_path),
            "-out",
            str(plan.cert_path),
            "-subj",
            f"/CN={plan.server_name}",
            ]
        ),
        check=True,
        capture=False,
        timeout=60,
    )
    run_command(ctx, root_cmd(["chmod", "600", str(plan.key_path)]), check=True, capture=True)
    run_command(ctx, root_cmd(["chmod", "644", str(plan.cert_path)]), check=True, capture=True)


def root_path_exists(ctx: RuntimeContext, path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        if ctx.dry_run:
            return False
    result = run_command(ctx, root_cmd(["test", "-e", str(path)]), check=False, capture=True, dry_run_execute=True)
    return result.ok


def safe_filename(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return clean or "proxy"


def guess_public_server() -> str:
    try:
        return socket.getfqdn() or socket.gethostname()
    except OSError:
        return "your-server.example.com"


def choose_random_port(ctx: RuntimeContext, proto: str) -> int:
    for _ in range(100):
        port = RANDOM_PORT_MIN + secrets.randbelow(RANDOM_PORT_MAX - RANDOM_PORT_MIN + 1)
        if port in COMMON_PORTS:
            continue
        if port_is_available(ctx, port, proto):
            return port
    raise RuntimeError("无法找到可用的随机高位端口。")


def port_is_available(ctx: RuntimeContext, port: int, proto: str) -> bool:
    if port in COMMON_PORTS:
        return False
    if port < RANDOM_PORT_MIN or port > RANDOM_PORT_MAX:
        return False

    sock_type = socket.SOCK_DGRAM if proto == "udp" else socket.SOCK_STREAM
    with socket.socket(socket.AF_INET, sock_type) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            ctx.logger.info(f"port unavailable: {port}/{proto}")
            return False
    return True


def detect_public_server(ctx: RuntimeContext) -> str:
    print_step("自动检测服务器公网地址")
    candidates = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ]
    for url in candidates:
        if not shutil.which("curl"):
            break
        result = run_command(
            ctx,
            ["curl", "-fsSL", "--max-time", "5", url],
            capture=True,
            timeout=8,
            dry_run_execute=True,
        )
        value = result.stdout.strip()
        if result.ok and is_reasonable_server(value):
            print_kv("检测到公网地址", value)
            return value
    fallback = guess_public_server()
    print_warning(f"公网地址自动检测失败，回退到主机名：{fallback}")
    return fallback


def is_reasonable_server(value: str) -> bool:
    if not value or len(value) > 253:
        return False
    if "\n" in value or "\r" in value or " " in value:
        return False
    return bool(re.match(r"^[A-Za-z0-9:._-]+$", value))
