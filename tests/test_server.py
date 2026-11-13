import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import _trusted_host  # noqa: E402


class HostCheckTests(unittest.TestCase):
    def test_accepts_local_origins_and_hosts(self):
        for value in (
            "http://127.0.0.1:8799",
            "http://localhost:8765",
            "https://localhost",
            "127.0.0.1:8799",
            "localhost:8765",
            "[::1]:8799",
            "::1",
        ):
            self.assertTrue(_trusted_host(value), value)

    def test_rejects_other_hosts(self):
        for value in (
            "",
            "http://evil.example",
            "https://127.0.0.1.evil.example",
            "http://localhost.evil.example:8799",
            "null",
        ):
            self.assertFalse(_trusted_host(value), value)


if __name__ == "__main__":
    unittest.main()
