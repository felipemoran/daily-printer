"""Print server config: one TOML file with the listen address, tokens and printers."""

from __future__ import annotations

import hmac
import os
import re
import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_HOSTNAME = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
# Lowercase only: a browser sends the Origin header in lowercase, so another case would never match.
_ORIGIN = re.compile(r"(https?)://[a-z0-9-]+(?:\.[a-z0-9-]+)*(?::([0-9]{1,5}))?")
# A browser leaves the scheme's default port out of the Origin header, so an origin that names it never matches.
_DEFAULT_PORTS = {"http": 80, "https": 443}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Printer:
    id: str
    name: str
    place: str
    token: str = field(repr=False)
    public: bool


@dataclass(frozen=True)
class Client:
    id: str
    token: str = field(repr=False)


@dataclass(frozen=True)
class Access:
    team_domain: str
    audience: str
    web_rate_limit: int
    admin_emails: tuple[str, ...]
    allowed_origins: tuple[str, ...]


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    database: Path
    admin_token: str = field(repr=False)
    access: Access | None
    printers: dict[str, Printer]
    clients: dict[str, Client]

    def is_admin_email(self, email: str) -> bool:
        # str.lower() maps some non-ASCII letters to ASCII: KELVIN SIGN (U+212A) becomes "k".
        return self.access is not None and email.isascii() and email.lower() in self.access.admin_emails

    def is_admin(self, token: str) -> bool:
        return _same(token, self.admin_token)

    def printer_for_token(self, token: str) -> Printer | None:
        return next((printer for printer in self.printers.values() if _same(token, printer.token)), None)

    def client_for_token(self, token: str) -> Client | None:
        return next((client for client in self.clients.values() if _same(token, client.token)), None)


def _same(given: str, expected: str) -> bool:
    # compare_digest raises TypeError on a str with non-ASCII characters; bytes accept anything.
    return hmac.compare_digest(given.encode(), expected.encode())


