import math
import random
import shutil
import sqlite3
import statistics
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from escpos.printer import Dummy
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import job_queue  # noqa: E402
from job_queue import (  # noqa: E402
    DAY_SECONDS, FRAME_SIZE, ID_TRIES, MAX_ATTEMPTS, Event, JobNotFinal, JobQueue,
    SourceActivity, Status,
)
from printer import PRINT_WIDTH_DOTS  # noqa: E402

FINAL = (Status.PRINTED, Status.FAILED, Status.EXPIRED, Status.CANCELLED)
SAO_PAULO = timezone(timedelta(hours=-3))


def _receipt_raster(height: int = 640) -> Image.Image:
    image = Image.new("1", (PRINT_WIDTH_DOTS, height), 1)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, PRINT_WIDTH_DOTS - 1, 48), fill=0)
    for y in range(70, height - 20, 26):
        draw.text((8, y), f"[ ] task line {y}", fill=0)
        draw.line((8, y + 20, PRINT_WIDTH_DOTS - 8, y + 20), fill=0)
    return image


def _escpos(image: Image.Image) -> bytes:
    printer = Dummy()
    printer.profile.profile_data["media"]["width"]["pixels"] = PRINT_WIDTH_DOTS
    printer.hw("INIT")
    printer.image(image, center=False)
    printer.ln(3)
    return printer.output


RASTER = _receipt_raster()
DATA = _escpos(RASTER)


class QueueTestCase(unittest.TestCase):
    def setUp(self):
        self.queue = JobQueue(":memory:")
        self.addCleanup(self.queue.close)

    def add(self, printer="home", data=DATA, *, now=0, expires_in=3600, height=RASTER.height):
        return self.queue.add(printer, data, kind="receipt", title="Morning brief", source="morning-brief",
                              ingress="api", width=PRINT_WIDTH_DOTS, height=height, render_ms=850,
                              expires_in=expires_in, now=now)

    def status(self, job_id: str) -> Status:
        return self.queue.job(job_id, now=0).status

    def events(self, job_id: str) -> list[Event]:
        return [event.event for event in self.queue.job(job_id, now=0).events]


