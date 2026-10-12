"""Each job's input and outputs, frozen at intake in one folder per job: docs/feature-print-system.md."""

from __future__ import annotations

import functools
import hashlib
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from render_job import DIST_DIR, Rendered

STAGING_PREFIX = ".tmp-"
PRINT_PNG = "print.png"
ESCPOS = "job.escpos"
META = "meta.json"


def artifacts_root(database: Path) -> Path:
    return database.parent / "artifacts"


@functools.cache
def dist_sha256() -> str | None:
    """A digest of every file in web/dist, read once per process. None when web/dist is missing."""
    if not DIST_DIR.is_dir():
        return None
    digest = hashlib.sha256()
    for file in sorted(path for path in DIST_DIR.rglob("*") if path.is_file()):
        content = file.read_bytes()
        digest.update(f"{file.relative_to(DIST_DIR).as_posix()}\0{len(content)}\0".encode())
        digest.update(content)
    return digest.hexdigest()


def _source_name(image: bytes) -> str:
    try:
        with Image.open(io.BytesIO(image)) as picture:
            extension = {"JPEG": "jpg"}.get(picture.format, (picture.format or "bin").lower())
    except (UnidentifiedImageError, OSError):
        extension = "bin"
    return f"source.{extension}"


def _json(value) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def job_files(kind: str, rendered: Rendered, *, payload: dict | None, image: bytes | None,
              created_at: float) -> dict[str, bytes]:
    """The files of a new job's folder, by name."""
    files = {}
    if payload is not None:
        files["payload.json"] = _json(payload)
    if image is not None:
        files[_source_name(image)] = image
    if rendered.mhtml is not None:
        files["page.mhtml"] = rendered.mhtml
    if rendered.screenshot is not None:
        files["screenshot.png"] = rendered.screenshot
    files[PRINT_PNG] = rendered.png
    files[ESCPOS] = rendered.escpos
    files[META] = _json({
        "kind": kind,
        "template": payload.get("template") if kind in ("template", "text") else None,
        "created_at": created_at,
        "width": rendered.width,
        "height": rendered.height,
        "render_ms": rendered.render_ms,
        "web_dist_sha256": dist_sha256(),
    })
    return files


class ArtifactStore:
    """``<root>/<job id>/`` per job. A folder is staged as ``.tmp-*`` and gets its job id inside the job's insert."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def folder(self, job_id: str) -> Path:
        return self.root / job_id

    def read(self, job_id: str, name: str) -> bytes | None:
        try:
            return (self.folder(job_id) / name).read_bytes()
        except FileNotFoundError:
            return None

    def stage(self, files: dict[str, bytes]) -> Path:
        staged = self._new_staging()
        try:
            for name, content in files.items():
                (staged / name).write_bytes(content)
        except BaseException:
            self.discard(staged)
            raise
        return staged

    def stage_reprint(self, job_id: str, *, created_at: float) -> Path:
        """A copy of the job's folder, its files hard-linked, with ``reprint_of`` in a new meta.json."""
        source = self.folder(job_id)
        meta = json.loads((source / META).read_text(encoding="utf-8"))
        staged = self._new_staging()
        try:
            for file in source.iterdir():
                if file.name != META:
                    os.link(file, staged / file.name)
            (staged / META).write_bytes(_json({**meta, "created_at": created_at, "reprint_of": job_id}))
        except BaseException:
            self.discard(staged)
            raise
        return staged

    def discard(self, staged: Path) -> None:
        shutil.rmtree(staged, ignore_errors=True)

    def sweep(self) -> int:
        """Delete the staging folders a stopped server left. Returns how many."""
        stale = list(self.root.glob(STAGING_PREFIX + "*")) if self.root.is_dir() else []
        for folder in stale:
            self.discard(folder)
        return len(stale)

    def _new_staging(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=self.root))