class _Reader:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.tokens: dict[str, str] = {}

    def table(self, data: dict[str, Any], key: str, where: str, required: bool = True) -> dict[str, Any] | None:
        value = data.get(key)
        if value is None:
            if required:
                self.problems.append(f"{where}: missing")
            return None
        if not isinstance(value, dict):
            self.problems.append(f"{where}: must be a table")
            return None
        return value

    def text(self, data: dict[str, Any], key: str, where: str) -> str:
        value = data.get(key)
        if value is None:
            self.problems.append(f"{where}.{key}: missing")
        elif not isinstance(value, str):
            self.problems.append(f"{where}.{key}: must be a string")
        elif not value.strip():
            self.problems.append(f"{where}.{key}: empty")
        else:
            return value
        return ""

    def number(self, data: dict[str, Any], key: str, where: str, low: int, high: int) -> int:
        value = data.get(key)
        # bool is a subclass of int, so `port = true` would pass a plain isinstance check.
        if value is None:
            self.problems.append(f"{where}.{key}: missing")
        elif not isinstance(value, int) or isinstance(value, bool):
            self.problems.append(f"{where}.{key}: must be an integer")
        elif not low <= value <= high:
            self.problems.append(f"{where}.{key}: must be between {low} and {high}")
        else:
            return value
        return 0

    def flag(self, data: dict[str, Any], key: str, where: str) -> bool:
        value = data.get(key, False)
        if not isinstance(value, bool):
            self.problems.append(f"{where}.{key}: must be true or false")
            return False
        return value

    def token(self, data: dict[str, Any], key: str, where: str) -> str:
        value = self.text(data, key, where)
        if not value:
            return ""
        place = f"{where}.{key}"
        if value in self.tokens:
            self.problems.append(f"{place}: same token as {self.tokens[value]}")
        else:
            self.tokens[value] = place
        return value

    def unknown(self, data: dict[str, Any], allowed: set[str], where: str) -> None:
        for key in data:
            if key not in allowed:
                self.problems.append(f"{where}{key}: unknown key")

    def emails(self, data: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
        value = data.get(key, [])
        if not isinstance(value, list):
            self.problems.append(f"{where}.{key}: must be a list of email addresses")
            return ()
        emails = []
        for index, email in enumerate(value):
            if isinstance(email, str) and email.isascii() and _EMAIL.fullmatch(email):
                emails.append(email.lower())
            else:
                self.problems.append(f"{where}.{key}[{index}]: not an email address: {email!r}")
        return tuple(emails)

    def origins(self, data: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
        value = data.get(key, [])
        if not isinstance(value, list):
            self.problems.append(f"{where}.{key}: must be a list of origins")
            return ()
        origins = []
        for index, origin in enumerate(value):
            match = _ORIGIN.fullmatch(origin) if isinstance(origin, str) else None
            port = match and match[2] and int(match[2])
            if match and port and (port > 65535 or port == _DEFAULT_PORTS[match[1]]):
                self.problems.append(
                    f"{where}.{key}[{index}]: bad port in {origin!r}; use a port from 1 to 65535, "
                    f"and leave out {match[1]}'s default port {_DEFAULT_PORTS[match[1]]}")
            elif match and port != 0:
                origins.append(origin)
            else:
                self.problems.append(
                    f"{where}.{key}[{index}]: not an origin: {origin!r}; write scheme://host[:port] in lowercase, "
                    f"such as https://app.example.com, with no path, trailing slash or *")
        return tuple(origins)

    def slug(self, name: str, where: str) -> None:
        if not _SLUG.fullmatch(name):
            self.problems.append(f"{where}: id must be lowercase letters, digits and single hyphens")


def load_config(path: str | Path) -> ServerConfig:
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ConfigError(f"Cannot read config {path}: {error.strerror}") from None
    reader = _Reader()
    if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        reader.problems.append(f"file is readable by other users; run: chmod 600 {path}")
    try:
        data = tomllib.loads(raw.decode())
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Invalid config {path}: not valid TOML: {error}") from None

    reader.unknown(data, {"server", "access", "printers", "clients"}, "")
    server = reader.table(data, "server", "server") or {}
    reader.unknown(server, {"host", "port", "database", "admin_token"}, "server.")
    host = reader.text(server, "host", "server")
    port = reader.number(server, "port", "server", 1, 65535)
    database = reader.text(server, "database", "server")
    admin_token = reader.token(server, "admin_token", "server")

    access = None
    access_table = reader.table(data, "access", "access", required=False)
    if access_table is not None:
        allowed = {"team_domain", "audience", "web_rate_limit", "admin_emails", "allowed_origins"}
        reader.unknown(access_table, allowed, "access.")
        team_domain = reader.text(access_table, "team_domain", "access")
        if team_domain and not _HOSTNAME.fullmatch(team_domain):
            reader.problems.append("access.team_domain: must be a bare hostname such as <team>.cloudflareaccess.com")
        access = Access(
            team_domain=team_domain,
            audience=reader.text(access_table, "audience", "access"),
            web_rate_limit=reader.number(access_table, "web_rate_limit", "access", 1, 1_000_000),
            admin_emails=reader.emails(access_table, "admin_emails", "access"),
            allowed_origins=reader.origins(access_table, "allowed_origins", "access"),
        )

    printers = {}
    for printer_id, table in (reader.table(data, "printers", "printers", required=False) or {}).items():
        where = f"printers.{printer_id}"
        reader.slug(printer_id, where)
        if not isinstance(table, dict):
            reader.problems.append(f"{where}: must be a table")
            continue
        reader.unknown(table, {"name", "place", "token", "public"}, f"{where}.")
        printers[printer_id] = Printer(
            id=printer_id,
            name=reader.text(table, "name", where),
            place=reader.text(table, "place", where),
            token=reader.token(table, "token", where),
            public=reader.flag(table, "public", where),
        )

    clients = {}
    for client_id, table in (reader.table(data, "clients", "clients", required=False) or {}).items():
        where = f"clients.{client_id}"
        reader.slug(client_id, where)
        if not isinstance(table, dict):
            reader.problems.append(f"{where}: must be a table")
            continue
        reader.unknown(table, {"token"}, f"{where}.")
        clients[client_id] = Client(id=client_id, token=reader.token(table, "token", where))

    if reader.problems:
        lines = "\n".join(f"  - {problem}" for problem in reader.problems)
        raise ConfigError(f"Invalid config {path}:\n{lines}")
    return ServerConfig(
        host=host,
        port=port,
        database=path.parent / database,
        admin_token=admin_token,
        access=access,
        printers=printers,
        clients=clients,
    )