class LifecycleTest(QueueTestCase):
    def test_delivers_oldest_first_per_printer_with_data(self):
        first = self.add("home", b"one", now=0)
        self.add("work", b"other", now=1)
        self.add("home", b"two", now=2)
        job = self.queue.take("home", now=3)
        self.assertEqual((job.id, job.data, job.attempts, job.status), (first.id, b"one", 1, Status.SENDING))
        self.assertEqual(self.queue.take("home", now=3).data, b"two")
        self.assertIsNone(self.queue.take("home", now=3))

    def test_confirm_marks_printed_sets_printed_at_and_drops_data(self):
        job = self.add(now=0)
        self.queue.take("home", now=5)
        self.queue.confirm(job.id, now=9)
        stored = self.queue.job(job.id, now=9)
        self.assertEqual((stored.status, stored.printed_at), (Status.PRINTED, 9))
        self.assertIsNone(self.queue.take("home", now=9))

    def test_release_retries_until_the_last_attempt_then_fails(self):
        job = self.add(now=0)
        for _ in range(MAX_ATTEMPTS - 1):
            self.queue.release(self.queue.take("home", now=0).id, now=0)
            self.assertEqual(self.status(job.id), Status.QUEUED)
        self.queue.release(self.queue.take("home", now=0).id, detail="paper out", now=0)
        self.assertEqual(self.status(job.id), Status.FAILED)
        self.assertEqual(self.queue.job(job.id).events[-1].detail, "paper out")
        self.assertIsNone(self.queue.take("home", now=0))

    def test_expired_jobs_are_not_delivered(self):
        job = self.add(expires_in=60, now=0)
        self.assertIsNone(self.queue.take("home", now=60))
        self.assertEqual(self.status(job.id), Status.EXPIRED)

    def test_release_after_expiry_expires_instead_of_requeueing(self):
        job = self.add(expires_in=60, now=0)
        self.queue.take("home", now=10)
        self.queue.release(job.id, now=61)
        self.assertEqual(self.status(job.id), Status.EXPIRED)

    def test_cancel_and_clear(self):
        one = self.add("home", b"1", now=0)
        two = self.add("home", b"2", now=1)
        work = self.add("work", b"3", now=2)
        self.assertTrue(self.queue.cancel(one.id, now=3))
        self.assertFalse(self.queue.cancel(one.id, now=3))
        self.assertEqual(self.queue.clear("home", now=3), 1)
        self.assertEqual(self.status(two.id), Status.CANCELLED)
        self.assertEqual(self.status(work.id), Status.QUEUED)
        self.assertEqual(self.events(two.id)[-1], Event.CANCELLED)

    def test_a_job_cancelled_while_sending_and_then_confirmed_is_printed(self):
        for name, cancel in {"cancel": lambda job: self.queue.cancel(job.id, now=1),
                             "clear": lambda job: self.queue.clear("home", now=1)}.items():
            with self.subTest(name):
                job = self.add(now=0)
                self.queue.take("home", now=0)
                cancel(job)
                self.queue.confirm(job.id, now=2)
                stored = self.queue.job(job.id, now=2)
                self.assertEqual((stored.status, stored.printed_at), (Status.PRINTED, 2))
                last = stored.events[-1]
                self.assertEqual((last.event, last.detail), (Event.PRINTED, "after the cancel"))

    def test_mark_sent_ignores_a_job_that_is_not_sending(self):
        job = self.add(now=0)
        self.assertFalse(self.queue.mark_sent(job.id, now=1))
        self.assertIsNone(self.queue.job(job.id, now=1).sent_at)
        self.assertNotIn(Event.SENT, self.events(job.id))

    def test_survives_a_restart_and_requeues_jobs_left_sending(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jobs.db"
            queue = JobQueue(path)
            job = queue.add("home", DATA, kind="image", title="Photo", source="admin", ingress="cli",
                            width=PRINT_WIDTH_DOTS, height=RASTER.height, render_ms=1200, now=0)
            queue.take("home", now=0)
            queue.close()

            queue = JobQueue(path)
            queue.release_all(now=1)
            delivered = queue.take("home", now=1)
            self.assertEqual((delivered.id, delivered.data), (job.id, DATA))
            queue.close()


class JobRecordTest(QueueTestCase):
    def test_add_derives_size_frames_and_paper_from_the_data(self):
        job = self.add(now=0)
        chunks = [DATA[i:i + FRAME_SIZE] for i in range(0, len(DATA), FRAME_SIZE)]
        self.assertEqual(job.size_bytes, len(DATA))
        self.assertEqual(job.frames, len(chunks))
        self.assertEqual(job.paper_mm, RASTER.height / 8)
        self.assertEqual((job.width, job.height, job.render_ms), (PRINT_WIDTH_DOTS, RASTER.height, 850))
        self.assertEqual((job.kind, job.title, job.source, job.ingress), ("receipt", "Morning brief", "morning-brief", "api"))

    def test_frame_count_rounds_up_at_the_frame_boundary(self):
        for size, frames in [(FRAME_SIZE - 1, 1), (FRAME_SIZE, 1), (FRAME_SIZE + 1, 2), (3 * FRAME_SIZE, 3)]:
            self.assertEqual(self.add(data=b"\0" * size).frames, frames, size)
            self.assertEqual(math.ceil(size / FRAME_SIZE), frames)

    def test_jobs_lists_newest_first_with_filters_and_no_blobs(self):
        ids = [self.add("home" if i % 2 else "work", now=i).id for i in range(6)]
        self.queue.take("home", now=10)
        listed = self.queue.jobs(now=10)
        self.assertEqual([job.id for job in listed], ids[::-1])
        self.assertTrue(all(job.data is None and job.events == () for job in listed))
        self.assertEqual([job.id for job in self.queue.jobs("home", now=10)], [ids[5], ids[3], ids[1]])
        self.assertEqual([job.id for job in self.queue.jobs("home", Status.QUEUED, now=10)], [ids[5], ids[3]])
        self.assertEqual(len(self.queue.jobs(limit=2, now=10)), 2)

    def test_job_returns_events_without_data_and_none_when_unknown(self):
        job = self.add(now=0)
        stored = self.queue.job(job.id, now=0)
        self.assertIsNone(stored.data)
        self.assertEqual([e.event for e in stored.events], [Event.RECEIVED, Event.RENDERED])
        self.assertIsNone(self.queue.job("nope", now=0))

    def test_a_database_from_before_the_artifact_folders_still_opens_and_takes_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jobs.db"
            old = sqlite3.connect(path)
            old.executescript(job_queue._SCHEMA.replace("    data BLOB\n", "    data BLOB,\n    png BLOB\n"))
            old.close()
            queue = JobQueue(path)
            self.addCleanup(queue.close)
            job = queue.add("home", DATA, kind="receipt", title="t", source="admin", ingress="cli",
                            width=PRINT_WIDTH_DOTS, height=RASTER.height, render_ms=1, now=0)
            self.assertEqual(queue.take("home", now=1).data, DATA)
            queue.confirm(job.id, now=2)
            self.assertEqual(queue.reprint(job.id, "home", DATA, source="admin", ingress="cli", now=3).kind, "receipt")


class JobIdTest(QueueTestCase):
    def setUp(self):
        super().setUp()
        self.original = self.add(now=0)
        self.queue.cancel(self.original.id, now=0)
        self.before = self.queue.job(self.original.id, now=0)

    def colliding(self, *ids: str):
        return mock.patch.object(job_queue, "_new_id", side_effect=[self.original.id, *ids])

    def assertOriginalUntouched(self) -> None:
        self.assertEqual(self.queue.job(self.original.id, now=0), self.before)

    def test_add_retries_a_colliding_id_and_leaves_the_existing_job_alone(self):
        with self.colliding("0000beef"):
            job = self.add("work", now=1)
        self.assertEqual(job.id, "0000beef")
        self.assertEqual(self.queue.take("work", now=1).data, DATA)
        self.assertOriginalUntouched()

    def test_reprint_retries_a_colliding_id(self):
        with self.colliding("0000cafe"):
            copy = self.queue.reprint(self.original.id, "work", DATA, source="admin", ingress="cli", now=1)
        self.assertEqual(copy.id, "0000cafe")
        events = self.queue.job(self.original.id, now=1).events
        self.assertEqual(events[:-1], self.before.events)
        self.assertEqual((events[-1].event, events[-1].detail), (Event.REPRINTED, "0000cafe"))

    def test_gives_up_after_the_last_try_without_writing_anything(self):
        events = self.queue._db.execute("SELECT COUNT(*) FROM job_events").fetchone()[0]
        with mock.patch.object(job_queue, "_new_id", return_value=self.original.id) as new_id:
            with self.assertRaisesRegex(RuntimeError, f"no free job id after {ID_TRIES} tries"):
                self.add(now=1)
            with self.assertRaisesRegex(RuntimeError, "no free job id"):
                self.queue.reprint(self.original.id, "work", DATA, source="admin", ingress="cli", now=1)
        self.assertEqual(new_id.call_count, 2 * ID_TRIES)
        self.assertEqual(len(self.queue.jobs(now=1)), 1)
        self.assertEqual(self.queue._db.execute("SELECT COUNT(*) FROM job_events").fetchone()[0], events)
        self.assertOriginalUntouched()

    def test_another_constraint_error_is_not_retried(self):
        with mock.patch.object(job_queue, "_new_id", return_value="0000f00d") as new_id:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "NOT NULL"):
                self.queue.add("home", DATA, kind=None, title="t", source="admin", ingress="cli",
                               width=PRINT_WIDTH_DOTS, height=RASTER.height, render_ms=1, now=1)
        self.assertEqual(new_id.call_count, 1)
        self.assertEqual(len(self.queue.jobs(now=1)), 1)


