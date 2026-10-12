"""
Run the whole print system on this machine: the server and two devices with fake printers.

Examples:
  uv run src/scripts/simulate.py           # print two jobs, then keep running until Ctrl-C
  uv run src/scripts/simulate.py --once    # print two jobs, then stop

Ctrl-C or SIGTERM stops the server and both devices. Exit status: 0 after the jobs printed,
1 when something failed, 130 when stopped before the jobs printed.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src" / "scripts"))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from PIL import Image  # noqa: E402

from printctl import Client, Failure  # noqa: E402
from render_job import DIST_DIR  # noqa: E402

SCRIPTS = _PROJECT_ROOT / "src" / "scripts"
SAMPLE_RECEIPT = _PROJECT_ROOT / "samples" / "receipt-sample.json"
DEFAULT_PORT = 8787
# (id, name, place, public)
PRINTERS = (("home", "Home", "Home office", True), ("work", "Work", "Desk at work", False))
CLIENT = "sim-client"
IMAGE_SIZE = (640, 480)
READY_TIMEOUT = 60
PRINT_TIMEOUT = 180
POLL_TIMEOUT = 10
STOP_TIMEOUT = 10
POLL_SECONDS = 0.2
_STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


class SimulationError(Exception):
    pass


@contextmanager
def _signals_blocked():
    """Hold back Ctrl-C and SIGTERM, so a child is never started without being recorded."""
    signal.pthread_sigmask(signal.SIG_BLOCK, _STOP_SIGNALS)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_UNBLOCK, _STOP_SIGNALS)


class Children:
    """The server and device processes. ``stop`` ends every one of them."""

    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir
        self.processes: dict[str, subprocess.Popen] = {}

    def log(self, name: str) -> Path:
        return self.workdir / f"{name}.log"

    def start(self, name: str, script: str, *args: str) -> None:
        with open(self.log(name), "wb") as log, _signals_blocked():
            # Each child gets its own session: Ctrl-C reaches only this script, which stops them in order.
            self.processes[name] = subprocess.Popen(
                [sys.executable, str(SCRIPTS / script), *args],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )

    def check(self) -> None:
        for name, process in self.processes.items():
            if process.poll() is not None:
                lines = self.log(name).read_text(errors="replace").splitlines()[-15:]
                tail = "\n".join(f"  | {line}" for line in lines) or "  | (no output)"
                raise SimulationError(
                    f"the {name} process stopped with exit code {process.returncode}. "
                    f"Last lines of {self.log(name)}:\n{tail}"
                )

    def stop(self) -> None:
        for signum in _STOP_SIGNALS:
            signal.signal(signum, signal.SIG_IGN)
        running = [process for process in self.processes.values() if process.poll() is None]
        # Each leader is still unreaped here, so its group id cannot belong to another process.
        for process in running:
            _signal_group(process, signal.SIGTERM)
        deadline = time.monotonic() + STOP_TIMEOUT
        for process in running:
            try:
                process.wait(max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                _signal_group(process, signal.SIGKILL)
                process.wait()


def _signal_group(process: subprocess.Popen, signum: int) -> None:
    """The group also holds the server's Chromium renderers."""
    try:
        os.killpg(process.pid, signum)
    except (ProcessLookupError, PermissionError):
        # macOS answers EPERM for a group that holds only an unreaped zombie.
        pass


def _interrupt(signum, frame) -> None:
    raise KeyboardInterrupt


def _write_private(path: Path, text: str) -> None:
    path.touch(mode=0o600)
    path.chmod(0o600)
    path.write_text(text)


def _write_config(workdir: Path, port: int) -> tuple[Path, str, str]:
    admin_token, client_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    _write_private(workdir / "admin-token", admin_token + "\n")
    printers = []
    for printer_id, name, place, public in PRINTERS:
        token = secrets.token_urlsafe(32)
        _write_private(workdir / f"{printer_id}.token", token + "\n")
        printers.append(
            f'[printers.{printer_id}]\nname = "{name}"\nplace = "{place}"\n'
            f'token = "{token}"\npublic = {"true" if public else "false"}\n'
        )
    config = workdir / "server.toml"
    _write_private(config, (
        f'[server]\nhost = "127.0.0.1"\nport = {port}\ndatabase = "data/queue.db"\nadmin_token = "{admin_token}"\n\n'
        + "\n".join(printers)
        + f'\n[clients.{CLIENT}]\ntoken = "{client_token}"\n'
    ))
    return config, admin_token, client_token


def _call(client: Client, method: str, path: str, body: dict | None = None) -> dict:
    try:
        return client.request(method, path, body)
    except Failure as failure:
        raise SimulationError(f"{method} {path} failed: {failure.message}") from None


def _until(children: Children, what: str, timeout: float, condition) -> None:
    deadline = time.monotonic() + timeout
    while True:
        children.check()
        try:
            if condition():
                return
        except SimulationError:
            # A child that died explains the failed request better than the request error does.
            children.check()
            raise
        if time.monotonic() > deadline:
            raise SimulationError(f"timed out after {timeout} s waiting for {what}; logs are in {children.workdir}")
        time.sleep(POLL_SECONDS)


def _test_image() -> bytes:
    picture = Image.merge("RGB", (
        Image.linear_gradient("L").resize(IMAGE_SIZE),
        Image.linear_gradient("L").rotate(90).resize(IMAGE_SIZE),
        Image.radial_gradient("L").resize(IMAGE_SIZE),
    ))
    data = io.BytesIO()
    picture.save(data, format="PNG")
    return data.getvalue()


