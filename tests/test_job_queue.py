import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_queue import MAX_ATTEMPTS, JobQueue, Status  # noqa: E402


class JobQueueTest(unittest.TestCase):
    def setUp(self):
        self.queue = JobQueue(":memory:")
        self.addCleanup(self.queue.close)

    def status(self, job_id: str) -> Status:
        return next(job.status for job in self.queue.jobs(now=0) if job.id == job_id)

    def test_delivers_oldest_first_per_printer_with_data(self):
        first = self.queue.add("home", b"one", now=0)
        self.queue.add("work", b"other", now=1)
        self.queue.add("home", b"two", now=2)
        job = self.queue.take("home", now=3)
        self.assertEqual((job.id, job.data, job.attempts, job.status), (first.id, b"one", 1, Status.SENDING))
        self.assertEqual(self.queue.take("home", now=3).data, b"two")
        self.assertIsNone(self.queue.take("home", now=3))

    def test_confirm_marks_printed_and_drops_data(self):
        job = self.queue.add("home", b"x", now=0)
        self.queue.take("home", now=0)
        self.queue.confirm(job.id)
        self.assertEqual(self.status(job.id), Status.PRINTED)
        self.assertIsNone(self.queue.take("home", now=0))

    def test_release_retries_until_the_last_attempt_then_fails(self):
        job = self.queue.add("home", b"x", now=0)
        for _ in range(MAX_ATTEMPTS - 1):
            self.queue.release(self.queue.take("home", now=0).id, now=0)
            self.assertEqual(self.status(job.id), Status.QUEUED)
        self.queue.release(self.queue.take("home", now=0).id, now=0)
        self.assertEqual(self.status(job.id), Status.FAILED)
        self.assertIsNone(self.queue.take("home", now=0))

    def test_expired_jobs_are_not_delivered(self):
        job = self.queue.add("home", b"x", expires_in=60, now=0)
        self.assertIsNone(self.queue.take("home", now=60))
        self.assertEqual(self.status(job.id), Status.EXPIRED)

    def test_release_after_expiry_expires_instead_of_requeueing(self):
        job = self.queue.add("home", b"x", expires_in=60, now=0)
        self.queue.take("home", now=10)
        self.queue.release(job.id, now=61)
        self.assertEqual(self.status(job.id), Status.EXPIRED)

    def test_cancel_and_clear(self):
        one = self.queue.add("home", b"1", now=0)
        two = self.queue.add("home", b"2", now=1)
        work = self.queue.add("work", b"3", now=2)
        self.assertTrue(self.queue.cancel(one.id))
        self.assertFalse(self.queue.cancel(one.id))
        self.assertEqual(self.queue.clear("home"), 1)
        self.assertEqual(self.status(two.id), Status.CANCELLED)
        self.assertEqual(self.status(work.id), Status.QUEUED)

    def test_a_cancelled_job_in_flight_is_not_marked_printed(self):
        job = self.queue.add("home", b"x", now=0)
        self.queue.take("home", now=0)
        self.queue.cancel(job.id)
        self.queue.confirm(job.id)
        self.assertEqual(self.status(job.id), Status.CANCELLED)

    def test_survives_a_restart_and_requeues_jobs_left_sending(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jobs.db"
            queue = JobQueue(path)
            job = queue.add("home", b"x", now=0)
            queue.take("home", now=0)
            queue.close()

            queue = JobQueue(path)
            queue.release_all(now=1)
            self.assertEqual(queue.take("home", now=1).id, job.id)
            queue.close()


if __name__ == "__main__":
    unittest.main()