class TransactionTest(QueueTestCase):
    def test_an_automatic_rollback_surfaces_the_original_error(self):
        self.queue._db.execute(
            "CREATE TEMP TRIGGER abort_events BEFORE INSERT ON job_events BEGIN SELECT RAISE(ROLLBACK, 'disk gone'); END"
        )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "disk gone"):
            self.add(now=0)
        self.assertFalse(self.queue._db.in_transaction)
        self.assertEqual(self.queue._db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)


class EventsTest(QueueTestCase):
    def test_events_read_back_in_the_order_of_the_transitions(self):
        job = self.add(now=0)
        performed = [Event.RECEIVED, Event.RENDERED]
        self.queue.take("home", now=1)
        self.queue.release(job.id, detail="no reply within 120 s", now=2)
        performed += [Event.SENDING, Event.RELEASED]
        self.queue.take("home", now=3)
        self.assertTrue(self.queue.mark_sent(job.id, now=4))
        self.queue.confirm(job.id, now=5)
        performed += [Event.SENDING, Event.SENT, Event.PRINTED]

        stored = self.queue.job(job.id, now=5)
        self.assertEqual([e.event for e in stored.events], performed)
        self.assertEqual([e.at for e in stored.events], [0, 0, 1, 2, 3, 4, 5])
        self.assertEqual(stored.events[3].detail, "no reply within 120 s")
        self.assertEqual(stored.events[4].detail, "attempt 2")
        self.assertEqual((stored.sent_at, stored.printed_at), (4, 5))

    def test_failed_after_three_attempts_records_each_attempt(self):
        job = self.add(now=0)
        for _ in range(MAX_ATTEMPTS):
            self.queue.release(self.queue.take("home", now=1).id, now=1)
        self.assertEqual(self.events(job.id), [Event.RECEIVED, Event.RENDERED]
                         + [Event.SENDING, Event.RELEASED] * (MAX_ATTEMPTS - 1) + [Event.SENDING, Event.FAILED])

    def test_lazy_expiry_records_expired_at_the_expiry_time(self):
        for read in (lambda: self.queue.jobs(now=500), lambda: self.queue.stats(now=500, tz=SAO_PAULO),
                     lambda: self.queue.take("home", now=500)):
            job = self.add(expires_in=60, now=0)
            read()
            events = self.queue.job(job.id, now=0).events
            self.assertEqual([e.event for e in events][-1], Event.EXPIRED)
            self.assertEqual(events[-1].at, 60)
            self.assertEqual(sum(e.event == Event.EXPIRED for e in events), 1)

    def test_cancel_of_a_sending_job_records_cancelled_once(self):
        job = self.add(now=0)
        self.queue.take("home", now=1)
        self.queue.cancel(job.id, now=2)
        self.queue.cancel(job.id, now=3)
        self.assertEqual(self.events(job.id), [Event.RECEIVED, Event.RENDERED, Event.SENDING, Event.CANCELLED])