def _check_port_free(port: int) -> None:
    """Fail before any token exists, so no request ever reaches another program on the port."""
    with socket.socket() as probe:
        # The server's own listener sets SO_REUSEADDR; without it a closed connection in TIME_WAIT reads as "in use".
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise SimulationError(f"port {port} on 127.0.0.1 is in use; pass --port with a free port") from None


def _all_online(admin: Client) -> bool:
    return all(printer["online"] for printer in _call(admin, "GET", "/api/printers")["printers"])


def _run(workdir: Path, port: int, children: Children) -> tuple[str, list[dict]]:
    base = f"http://127.0.0.1:{port}"
    _check_port_free(port)
    config, admin_token, client_token = _write_config(workdir, port)
    admin = Client(base, admin_token, timeout=POLL_TIMEOUT)
    # A receipt render starts a Chromium, so the POST can take a while.
    sender = Client(base, client_token, timeout=PRINT_TIMEOUT)
    print(f"Starting the print server on {base} ...", flush=True)
    children.start("server", "print_server.py", "--config", str(config))
    # Only our server writes this line, so no request goes out before it owns the port.
    _until(children, "the server to listen", READY_TIMEOUT,
           lambda: f"listening on {base}" in children.log("server").read_text(errors="replace"))

    print(f"Starting the fake printers: {', '.join(p[0] for p in PRINTERS)} ...", flush=True)
    for printer_id, *_ in PRINTERS:
        children.start(
            f"device-{printer_id}", "print_device.py", "--server", f"ws://127.0.0.1:{port}/device",
            "--token-file", str(workdir / f"{printer_id}.token"), "--fake", str(workdir / printer_id),
        )
    _until(children, "both devices to come online", READY_TIMEOUT, lambda: _all_online(admin))

    print("Sending a receipt to home and an image to work ...", flush=True)
    requests = [
        {"printer": "home", "kind": "receipt", "title": "Sample receipt",
         "payload": json.loads(SAMPLE_RECEIPT.read_text(encoding="utf-8"))},
        {"printer": "work", "kind": "image", "title": "Test pattern",
         "image": base64.b64encode(_test_image()).decode()},
    ]
    ids = [_call(sender, "POST", "/api/jobs", body)["id"] for body in requests]

    jobs: dict[str, dict] = {}

    def all_printed() -> bool:
        for job_id in ids:
            job = jobs[job_id] = _call(admin, "GET", f"/api/jobs/{job_id}")
            if job["status"] in ("failed", "expired", "cancelled"):
                events = ", ".join(f"{e['event']} {e['detail'] or ''}".strip() for e in job["events"])
                raise SimulationError(f"job {job_id} for {job['printer']} ended {job['status']}: {events}")
        return all(job["status"] == "printed" for job in jobs.values())

    _until(children, "both jobs to print", PRINT_TIMEOUT, all_printed)
    return base, [jobs[job_id] for job_id in ids]


def _summary(workdir: Path, jobs: list[dict]) -> None:
    print(f"\nPrinted {len(jobs)} jobs. Fake printer output is in {workdir}:")
    for job in jobs:
        png = workdir / job["printer"] / f"{job['id']}.png"
        if not png.is_file():
            raise SimulationError(f"job {job['id']} is printed, but the fake printer wrote no {png}")
        size = f"{job['width']} x {job['height']} dots"
        print(f"  {job['printer']:<5} {job['kind']:<8} {job['status']:<8} {size:<16} "
              f"{job['paper_mm'] / 10:5.1f} cm  {png}")


def _instructions(workdir: Path, base: str) -> None:
    printctl = f"uv run src/scripts/printctl.py --server {base} --token-file {workdir / 'admin-token'}"
    print(f"""
The print system is running. Press Ctrl-C to stop it.
  Server:        {base}
  Admin token:   {workdir / 'admin-token'}
  Logs, config:  {workdir}

Try these in another terminal, from the repo root:
  {printctl} printers
  {printctl} jobs
  {printctl} stats
  {printctl} send image <photo.jpg> --printer work
""", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the print server and two devices with fake printers, print one job on each, "
        "and keep them running until Ctrl-C.",
    )
    parser.add_argument("--once", action="store_true", help="stop after both jobs print")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"server port (default {DEFAULT_PORT})")
    args = parser.parse_args(argv)

    if not (DIST_DIR / "index.html").is_file():
        print(
            f"simulate: {DIST_DIR / 'index.html'} is missing. The receipt job needs the built receipt app.\n"
            "Build it with `make web-build` (on a fresh clone, run `make setup-web` first).",
            file=sys.stderr,
        )
        return 1

    workdir = Path(tempfile.mkdtemp(prefix="print-sim-"))
    children = Children(workdir)
    printed = False
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, _interrupt)
    try:
        base, jobs = _run(workdir, args.port, children)
        _summary(workdir, jobs)
        printed = True
        if args.once:
            return 0
        _instructions(workdir, base)
        while True:
            children.check()
            time.sleep(0.5)
    except SimulationError as error:
        print(f"simulate: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopping ...", flush=True)
        return 0 if printed else 130
    finally:
        children.stop()


if __name__ == "__main__":
    sys.exit(main())
