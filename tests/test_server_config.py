import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from server_config import ConfigError, load_config  # noqa: E402

EXAMPLE = ROOT / "samples" / "print-server.example.toml"
ADMIN = "REPLACE-ME-admin-token-0000000000"
HOME = "REPLACE-ME-home-printer-token-000"
OFFICE = "REPLACE-ME-office-printer-token-0"
BRIEF = "REPLACE-ME-morning-brief-token-00"


class ServerConfigTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def write(self, text: str, mode: int = 0o600) -> Path:
        path = self.directory / "print-server.toml"
        path.write_text(text)
        path.chmod(mode)
        return path

    def example(self) -> Path:
        path = self.directory / "print-server.toml"
        shutil.copy(EXAMPLE, path)
        path.chmod(0o600)
        return path

    def problems(self, text: str, mode: int = 0o600) -> str:
        with self.assertRaises(ConfigError) as caught:
            load_config(self.write(text, mode))
        return str(caught.exception)

    def test_example_file_loads_with_every_section(self):
        config = load_config(self.example())
        self.assertEqual((config.host, config.port), ("127.0.0.1", 8787))
        self.assertEqual(config.database, self.directory / "data" / "print-server.db")
        self.assertEqual(config.access.team_domain, "your-team.cloudflareaccess.com")
        self.assertEqual(config.access.web_rate_limit, 10)
        self.assertEqual(list(config.printers), ["home", "office"])
        self.assertEqual((config.printers["home"].public, config.printers["office"].public), (True, False))
        self.assertEqual(config.printers["office"].place, "Desk at work")
        self.assertEqual(list(config.clients), ["morning-brief"])

    def test_tokens_map_to_exactly_one_identity(self):
        config = load_config(self.example())
        self.assertTrue(config.is_admin(ADMIN))
        self.assertFalse(config.is_admin(HOME))
        self.assertEqual(config.printer_for_token(HOME).id, "home")
        self.assertEqual(config.printer_for_token(OFFICE).id, "office")
        self.assertIsNone(config.printer_for_token(BRIEF))
        self.assertEqual(config.client_for_token(BRIEF).id, "morning-brief")
        self.assertIsNone(config.client_for_token(ADMIN))

    def test_wrong_tokens_are_refused_without_raising(self):
        config = load_config(self.example())
        for token in ["", HOME[:-1], HOME + "x", "tökén-with-non-ascii-characters"]:
            with self.subTest(token=token):
                self.assertFalse(config.is_admin(token))
                self.assertIsNone(config.printer_for_token(token))
                self.assertIsNone(config.client_for_token(token))

    def test_without_access_section_no_email_is_admin(self):
        text = EXAMPLE.read_text()
        start = text.index("# Optional. Without [access]")
        end = text.index("# One table per printer.")
        config = load_config(self.write(text[:start] + text[end:]))
        self.assertIsNone(config.access)
        self.assertFalse(config.is_admin_email("you@example.com"))

    def test_absolute_database_path_is_kept(self):
        text = EXAMPLE.read_text().replace('"data/print-server.db"', '"/var/lib/print/queue.db"')
        self.assertEqual(load_config(self.write(text)).database, Path("/var/lib/print/queue.db"))

    def test_lists_every_problem_in_one_message(self):
        message = self.problems(f"""
[server]
host = ""
port = "8787"
database = 42

[access]
team_domain = "team.cloudflareaccess.com"
web_rate_limit = true

[printers.Home]
name = "Home"
place = "Home office"
token = "{HOME}"
public = "yes"

[printers.short]
name = "Short"
place = "Somewhere"
token = ""

[printers.text]
token = "{OFFICE}"

[printers.stray]
token = "{ADMIN}"
name = "Stray"
place = "Nowhere"

[clients."morning brief"]
token = "{HOME}"
""")
        expected = [
            "server.host: empty",
            "server.port: must be an integer",
            "server.database: must be a string",
            "server.admin_token: missing",
            "access.audience: missing",
            "access.web_rate_limit: must be an integer",
            "printers.Home: id must be lowercase",
            "printers.Home.public: must be true or false",
            "printers.short.token: empty",
            "printers.text.name: missing",
            "printers.text.place: missing",
            "clients.morning brief: id must be lowercase",
            "clients.morning brief.token: same token as printers.Home.token",
        ]
        for problem in expected:
            self.assertIn(problem, message)
        self.assertEqual(message.count("\n  - "), len(expected))
        self.assertNotIn(HOME, message)

    def test_unknown_keys_are_reported_in_every_table(self):
        text = (
            EXAMPLE.read_text()
            .replace("public = true", "publik = true")
            .replace("port = 8787", "port = 8787\nhots = \"0.0.0.0\"")
            .replace("web_rate_limit = 10", "web_rate_limt = 10")
            .replace(f'token = "{BRIEF}"', f'token = "{BRIEF}"\nschedule = "07:00"')
        )
        message = self.problems(text + '\n[printer.desk]\nname = "Desk"\n')
        expected = [
            "printers.home.publik: unknown key",
            "server.hots: unknown key",
            "access.web_rate_limt: unknown key",
            "access.web_rate_limit: missing",
            "clients.morning-brief.schedule: unknown key",
            "  - printer: unknown key",
        ]
        for problem in expected:
            self.assertIn(problem, message)
        self.assertEqual(message.count("\n  - "), len(expected))

    def test_a_short_token_loads_and_an_empty_one_is_refused(self):
        config = load_config(self.write(EXAMPLE.read_text().replace(ADMIN, "moranlindo")))
        self.assertTrue(config.is_admin("moranlindo"))
        message = self.problems(EXAMPLE.read_text().replace(ADMIN, ""))
        self.assertIn("server.admin_token: empty", message)

    def test_no_token_appears_in_repr_or_str(self):
        config = load_config(self.example())
        for text in [repr(config), str(config), repr(config.printers["home"]), repr(config.clients["morning-brief"])]:
            for token in [ADMIN, HOME, OFFICE, BRIEF]:
                self.assertNotIn(token, text)
        self.assertIn("home", repr(config))

    def with_admin_emails(self, line: str) -> Path:
        text = EXAMPLE.read_text().replace('# admin_emails = ["you@example.com"]', line)
        self.assertIn(line, text)
        return self.write(text)

    def test_admin_emails_allow_listed_logins_case_insensitively(self):
        config = load_config(self.with_admin_emails('admin_emails = ["Felipe@Example.com", "ops@example.org"]'))
        self.assertEqual(config.access.admin_emails, ("felipe@example.com", "ops@example.org"))
        for email in ["felipe@example.com", "FELIPE@EXAMPLE.COM", "ops@example.org"]:
            self.assertTrue(config.is_admin_email(email), email)
        for email in ["friend@example.com", "felipe@example.co", "", "felipe@example.com.evil.org"]:
            self.assertFalse(config.is_admin_email(email), email)

    def test_admin_emails_never_match_non_ascii_lookalikes(self):
        config = load_config(self.with_admin_emails('admin_emails = ["mark@example.com"]'))
        self.assertTrue(config.is_admin_email("MARK@example.com"))
        self.assertFalse(config.is_admin_email("mar\u212a@example.com"))
        message = self.problems(EXAMPLE.read_text().replace(
            '# admin_emails = ["you@example.com"]', 'admin_emails = ["mar\u212a@example.com"]'
        ))
        self.assertIn("access.admin_emails[0]: not an email address", message)

    def test_admin_emails_default_to_nobody(self):
        config = load_config(self.example())
        self.assertEqual(config.access.admin_emails, ())
        self.assertFalse(config.is_admin_email("felipe@example.com"))

    def test_admin_emails_reports_each_invalid_entry(self):
        message = self.problems(
            EXAMPLE.read_text().replace(
                '# admin_emails = ["you@example.com"]', 'admin_emails = ["ok@example.com", "felipe", 42, "a b@example.com"]'
            )
        )
        self.assertIn("access.admin_emails[1]: not an email address: 'felipe'", message)
        self.assertIn("access.admin_emails[2]: not an email address: 42", message)
        self.assertIn("access.admin_emails[3]: not an email address", message)
        self.assertEqual(message.count("\n  - "), 3)
        not_a_list = EXAMPLE.read_text().replace('# admin_emails = ["you@example.com"]', 'admin_emails = "ok@example.com"')
        self.assertIn("access.admin_emails: must be a list of email addresses", self.problems(not_a_list))

    def with_allowed_origins(self, line: str) -> str:
        return EXAMPLE.read_text().replace('# allowed_origins = ["https://app.example.com"]', line)

    def test_allowed_origins_default_to_none(self):
        self.assertEqual(load_config(self.example()).access.allowed_origins, ())

    def test_allowed_origins_keep_exact_origins(self):
        origins = ("https://mise-en-place.felipemoran.com", "http://localhost:5173", "http://localhost:443",
                   "https://app.example.com:65535")
        line = f"allowed_origins = {list(origins)}".replace("'", '"')
        config = load_config(self.write(self.with_allowed_origins(line)))
        self.assertEqual(config.access.allowed_origins, origins)

    def test_allowed_origins_refuse_anything_but_an_exact_origin(self):
        for origin in [
            "https://app.example.com/",
            "https://app.example.com/print",
            "*",
            "https://*.example.com",
            "app.example.com",
            "https://App.Example.com",
            "ftp://app.example.com",
            "https://app.example.com?x=1",
        ]:
            with self.subTest(origin=origin):
                message = self.problems(self.with_allowed_origins(f'allowed_origins = ["{origin}"]'))
                self.assertIn(f"access.allowed_origins[0]: not an origin: '{origin}'", message)
        for origin in ["https://app.example.com:443", "http://app.example.com:80", "https://app.example.com:65536",
                       "http://localhost:99999"]:
            with self.subTest(origin=origin):
                message = self.problems(self.with_allowed_origins(f'allowed_origins = ["{origin}"]'))
                self.assertIn(f"access.allowed_origins[0]: bad port in '{origin}'", message)
        message = self.problems(self.with_allowed_origins('allowed_origins = "https://app.example.com"'))
        self.assertIn("access.allowed_origins: must be a list of origins", message)

    def test_team_domain_must_be_a_bare_hostname(self):
        for team_domain in [
            "https://your-team.cloudflareaccess.com",
            "your-team.cloudflareaccess.com/",
            "your-team .cloudflareaccess.com",
            "your-team.cloudflareaccess.com:443",
            "localhost",
        ]:
            with self.subTest(team_domain=team_domain):
                text = EXAMPLE.read_text().replace("your-team.cloudflareaccess.com", team_domain)
                self.assertIn("access.team_domain: must be a bare hostname", self.problems(text))

    def test_admin_token_reused_by_a_printer_is_refused(self):
        text = EXAMPLE.read_text().replace(HOME, ADMIN)
        message = self.problems(text)
        self.assertIn("printers.home.token: same token as server.admin_token", message)

    def test_missing_server_section_and_non_table_entries_are_refused(self):
        message = self.problems('printers = "home"\n\n[clients]\nbrief = "token"\n')
        self.assertIn("server: missing", message)
        self.assertIn("printers: must be a table", message)
        self.assertIn("clients.brief: must be a table", message)

    def test_port_out_of_range_is_refused(self):
        message = self.problems(EXAMPLE.read_text().replace("port = 8787", "port = 70000"))
        self.assertIn("server.port: must be between 1 and 65535", message)

    @unittest.skipUnless(os.name == "posix", "POSIX file modes only")
    def test_file_readable_by_others_is_refused_with_the_chmod_command(self):
        for mode in [0o644, 0o640, 0o604]:
            with self.subTest(mode=oct(mode)):
                path = self.write(EXAMPLE.read_text(), mode)
                with self.assertRaises(ConfigError) as caught:
                    load_config(path)
                self.assertIn(f"chmod 600 {path}", str(caught.exception))

    def test_invalid_toml_and_missing_file_raise_config_error(self):
        self.assertIn("not valid TOML", self.problems("[server\nhost = 1"))
        with self.assertRaises(ConfigError) as caught:
            load_config(self.directory / "absent.toml")
        self.assertIn("absent.toml", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
