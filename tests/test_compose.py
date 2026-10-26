import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.yaml"
TEST_DIR = ROOT / "deploy" / "compose-test"
TEST_CONFIG = TEST_DIR / "server.toml"
SECRET_LIKE = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9_-])")
PROFILES = {"server": [], "cloudflared": ["tunnel"], "printer-home": ["test"], "printer-work": ["test"],
            "check": ["check"]}


def _compose_config(**variables: str) -> dict:
    if shutil.which("docker") is None:
        raise unittest.SkipTest("docker is missing, so `docker compose config` cannot run")
    with tempfile.NamedTemporaryFile("w", suffix=".env") as empty:
        # An empty env file and a bare environment: the operator's .env or shell may hold the real tunnel token.
        env = {name: os.environ[name] for name in ("PATH", "HOME", "DOCKER_CONFIG", "DOCKER_HOST") if name in os.environ}
        env["PRINT_SERVER_CONFIG"] = str(TEST_CONFIG)
        env.update(variables)
        command = ["docker", "compose", "-f", str(COMPOSE), "--env-file", empty.name]
        for profile in ("tunnel", "test", "check"):
            command += ["--profile", profile]
        result = subprocess.run(command + ["config", "--format", "json"], capture_output=True, text=True, env=env,
                                cwd=ROOT, check=False)
    if result.returncode != 0 and "is not a docker command" in result.stderr:
        raise unittest.SkipTest("docker compose is missing")
    if result.returncode != 0:
        raise AssertionError(f"docker compose config failed:\n{result.stderr}")
    return json.loads(result.stdout)


class ComposeConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = _compose_config()
        cls.services = cls.config["services"]

    def test_services_and_their_profiles(self):
        self.assertEqual({name: service.get("profiles", []) for name, service in self.services.items()}, PROFILES)

    def test_the_real_project_name_differs_from_the_test_one_so_the_test_teardown_cannot_delete_real_data(self):
        self.assertEqual(self.config["name"], "daily-printer")
        self.assertIn("-p daily-printer-test", (ROOT / "Makefile").read_text())

    def test_a_test_build_gets_its_own_image_tag_so_it_never_retags_the_real_server_image(self):
        ours = {name for name, service in self.services.items() if service["image"].startswith("daily-printer:")}
        self.assertEqual(ours, {"server", "printer-home", "printer-work", "check"})
        self.assertEqual({self.services[name]["image"] for name in ours}, {"daily-printer:local"})
        tagged = _compose_config(PRINT_SERVER_IMAGE_TAG="test")["services"]
        self.assertEqual({tagged[name]["image"] for name in ours}, {"daily-printer:test"})
        self.assertIn("PRINT_SERVER_IMAGE_TAG=test docker compose -p daily-printer-test", (ROOT / "Makefile").read_text())

    def test_the_server_is_published_on_loopback_only(self):
        self.assertEqual(self.services["server"]["ports"],
                         [{"mode": "ingress", "host_ip": "127.0.0.1", "target": 8787, "published": "8787",
                           "protocol": "tcp"}])
        for name, service in self.services.items():
            for port in service.get("ports", []):
                self.assertEqual(port["host_ip"], "127.0.0.1", name)

    def test_the_config_is_mounted_read_only_and_the_data_on_a_named_volume(self):
        mounts = {mount["target"]: mount for mount in self.services["server"]["volumes"]}
        self.assertEqual(mounts["/config/server.toml"]["source"], str(TEST_CONFIG))
        self.assertTrue(mounts["/config/server.toml"]["read_only"])
        self.assertEqual((mounts["/data"]["type"], mounts["/data"]["source"]), ("volume", "data"))

    def test_the_server_has_a_healthcheck_on_a_route_that_needs_no_token(self):
        test = self.services["server"]["healthcheck"]["test"]
        self.assertEqual(test[0], "CMD")
        self.assertIn(":8787/admin", " ".join(test))

    def test_the_tunnel_token_comes_from_the_environment_not_the_file(self):
        self.assertEqual(self.services["cloudflared"]["environment"], {"TUNNEL_TOKEN": None})

    def test_the_compose_file_holds_no_secret_literal(self):
        text = COMPOSE.read_text()
        self.assertEqual(SECRET_LIKE.findall(text), [])
        self.assertNotRegex(text, r"(?i)token\s*[:=]\s*\S")
        for token in tomllib.loads(TEST_CONFIG.read_text())["printers"].values():
            self.assertNotIn(token["token"], text)


class ComposeTestConfigTest(unittest.TestCase):
    def setUp(self):
        self.text = TEST_CONFIG.read_text()
        self.config = tomllib.loads(self.text)

    def test_the_file_says_it_is_for_tests_only(self):
        self.assertTrue(self.text.startswith("# TEST ONLY:"), self.text.splitlines()[0])

    def test_every_token_is_marked_test_only_except_the_demo_admin_token(self):
        self.assertEqual(self.config["server"]["admin_token"], "moranlindo")
        tokens = [table["token"] for section in ("printers", "clients") for table in self.config[section].values()]
        for token in tokens:
            self.assertTrue(token.startswith("test-only-"), token)

    def test_each_fake_printer_token_file_matches_its_printer(self):
        for printer_id, table in self.config["printers"].items():
            self.assertEqual((TEST_DIR / f"{printer_id}.token").read_text().strip(), table["token"])

    def test_the_server_listens_on_every_interface_and_keeps_its_data_on_the_volume(self):
        self.assertEqual(self.config["server"]["host"], "0.0.0.0")
        self.assertEqual(self.config["server"]["port"], 8787)
        self.assertEqual(self.config["server"]["database"], "/data/print-server.db")


class DockerignoreTest(unittest.TestCase):
    def test_local_state_stays_out_of_the_build_context(self):
        entries = set((ROOT / ".dockerignore").read_text().split())
        for entry in (".venv", "**/node_modules", "web/dist", "data", ".workspaces", "tasks", ".jj", ".git", "**/.env*"):
            self.assertIn(entry, entries)

    def test_git_ignores_every_env_file_where_the_operator_keeps_credentials(self):
        entries = set((ROOT / ".gitignore").read_text().split())
        self.assertLessEqual({".env", ".env.*"}, entries)


if __name__ == "__main__":
    unittest.main()
