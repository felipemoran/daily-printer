"""
Send the simulation's sample jobs to a running print server and check that each one printed byte for byte.

`make compose-test` runs it in a container that mounts the server's data volume and the fake printers' volume.

Example:
  .venv/bin/python src/scripts/compose_check.py --server http://server:8787 --config /config/server.toml \\
      --printers /printers
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src" / "scripts"))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from job_artifacts import ESCPOS, artifacts_root  # noqa: E402
from printctl import Client, Failure  # noqa: E402
from server_config import ConfigError, load_config  # noqa: E402
from simulate import POLL_SECONDS, PRINT_TIMEOUT, READY_TIMEOUT, sample_jobs, sample_request  # noqa: E402

ENDED = ("failed", "expired", "cancelled")


class CheckError(Exception):
    pass


def _until(what: str, timeout: float, condition) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise CheckError(f"timed out after {timeout} s waiting for {what}")
        time.sleep(POLL_SECONDS)


def _printed(admin: Client, ids: list[str], jobs: dict[str, dict]) -> bool:
    for job_id in ids:
        job = jobs[job_id] = admin.request("GET", f"/api/jobs/{job_id}")
        if job["status"] in ENDED:
            events = ", ".join(f"{e['event']} {e['detail'] or ''}".strip() for e in job["events"])
            raise CheckError(f"job {job_id} for {job['printer']} ended {job['status']}: {events}")
    return all(job["status"] == "printed" for job in jobs.values())


def run(server: str, config_path: Path, printers_dir: Path) -> int:
    config = load_config(config_path)
    if len(config.clients) != 1:
        raise CheckError(f"{config_path} must hold exactly one [clients.*] table, the sender")
    sender_token = next(iter(config.clients.values())).token
    admin = Client(server, config.admin_token, timeout=PRINT_TIMEOUT)
    sender = Client(server, sender_token, timeout=PRINT_TIMEOUT)
    printer_ids = list(config.printers)

    print(f"Waiting for the printers to come online: {', '.join(printer_ids)} ...", flush=True)
    _until("the printers to come online", READY_TIMEOUT,
           lambda: all(p["online"] for p in admin.request("GET", "/api/printers")["printers"]))

    samples = sample_jobs()
    print(f"Sending {len(samples)} sample jobs ...", flush=True)
    sent = []
    for number, (kind, name, path) in enumerate(samples):
        printer = printer_ids[number % len(printer_ids)]
        sent.append(sender.request("POST", "/api/jobs", sample_request(printer, kind, name, path))["id"])

    jobs: dict[str, dict] = {}
    _until("every job to print", PRINT_TIMEOUT, lambda: _printed(admin, sent, jobs))

    artifacts = artifacts_root(config.database)
    width = max(len(name) for _, name, _ in samples)
    mismatches = 0
    print(f"\n{'printer':<8} {'kind':<9} {'title':<{width}}  status   bytes    same as {ESCPOS}")
    for job_id in sent:
        job = jobs[job_id]
        output = printers_dir / job["printer"] / f"{job_id}.bin"
        expected = (artifacts / job_id / ESCPOS).read_bytes()
        actual = output.read_bytes() if output.is_file() else None
        same = actual == expected
        mismatches += not same
        verdict = "yes" if same else ("NO: missing " + str(output) if actual is None else "NO: bytes differ")
        print(f"{job['printer']:<8} {job['kind']:<9} {job['title']:<{width}}  {job['status']:<8} "
              f"{len(expected):>7}  {verdict}")
    if mismatches:
        raise CheckError(f"{mismatches} of {len(sent)} jobs did not print the bytes the server rendered")
    print(f"\nAll {len(sent)} jobs printed, and each fake printer's output equals the job's {ESCPOS}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print every sample on a running server and check the output.")
    parser.add_argument("--server", required=True, metavar="URL", help="the server's base URL")
    parser.add_argument("--config", required=True, type=Path, metavar="PATH", help="the server's config file")
    parser.add_argument("--printers", required=True, type=Path, metavar="DIR",
                        help="the fake printers' output: DIR/<printer id>/<job id>.bin")
    args = parser.parse_args(argv)
    try:
        return run(args.server, args.config, args.printers)
    except (CheckError, ConfigError) as error:
        print(f"compose_check: {error}", file=sys.stderr)
    except Failure as failure:
        print(f"compose_check: request failed: {failure.message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