class ReprintTest(QueueTestCase):
    def reprint(self, job_id, printer="work", data=DATA, *, now):
        return self.queue.reprint(job_id, printer, data, source="admin", ingress="cli", now=now)

    def test_reprint_queues_a_copy_that_sends_the_given_data(self):
        original = self.add("home", now=0)
        self.queue.take("home", now=1)
        self.queue.confirm(original.id, now=2)
        new_data = _escpos(RASTER)

        copy = self.reprint(original.id, "work", new_data, now=100)
        self.assertNotEqual(copy.id, original.id)
        self.assertEqual((copy.printer, copy.status, copy.created_at, copy.expires_at), ("work", Status.QUEUED, 100, 3700))
        self.assertEqual((copy.source, copy.ingress), ("admin", "cli"))
        for name in ("kind", "title", "width", "height", "render_ms", "paper_mm"):
            self.assertEqual(getattr(copy, name), getattr(original, name), name)
        self.assertEqual(self.queue.take("work", now=101).data, new_data)

        last = self.queue.job(original.id, now=100).events[-1]
        self.assertEqual((last.event, last.detail, last.at), (Event.REPRINTED, copy.id, 100))
        events = self.queue.job(copy.id, now=100).events
        self.assertEqual([e.event for e in events[:2]], [Event.RECEIVED, Event.RENDERED])
        self.assertEqual(events[0].detail, f"admin via cli, reprint of {original.id}")

    def test_reprint_of_a_text_job_is_a_text_job(self):
        text = b"\x1b@ BUILD FAILED\n\n\n\n"
        original = self.queue.add("home", text, kind="text", title="NIGHTLY", source="ci", ingress="api",
                                  width=PRINT_WIDTH_DOTS, height=RASTER.height, render_ms=900, expires_in=3600, now=0)
        self.queue.take("home", now=1)
        self.queue.confirm(original.id, now=2)

        copy = self.reprint(original.id, "home", text, now=100)
        self.assertEqual(copy.kind, "text")
        self.assertEqual(self.queue.take("home", now=101).data, text)

    def test_reprint_refuses_a_job_that_is_still_queued_or_sending(self):
        queued = self.add("home", now=0)
        sending = self.add("work", now=0)
        self.queue.take("work", now=1)
        for job in (queued, sending):
            before = self.queue.job(job.id, now=0)
            with self.assertRaises(JobNotFinal):
                self.reprint(job.id, now=2)
            self.assertEqual(self.queue.job(job.id, now=0), before)
        self.assertTrue(issubclass(JobNotFinal, ValueError))
        self.assertEqual(len(self.queue.jobs(now=0)), 2)

    def test_reprint_accepts_a_queued_job_whose_expiry_passed(self):
        job = self.add("home", expires_in=60, now=0)
        copy = self.reprint(job.id, now=61)
        self.assertEqual(self.status(job.id), Status.EXPIRED)
        self.assertEqual(copy.status, Status.QUEUED)

    def test_reprint_of_an_unknown_job_is_none(self):
        self.assertIsNone(self.reprint("nope", now=0))
        self.assertEqual(self.queue.jobs(now=0), [])


