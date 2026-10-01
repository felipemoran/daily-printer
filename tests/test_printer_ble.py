import asyncio
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from printer import BLE_BYTES_PER_SECOND, _ble_bytes_per_second, _send_paced  # noqa: E402


class SendPacedTest(unittest.TestCase):
    def _send(self, data: bytes, rate: float) -> tuple[list[bytes], float]:
        chunks: list[bytes] = []

        async def write(chunk: bytes) -> None:
            chunks.append(chunk)

        start = time.monotonic()
        asyncio.run(_send_paced(write, data, chunk_size=20, bytes_per_second=rate))
        return chunks, time.monotonic() - start

    def test_sends_every_byte_in_order_in_chunk_sized_pieces(self):
        data = bytes(range(256)) * 2
        chunks, _ = self._send(data, rate=1_000_000)
        self.assertEqual(b"".join(chunks), data)
        self.assertTrue(all(len(chunk) == 20 for chunk in chunks[:-1]))
        self.assertEqual(len(chunks[-1]), len(data) % 20)

    def test_holds_the_byte_rate(self):
        _, elapsed = self._send(b"x" * 400, rate=2000)  # 0.2 s at the target rate
        self.assertGreater(elapsed, 0.18)
        self.assertLess(elapsed, 0.6)


class RateOverrideTest(unittest.TestCase):
    def test_defaults_to_the_constant(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_ble_bytes_per_second(), BLE_BYTES_PER_SECOND)

    def test_env_var_overrides(self):
        with mock.patch.dict(os.environ, {"DAILY_PRINTER_BLE_BPS": "1500"}):
            self.assertEqual(_ble_bytes_per_second(), 1500)

    def test_rejects_non_positive_rate(self):
        for raw in ("0", "-5", "nan", "abc"):
            with self.subTest(raw=raw), mock.patch.dict(os.environ, {"DAILY_PRINTER_BLE_BPS": raw}):
                with self.assertRaises(ValueError):
                    _ble_bytes_per_second()


if __name__ == "__main__":
    unittest.main()
