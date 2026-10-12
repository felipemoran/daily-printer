import os
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from server_config import load_config  # noqa: E402

DEPLOY = ROOT / "deploy"
WIZARD = DEPLOY / "wizard.sh"
CLOUDFLARED = DEPLOY / "cloudflared" / "config.example.yml"
PLISTS = sorted((DEPLOY / "launchd").glob("*.plist"))
UNITS = sorted((DEPLOY / "systemd").glob("*.service"))
PLACEHOLDER = re.compile(r"__([A-Z][A-Z_]*[A-Z])__")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SECRET_LIKE = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9_-])")


def wizard_placeholders() -> set[str]:
    match = re.search(r'^PLACEHOLDERS="([^"]*)"', WIZARD.read_text(), re.MULTILINE)
    return set(match.group(1).split())


def entry_point_flags(script: str) -> set[str]:
    return set(re.findall(r'add_argument\(\s*"(--[a-z-]+)"', (ROOT / script).read_text()))


def parse_ingress(text: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Parse the YAML subset the cloudflared example uses: top-level scalars and one list of flat mappings."""
    top: dict[str, str] = {}
    rules: list[dict[str, str]] = []
    in_ingress = False
    for number, line in enumerate(text.splitlines(), 1):
        if "\t" in line:
            raise ValueError(f"line {number}: YAML forbids tabs for indentation")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        item = re.fullmatch(r"  - ([a-z-]+): (\S.*)", line)
        more = re.fullmatch(r"    ([a-z-]+): (\S.*)", line)
        scalar = re.fullmatch(r"([a-z-]+):(?: (\S.*))?", line)
        if item and in_ingress:
            rules.append({item.group(1): item.group(2)})
        elif more and rules:
            if more.group(1) in rules[-1]:
                raise ValueError(f"line {number}: duplicate key {more.group(1)}")
            rules[-1][more.group(1)] = more.group(2)
        elif scalar:
            in_ingress = scalar.group(1) == "ingress" and scalar.group(2) is None
            if not in_ingress:
                top[scalar.group(1)] = scalar.group(2) or ""
        else:
            raise ValueError(f"line {number}: not in the expected YAML subset: {line!r}")
    return top, rules


def check_ingress(text: str) -> list[dict[str, str]]:
    top, rules = parse_ingress(text)
    if set(top) != {"tunnel", "credentials-file"}:
        raise ValueError(f"top-level keys {sorted(top)}")
    if not rules:
        raise ValueError("no ingress rules")
    for rule in rules:
        if not set(rule) <= {"hostname", "path", "service"} or "service" not in rule:
            raise ValueError(f"bad rule {rule}")
        if not re.fullmatch(r"http://127\.0\.0\.1:__PORT__|http_status:\d{3}", rule["service"]):
            raise ValueError(f"unexpected service {rule['service']}")
    if set(rules[-1]) != {"service"}:
        raise ValueError("the last rule must be a catch-all with only a service")
    return rules


def config_tool_source() -> str:
    match = re.search(r"<<'PY'\n(.*?)\nPY\n", WIZARD.read_text(), re.DOTALL)
    return match.group(1)


class DeployFilesTest(unittest.TestCase):
    def test_every_plist_parses_and_runs_an_existing_entry_point_with_its_real_flags(self):
        self.assertEqual([path.name for path in PLISTS], ["com.daily-printer.device.plist", "com.daily-printer.server.plist"])
        for path in PLISTS:
            with self.subTest(path.name):
                with path.open("rb") as file:
                    job = plistlib.load(file)
                self.assertEqual(job["Label"], path.stem)
                arguments = job["ProgramArguments"]
                self.assertEqual(arguments[:2], ["__UV__", "run"])
                self.assertTrue((ROOT / arguments[2]).is_file(), arguments[2])
                flags = {argument for argument in arguments[3:] if argument.startswith("--")}
                self.assertTrue(flags <= entry_point_flags(arguments[2]), flags)
                self.assertIs(job["KeepAlive"], True)
                self.assertEqual(job["WorkingDirectory"], "__REPO__")
                self.assertTrue(job["StandardErrorPath"].startswith("__LOG_DIR__/"))

    def test_only_the_server_plist_sets_username_because_it_is_a_system_daemon(self):
        jobs = {path.stem: plistlib.loads(path.read_bytes()) for path in PLISTS}
        self.assertEqual(jobs["com.daily-printer.server"]["UserName"], "__SERVICE_USER__")
        self.assertNotIn("UserName", jobs["com.daily-printer.device"])

    def test_every_unit_has_the_required_sections_and_directives(self):
        self.assertEqual([path.name for path in UNITS], ["print-device.service", "print-server.service"])
        for path in UNITS:
            with self.subTest(path.name):
                sections: dict[str, dict[str, str]] = {}
                current = None
                for line in path.read_text().splitlines():
                    if not line.strip() or line.startswith("#"):
                        continue
                    header = re.fullmatch(r"\[(\w+)\]", line)
                    if header:
                        current = sections.setdefault(header.group(1), {})
                        continue
                    key, _, value = line.partition("=")
                    self.assertIsNotNone(current, f"directive outside a section: {line}")
                    current[key] = value
                self.assertEqual(list(sections), ["Unit", "Service", "Install"])
                service = sections["Service"]
                self.assertEqual(service["User"], "__SERVICE_USER__")
                self.assertEqual(service["Restart"], "always")
                self.assertEqual(sections["Install"]["WantedBy"], "multi-user.target")
                command = service["ExecStart"].split()
                self.assertEqual(command[:2], ["__UV__", "run"])
                self.assertTrue((ROOT / command[2]).is_file(), command[2])
                flags = {word for word in command[3:] if word.startswith("--")}
                self.assertTrue(flags <= entry_point_flags(command[2]), flags)

    def test_device_unit_waits_for_the_network_because_it_dials_out(self):
        unit = (DEPLOY / "systemd" / "print-device.service").read_text()
        self.assertIn("Wants=network-online.target", unit)
        self.assertIn("After=network-online.target", unit)

    def test_cloudflared_example_routes_only_device_path_on_device_host_and_ends_with_catch_all(self):
        rules = check_ingress(CLOUDFLARED.read_text())
        device = [rule for rule in rules if rule.get("hostname") == "__DEVICE_HOST__"]
        self.assertEqual(device[0], {"hostname": "__DEVICE_HOST__", "path": "^/device$", "service": "http://127.0.0.1:__PORT__"})
        self.assertEqual(device[1], {"hostname": "__DEVICE_HOST__", "service": "http_status:404"})
        sender = [rule for rule in rules if rule.get("hostname") == "__SENDER_HOST__"]
        self.assertEqual(sender, [{"hostname": "__SENDER_HOST__", "service": "http://127.0.0.1:__PORT__"}])

    def test_ingress_check_rejects_a_config_without_a_final_catch_all(self):
        broken = CLOUDFLARED.read_text().replace("  - service: http_status:404\n", "")
        with self.assertRaisesRegex(ValueError, "catch-all"):
            check_ingress(broken)
        with self.assertRaisesRegex(ValueError, "tabs"):
            check_ingress(CLOUDFLARED.read_text().replace("  - hostname", "\t- hostname", 1))

    def test_wizard_substitutes_every_placeholder_the_templates_use(self):
        used = set()
        for path in [*PLISTS, *UNITS, CLOUDFLARED]:
            used |= set(PLACEHOLDER.findall(path.read_text()))
        self.assertTrue(used)
        self.assertEqual(used - wizard_placeholders(), set())

    def render(self, template: Path, values: dict[str, str]) -> subprocess.CompletedProcess:
        text = WIZARD.read_text()
        functions = "\n".join(
            re.search(rf"^{name}\(\) \{{[^\n]*\}}$|^{name}\(\) \{{\n.*?^\}}", text, re.MULTILINE | re.DOTALL).group(0)
            for name in ("die", "render")
        )
        placeholders = re.search(r'^PLACEHOLDERS=".*"$', text, re.MULTILINE).group(0)
        script = f'set -euo pipefail\nRED=""; RESET=""\n{placeholders}\n{functions}\nrender "$1"\n'
        return subprocess.run(["bash", "-c", script, "render", str(template)], capture_output=True, text=True, env={**os.environ, **values})

    def test_render_fills_every_template_with_path_values(self):
        values = {name: f"/Users/someone/{name.lower()}" for name in wizard_placeholders()}
        values.update(PORT="8787", TUNNEL_ID="tunnel-id", DEVICE_HOST="device.example.com", SENDER_HOST="print.example.com")
        for template in [*PLISTS, *UNITS, CLOUDFLARED]:
            with self.subTest(template.name):
                result = self.render(template, values)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("__", result.stdout)
                if template.suffix == ".plist":
                    job = plistlib.loads(result.stdout.encode())
                    self.assertEqual(job["ProgramArguments"][0], values["UV"])
                    self.assertEqual(job["WorkingDirectory"], values["REPO"])
        self.assertIn("service: http://127.0.0.1:8787", self.render(CLOUDFLARED, values).stdout)

    def test_render_refuses_a_template_whose_placeholder_has_no_value(self):
        result = self.render(CLOUDFLARED, {"TUNNEL_ID": "tunnel-id"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no value for __", result.stderr)

    def access_check(self, answer: str, team_domain: str = "team.cloudflareaccess.com") -> int:
        function = re.search(r"^access_protects_sender\(\) \{\n.*?^\}", WIZARD.read_text(), re.MULTILINE | re.DOTALL).group(0)
        script = f'set -euo pipefail\ncurl() {{ printf "%s" "$ANSWER"; }}\n{function}\naccess_protects_sender\n'
        env = {**os.environ, "ANSWER": answer, "TEAM_DOMAIN": team_domain, "SENDER_HOST": "print.example.com"}
        return subprocess.run(["bash", "-c", script], capture_output=True, env=env).returncode

    def test_access_check_accepts_only_a_redirect_to_the_configured_team(self):
        login = "https://team.cloudflareaccess.com/cdn-cgi/access/login/print.example.com?kid=abc"
        self.assertEqual(self.access_check(f"302 {login}"), 0)
        for answer in (
            "302 https://evil-cloudflareaccess.com/cdn-cgi/access/login",
            "302 https://team.cloudflareaccess.com.evil/cdn-cgi/access/login",
            "302 https://evil.example.com/?u=team.cloudflareaccess.com/",
            f"200 {login}",
            "200 ",
        ):
            with self.subTest(answer):
                self.assertNotEqual(self.access_check(answer), 0)
        self.assertNotEqual(self.access_check(f"302 {login}", team_domain="taem.cloudflareaccess.com"), 0)

    def test_wizard_passes_bash_syntax_check_and_is_executable(self):
        result = subprocess.run(["bash", "-n", str(WIZARD)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(WIZARD.stat().st_mode & stat.S_IXUSR)

    def test_wizard_stage_count_matches_the_stages_each_role_runs(self):
        text = WIZARD.read_text()
        for role in ("server", "device"):
            with self.subTest(role):
                blocks = re.findall(rf"^  {role}\)\n(.*?)\n    ;;", text, re.MULTILINE | re.DOTALL)
                block = next(block for block in blocks if "TOTAL_STAGES" in block)
                total = int(re.search(r"TOTAL_STAGES=(\d+)", block).group(1))
                calls = re.findall(r"^    (stage_\w+)$", block, re.MULTILINE)
                stages = sum(len(re.findall(r'^  stage "', self.function(text, call), re.MULTILINE)) for call in calls)
                self.assertEqual(stages, total)

    @staticmethod
    def function(text: str, name: str) -> str:
        return re.search(rf"^{name}\(\) \{{\n(.*?)^\}}", text, re.MULTILINE | re.DOTALL).group(1)

    def test_no_deploy_file_contains_a_real_looking_token_or_tunnel_id(self):
        paths = [*DEPLOY.rglob("*"), ROOT / "docs" / "setup-deploy.md"]
        for path in [path for path in paths if path.is_file()]:
            text = path.read_text()
            with self.subTest(path.name):
                self.assertEqual(SECRET_LIKE.findall(text), [])
                self.assertEqual(UUID.findall(text), [])
                self.assertNotIn("eyJ", text)

    def test_token_scan_flags_a_generated_token(self):
        import secrets

        self.assertTrue(SECRET_LIKE.findall(f'token = "{secrets.token_urlsafe(32)}"'))


class WizardConfigToolTest(unittest.TestCase):
    """Runs the Python helper embedded in deploy/wizard.sh against a temp config."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.config = self.directory / "config.toml"

    def tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-", str(self.config), *args],
            input=config_tool_source(),
            capture_output=True,
            text=True,
            env={**os.environ, "REPO": str(ROOT)},
        )

    def test_config_written_by_the_wizard_loads_with_mode_0600_and_survives_a_rerun(self):
        self.assertEqual(self.tool("init").returncode, 0)
        self.assertEqual(self.tool("add-printer", "home", 'Home "den"', "Living room", "yes").returncode, 0)
        self.assertEqual(self.tool("add-printer", "office", "Office", "Desk at work", "no").returncode, 0)
        self.assertEqual(self.tool("set-access", "team.cloudflareaccess.com", "aud-tag", " A@Example.com, b@example.com ").returncode, 0)
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        first = load_config(self.config)

        rerun = self.tool("init")
        self.assertIn("kept", rerun.stdout)
        again = load_config(self.config)
        self.assertEqual(again.admin_token, first.admin_token)
        self.assertEqual(again.printers["home"].token, first.printers["home"].token)
        self.assertEqual(again.printers["home"].name, 'Home "den"')
        self.assertTrue(again.printers["home"].public)
        self.assertFalse(again.printers["office"].public)
        self.assertEqual(again.access.admin_emails, ("a@example.com", "b@example.com"))
        self.assertEqual(again.access.web_rate_limit, 10)
        self.assertEqual(self.tool("validate").returncode, 0)

    def test_access_defaults_come_from_a_hand_edited_config(self):
        self.tool("init")
        self.assertEqual(self.tool("access").stdout, "TEAM_DOMAIN=\nACCESS_AUD=\nADMIN_EMAILS=\n")
        self.tool("set-access", "old.cloudflareaccess.com", "old-aud", "")
        edited = self.config.read_text().replace("old.cloudflareaccess.com", "new.cloudflareaccess.com").replace("old-aud", "new-aud")
        self.config.write_text(edited.replace("admin_emails = []", 'admin_emails = ["me@example.com", "you@example.com"]'))
        result = self.tool("access")
        self.assertEqual(
            result.stdout,
            "TEAM_DOMAIN=new.cloudflareaccess.com\nACCESS_AUD=new-aud\nADMIN_EMAILS=me@example.com,you@example.com\n",
        )
        self.assertNotIn(load_config(self.config).admin_token, result.stdout)

    def test_listing_printers_never_prints_a_token(self):
        self.tool("init")
        self.tool("add-printer", "home", "Home", "Home office", "yes")
        token = load_config(self.config).printers["home"].token
        listing = self.tool("printers")
        self.assertEqual(listing.stdout, "home\tHome\tpublic\n")
        self.assertNotIn(token, listing.stdout + self.tool("validate").stdout)
        self.assertEqual(self.tool("token", "home").stdout.strip(), token)

    def test_admin_token_file_holds_the_config_token_with_mode_0600(self):
        self.tool("init")
        destination = self.directory / "admin-token"
        self.assertEqual(self.tool("admin-token", str(destination)).returncode, 0)
        self.assertEqual(destination.read_text().strip(), load_config(self.config).admin_token)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)

    def test_add_printer_refuses_a_bad_id_and_a_duplicate(self):
        self.tool("init")
        bad = self.tool("add-printer", "Home Office", "Home", "Den", "yes")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("lowercase", bad.stderr)
        self.assertEqual(self.tool("add-printer", "home", "Home", "Den", "yes").returncode, 0)
        duplicate = self.tool("add-printer", "home", "Home", "Den", "yes")
        self.assertEqual(duplicate.returncode, 2)
        self.assertIn("already exists", duplicate.stderr)

    def test_validate_reports_a_config_other_users_can_read(self):
        self.tool("init")
        self.config.chmod(0o644)
        result = self.tool("validate")
        self.assertEqual(result.returncode, 2)
        self.assertIn("chmod 600", result.stderr)

    def test_init_on_an_existing_config_restores_mode_0600(self):
        self.tool("init")
        self.config.chmod(0o644)
        self.tool("init")
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)


@unittest.skipUnless(shutil.which("shellcheck"), "shellcheck is not installed")
class ShellcheckTest(unittest.TestCase):
    def test_wizard_has_no_shellcheck_findings(self):
        result = subprocess.run(["shellcheck", str(WIZARD)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