class ArtifactFolderTest(QueueTestCase):
    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp(prefix="job-queue-test-"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def staged(self) -> Path:
        folder = self.root / ".tmp-staged"
        folder.mkdir()
        (folder / "job.escpos").write_bytes(DATA)
        return folder

    def test_add_and_reprint_rename_the_staged_folder_to_the_job_id(self):
        job = self.queue.add("home", DATA, kind="receipt", title="t", source="admin", ingress="cli",
                             width=PRINT_WIDTH_DOTS, height=RASTER.height, render_ms=1, artifacts=self.staged(), now=0)
        self.queue.cancel(job.id, now=1)
        copy = self.queue.reprint(job.id, "home", DATA, source="admin", ingress="cli", artifacts=self.staged(), now=2)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), sorted([job.id, copy.id]))
        self.assertEqual((self.root / copy.id / "job.escpos").read_bytes(), DATA)

    def test_a_failed_commit_removes_the_renamed_folder_and_stores_no_job(self):
        queue = JobQueue(self.root / "jobs.db")
        self.addCleanup(queue.close)
        finished = queue.add("home", DATA, kind="receipt", title="t", source="admin", ingress="cli",
                             width=PRINT_WIDTH_DOTS, height=RASTER.height, render_ms=1, now=0)
        queue.cancel(finished.id, now=0)
        artifacts = self.root / "artifacts"
        artifacts.mkdir()
        # A reader's lock lets the insert run but makes COMMIT fail with SQLITE_BUSY.
        reader = sqlite3.connect(self.root / "jobs.db", isolation_level=None)
        self.addCleanup(reader.close)
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM jobs").fetchone()
        queue._db.execute("PRAGMA busy_timeout = 0")
        attempts = {
            "add": lambda staged: queue.add(
                "home", DATA, kind="receipt", title="t", source="admin", ingress="cli", width=PRINT_WIDTH_DOTS,
                height=RASTER.height, render_ms=1, artifacts=staged, now=1),
            "reprint": lambda staged: queue.reprint(
                finished.id, "home", DATA, source="admin", ingress="cli", artifacts=staged, now=1),
        }
        for name, attempt in attempts.items():
            with self.subTest(name):
                staged = artifacts / ".tmp-staged"
                staged.mkdir()
                with self.assertRaisesRegex(sqlite3.OperationalError, "database is locked"):
                    attempt(staged)
                self.assertFalse(queue._db.in_transaction)
                self.assertEqual(list(artifacts.iterdir()), [])
        reader.execute("ROLLBACK")
        self.assertEqual([job.id for job in queue.jobs(now=1)], [finished.id])

    def test_a_failed_rename_rolls_the_insert_back(self):
        staged = self.staged()
        (self.root / "0000beef").mkdir()
        (self.root / "0000beef" / "orphan").write_bytes(b"")
        with mock.patch.object(job_queue, "_new_id", return_value="0000beef"), self.assertRaises(OSError):
            self.queue.add("home", DATA, kind="receipt", title="t", source="admin", ingress="cli",
                           width=PRINT_WIDTH_DOTS, height=RASTER.height, render_ms=1, artifacts=staged, now=0)
        self.assertEqual(self.queue.jobs(now=0), [])
        self.assertEqual(self.queue._db.execute("SELECT COUNT(*) FROM job_events").fetchone()[0], 0)
        self.assertTrue(staged.is_dir())


