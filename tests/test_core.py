from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ops_tool.detect import normalize_arch, read_os_release  # noqa: E402
from ops_tool.context import RuntimeContext  # noqa: E402
from ops_tool.files import mask_json_value, redact_text  # noqa: E402
from ops_tool.log import OpsLogger  # noqa: E402
from ops_tool.shell import CommandResult  # noqa: E402
from ops_tool.tasks import proxy  # noqa: E402
from ops_tool.tasks import ccswitch  # noqa: E402
from ops_tool.tasks.codex import encode_toml_value, redact_login_status, validate_toml_text  # noqa: E402


class CoreTests(unittest.TestCase):
    def make_ctx(self) -> RuntimeContext:
        root = Path(tempfile.mkdtemp())
        return RuntimeContext(root=root, dry_run=True, assume_yes=True, verbose=False, logger=OpsLogger(root / "logs"))

    def test_normalize_arch(self) -> None:
        self.assertEqual(normalize_arch("x86_64"), "amd64")
        self.assertEqual(normalize_arch("aarch64"), "arm64")
        self.assertEqual(normalize_arch("armv7l"), "arm")

    def test_os_release_parser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "os-release"
            path.write_text('ID=ubuntu\nPRETTY_NAME="Ubuntu Test"\n', encoding="utf-8")
            data = read_os_release(path)
        self.assertEqual(data["ID"], "ubuntu")
        self.assertEqual(data["PRETTY_NAME"], "Ubuntu Test")

    def test_redact_text(self) -> None:
        text = "model = \"x\"\napi_key = \"secret\"\n"
        redacted = redact_text(text)
        self.assertIn("model = \"x\"", redacted)
        self.assertNotIn("secret", redacted)

    def test_mask_json_value(self) -> None:
        masked = mask_json_value({"token": "abcdef", "enabled": True})
        self.assertEqual(masked["enabled"], True)
        self.assertEqual(masked["token"], "[已隐藏字符串，长度 6]")

    def test_toml_values(self) -> None:
        self.assertEqual(encode_toml_value("abc", value_type="string"), '"abc"')
        self.assertEqual(encode_toml_value("42", value_type="int"), "42")
        self.assertEqual(encode_toml_value("是", value_type="bool"), "true")
        self.assertEqual(encode_toml_value('"gpt-5.2"', value_type="raw"), '"gpt-5.2"')
        validate_toml_text('model = "gpt-5.2"\n')

    def test_ccswitch_constants(self) -> None:
        self.assertEqual(ccswitch.APP_NAME, "codex")
        self.assertIn("SaladDay/cc-switch-cli", ccswitch.INSTALL_SCRIPT_URL)

    def test_redact_login_status(self) -> None:
        text = "Logged in using an API key - sk-test***abcd"
        redacted = redact_login_status(text)
        self.assertNotIn("sk-test", redacted)
        self.assertIn("[已隐藏的 OpenAI API Key]", redacted)

    def test_xray_vless_reality_xhttp_config(self) -> None:
        plan = proxy.VlessRealityXhttpPlan(
            listen="0.0.0.0",
            server="example.com",
            port=443,
            uuid="11111111-1111-4111-8111-111111111111",
            email="test@example.com",
            reality_target="www.microsoft.com:443",
            server_name="www.microsoft.com",
            private_key="private",
            public_key="public",
            short_id="0123456789abcdef",
            path="/xhttp",
            xhttp_mode="auto",
            remark="test",
        )
        config = proxy.generate_xray_vless_reality_xhttp_config(plan)
        inbound = config["inbounds"][0]
        self.assertEqual(inbound["protocol"], "vless")
        self.assertEqual(inbound["settings"]["users"][0]["id"], plan.uuid)
        self.assertEqual(inbound["streamSettings"]["network"], "xhttp")
        self.assertEqual(inbound["streamSettings"]["security"], "reality")
        self.assertEqual(inbound["streamSettings"]["xhttpSettings"]["path"], "/xhttp")
        client = proxy.generate_vless_client_info(plan)
        self.assertIn("vless://", client)
        self.assertIn("type=xhttp", client)

    def test_singbox_hy2_config(self) -> None:
        plan = proxy.Hy2Plan(
            listen="::",
            server="example.com",
            port=443,
            server_name="example.com",
            user="default",
            password="pass",
            obfs_password="obfs",
            up_mbps=100,
            down_mbps=100,
            cert_path=Path("/etc/test/cert.pem"),
            key_path=Path("/etc/test/key.pem"),
            self_signed=True,
            insecure_client=True,
            remark="hy2",
        )
        config = proxy.generate_singbox_hy2_config(plan)
        inbound = config["inbounds"][0]
        self.assertEqual(inbound["type"], "hysteria2")
        self.assertEqual(inbound["listen_port"], 443)
        self.assertEqual(inbound["obfs"]["type"], "salamander")
        client = proxy.generate_hy2_client_info(plan)
        self.assertIn("hysteria2://", client)
        self.assertIn("obfs=salamander", client)

    def test_root_pipe_install_command_uses_sudo_for_non_root(self) -> None:
        command = proxy.root_pipe_install_command("https://example.com/install.sh", "bash", "install")
        self.assertIn('if [ "$(id -u)" -eq 0 ]', command)
        self.assertIn("sudo env", command)
        self.assertIn("bash -s -- install", command)
        self.assertIn("HTTPS_PROXY", command)

    def test_default_proxy_profiles(self) -> None:
        vless = proxy.VlessRealityXhttpDefaults()
        hy2 = proxy.Hy2Defaults()
        self.assertEqual(vless.port, 443)
        self.assertEqual(vless.server_name, "www.microsoft.com")
        self.assertEqual(vless.path, "/xhttp")
        self.assertEqual(hy2.port, 443)
        self.assertTrue(hy2.self_signed)

    def test_server_value_validation(self) -> None:
        self.assertTrue(proxy.is_reasonable_server("203.0.113.10"))
        self.assertTrue(proxy.is_reasonable_server("example.com"))
        self.assertFalse(proxy.is_reasonable_server("bad value"))
        self.assertFalse(proxy.is_reasonable_server("bad\nvalue"))

    def test_xray_x25519_parser_accepts_new_output(self) -> None:
        output = (
            "PrivateKey: private-value\n"
            "Password (PublicKey): public-value\n"
            "Hash32: ignored\n"
        )
        with patch("ops_tool.tasks.proxy._command_path", return_value="/usr/local/bin/xray"), patch(
            "ops_tool.tasks.proxy.run_command",
            return_value=CommandResult(["xray", "x25519"], 0, output, ""),
        ):
            private_key, public_key = proxy.generate_xray_x25519(self.make_ctx())
        self.assertEqual(private_key, "private-value")
        self.assertEqual(public_key, "public-value")


if __name__ == "__main__":
    unittest.main()