class MoveTest(QueueTestCase):
    def test_move_takes_only_queued_jobs(self):
        sending = self.add("home", now=0)
        self.queue.take("home", now=1)
        printed = self.add("home", now=2)
        self.queue.take("home", now=3)
        self.queue.confirm(printed.id, now=4)
        cancelled = self.add("home", now=5)
        self.queue.cancel(cancelled.id, now=6)
        expiring = self.add("home", expires_in=10, now=7)
        queued = [self.add("home", now=8), self.add("home", now=9)]
        elsewhere = self.add("work", now=10)

        self.assertEqual(self.queue.move("home", "office", now=20), 2)
        for job in queued:
            self.assertEqual(self.queue.job(job.id, now=20).printer, "office")
            last = self.queue.job(job.id, now=20).events[-1]
            self.assertEqual((last.event, last.detail), (Event.MOVED, "home -> office"))
        for job in (sending, printed, cancelled, expiring):
            stored = self.queue.job(job.id, now=20)
            self.assertEqual(stored.printer, "home")
            self.assertNotIn(Event.MOVED, [e.event for e in stored.events])
        self.assertEqual(self.queue.job(elsewhere.id, now=20).printer, "work")
        self.assertEqual(self.status(sending.id), Status.SENDING)
        self.assertEqual(self.queue.take("office", now=21).id, queued[0].id)


class PrinterStateTest(QueueTestCase):
    def test_update_sets_only_the_given_fields(self):
        self.assertIsNone(self.queue.printer_state("home"))
        self.queue.update_printer_state("home", connected_since=100, last_seen=100, address="10.0.0.5",
                                        route="tunnel", client_version="0.1.0")
        self.queue.update_printer_state("home", last_seen=120, latency_ms=42.5)
        state = self.queue.printer_state("home")
        self.assertEqual((state.id, state.connected_since, state.last_seen, state.address, state.route,
                          state.latency_ms, state.client_version),
                         ("home", 100, 120, "10.0.0.5", "tunnel", 42.5, "0.1.0"))
        self.queue.update_printer_state("home", connected_since=None)
        self.assertIsNone(self.queue.printer_state("home").connected_since)
        self.assertEqual(self.queue.printer_state("home").last_seen, 120)

    def test_update_rejects_an_unknown_field(self):
        with self.assertRaisesRegex(ValueError, "online"):
            self.queue.update_printer_state("home", online=True)
        self.assertIsNone(self.queue.printer_state("home"))


class StatsTest(QueueTestCase):
    # 2026-10-12 00:00 in Sao Paulo (UTC-3).
    MIDNIGHT = datetime(2026, 10, 12, tzinfo=SAO_PAULO).timestamp()

    def build_history(self, now: float) -> None:
        """Two printers over the 30 hours before ``now``: settled jobs in creation order, then live ones."""
        rng = random.Random(7)
        for created in sorted(rng.uniform(now - 30 * 3600, now - 3600) for _ in range(150)):
            printer = rng.choice(["home", "office"])
            outcome = rng.choice(["printed", "printed", "printed", "failed", "cancelled", "expired"])
            # A 1 s expiry runs out before any later job is taken, so it never blocks the queue.
            job = self.add(printer, now=created, expires_in=1 if outcome == "expired" else rng.choice([600, 3600]),
                           height=rng.randrange(200, 3000))
            at = created + rng.uniform(1, 300)
            if outcome == "cancelled":
                self.queue.cancel(job.id, now=at)
            elif outcome != "expired":
                attempts = MAX_ATTEMPTS if outcome == "failed" else rng.randrange(1, MAX_ATTEMPTS + 1)
                for attempt in range(attempts):
                    self.assertEqual(self.queue.take(printer, now=at).id, job.id)
                    at += rng.uniform(1, 20)
                    if attempt < attempts - 1 or outcome == "failed":
                        self.queue.release(job.id, now=at)
                if outcome == "printed":
                    self.queue.mark_sent(job.id, now=at)
                    self.queue.confirm(job.id, now=at + rng.uniform(0.5, 5))
        for printed_at in (self.MIDNIGHT - 60, self.MIDNIGHT):
            job = self.add("home", now=printed_at - 30, height=800)
            self.assertEqual(self.queue.take("home", now=printed_at - 20).id, job.id)
            self.queue.confirm(job.id, now=printed_at)
        for created in sorted(rng.uniform(now - 3000, now - 600) for _ in range(10)):
            self.add(rng.choice(["home", "office"]), now=created)
        self.queue.take("home", now=now - 300)
        self.queue.take("office", now=now - 300)
        self.queue.update_printer_state("garage", last_seen=now)

    def brute_force(self, now: float, printer: str | None):
        jobs = self.queue.jobs(printer, limit=10_000, now=now)
        printed = [j for j in jobs if j.status == Status.PRINTED]
        today = [j for j in printed if self.MIDNIGHT <= j.printed_at <= now]
        last_day = [j for j in printed if now - DAY_SECONDS < j.printed_at <= now]
        failed = []
        for j in jobs:
            failed += [e for e in self.queue.job(j.id, now=now).events
                       if e.event == Event.FAILED and now - DAY_SECONDS < e.at <= now]
        names = {printer} if printer else {j.printer for j in jobs} | {"garage"}
        hourly = {name: [0] * 24 for name in sorted(names)}
        for j in last_day:
            start = now - DAY_SECONDS
            hour = next(h for h in range(24) if start + h * 3600 < j.printed_at <= start + (h + 1) * 3600)
            hourly[j.printer][hour] += 1
        return {
            "printed_today": len(today),
            "queued": sum(j.status == Status.QUEUED for j in jobs),
            "failed_24h": len(failed),
            "median_job_seconds": statistics.median(j.printed_at - j.created_at for j in last_day) if last_day else None,
            "paper_today_mm": sum(j.paper_mm for j in today),
            "hourly": hourly,
        }

    def assertStatsMatch(self, now: float, printer: str | None) -> None:
        stats = self.queue.stats(printer, now=now, tz=SAO_PAULO)
        expected = self.brute_force(now, printer)
        for name, value in expected.items():
            if isinstance(value, float):
                self.assertAlmostEqual(getattr(stats, name), value, msg=name)
            else:
                self.assertEqual(getattr(stats, name), value, name)

    def test_stats_agree_with_a_brute_force_count_across_midnight(self):
        now = self.MIDNIGHT + 6 * 3600 + 17
        self.build_history(now)
        for printer in (None, "home", "office"):
            self.assertStatsMatch(now, printer)
        stats = self.queue.stats(now=now, tz=SAO_PAULO)
        self.assertGreater(stats.printed_today, 0)
        self.assertGreater(stats.failed_24h, 0)
        self.assertGreater(stats.queued, 0)
        self.assertEqual(set(stats.hourly), {"home", "office", "garage"})

    def test_no_job_in_a_final_state_keeps_its_escpos_data(self):
        now = self.MIDNIGHT + 6 * 3600
        self.build_history(now)
        statuses = {job.status for job in self.queue.jobs(limit=10_000, now=now)}
        self.assertEqual(statuses, set(Status))
        kept = self.queue._db.execute(
            f"SELECT COUNT(*) FROM jobs WHERE data IS NOT NULL AND status IN ({', '.join('?' * len(FINAL))})", FINAL
        ).fetchone()[0]
        self.assertEqual(kept, 0)

    def test_a_job_printed_before_local_midnight_is_not_today(self):
        before = self.add("home", now=self.MIDNIGHT - 100, height=800)
        self.queue.take("home", now=self.MIDNIGHT - 90)
        self.queue.confirm(before.id, now=self.MIDNIGHT - 1)
        after = self.add("home", now=self.MIDNIGHT - 50, height=400)
        self.queue.take("home", now=self.MIDNIGHT - 40)
        self.queue.confirm(after.id, now=self.MIDNIGHT)

        stats = self.queue.stats(now=self.MIDNIGHT + 1800, tz=SAO_PAULO)
        self.assertEqual((stats.printed_today, stats.paper_today_mm), (1, 50))
        self.assertEqual(sum(stats.hourly["home"]), 2)
        self.assertEqual(stats.hourly["home"][23], 2)
        self.assertEqual(stats.median_job_seconds, (99 + 50) / 2)
        # The same instant in UTC is 03:30, so midnight UTC is earlier and both jobs count.
        self.assertEqual(self.queue.stats(now=self.MIDNIGHT + 1800, tz=timezone.utc).printed_today, 2)

    def test_stats_of_an_empty_queue(self):
        stats = self.queue.stats(now=self.MIDNIGHT, tz=SAO_PAULO)
        self.assertEqual((stats.printed_today, stats.queued, stats.failed_24h, stats.median_job_seconds,
                          stats.paper_today_mm, stats.hourly), (0, 0, 0, None, 0, {}))

    def test_default_today_starts_at_system_local_midnight(self):
        now = self.MIDNIGHT + 5 * 3600
        local_midnight = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        job = self.add("home", now=local_midnight - 10)
        self.queue.take("home", now=local_midnight - 5)
        self.queue.confirm(job.id, now=local_midnight)
        self.assertEqual(self.queue.stats(now=now).printed_today, 1)
        early = self.add("home", now=local_midnight - 10)
        self.queue.take("home", now=local_midnight - 5)
        self.queue.confirm(early.id, now=local_midnight - 1)
        self.assertEqual(self.queue.stats(now=now).printed_today, 1)


class ActivityTest(QueueTestCase):
    MIDNIGHT = StatsTest.MIDNIGHT

    def job(self, source: str, ingress: str, at: float, *, data: bytes = DATA):
        return self.queue.add("home", data, kind="receipt", title=f"{source} at {at}", source=source,
                              ingress=ingress, width=PRINT_WIDTH_DOTS, height=RASTER.height, render_ms=850,
                              now=at)

    def test_activity_counts_jobs_since_local_midnight_and_returns_each_sources_newest_job(self):
        self.job("morning-brief", "api", self.MIDNIGHT - 100)
        self.job("morning-brief", "api", self.MIDNIGHT + 10)
        newest = self.job("morning-brief", "api", self.MIDNIGHT + 20)
        sender = self.job("friend@example.com", "web", self.MIDNIGHT - 50)
        self.job("admin", "cli", self.MIDNIGHT + 30)
        self.job("morning-brief", "api", self.MIDNIGHT + 5000)
        now = self.MIDNIGHT + 3600

        self.assertEqual(self.queue.activity(("api", "web"), now=now, tz=SAO_PAULO), [
            SourceActivity("api", "morning-brief", 2, newest),
            SourceActivity("web", "friend@example.com", 0, sender),
        ])
        # Midnight UTC is three hours before midnight in Sao Paulo, so yesterday's jobs there are today here.
        in_utc = self.queue.activity(("api", "web"), now=now, tz=timezone.utc)
        self.assertEqual([(seen.source, seen.jobs_today) for seen in in_utc],
                         [("morning-brief", 3), ("friend@example.com", 1)])
        self.assertEqual(self.queue.activity(("web",), now=now, tz=SAO_PAULO),
                         [SourceActivity("web", "friend@example.com", 0, sender)])
        self.assertEqual(self.queue.activity((), now=now), [])

    def test_a_source_stays_listed_behind_more_than_5000_newer_jobs(self):
        old = self.job("old.friend@example.com", "web", 1000, data=b"\x1b@")
        for at in range(1001, 6003):
            self.job("morning-brief", "api", at, data=b"\x1b@")
        activity = self.queue.activity(("api", "web"), now=7000, tz=timezone.utc)
        self.assertEqual([(seen.source, seen.jobs_today, seen.last_job.id) for seen in activity],
                         [("morning-brief", 5002, activity[0].last_job.id), ("old.friend@example.com", 1, old.id)])
        self.assertEqual(activity[0].last_job.created_at, 6002)


if __name__ == "__main__":
    unittest.main()
