import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo" / "cross_session_demo.py"


class CrossSessionDemoTest(unittest.TestCase):
    def test_demo_captures_checks_and_recalls_the_fact(self) -> None:
        result = subprocess.run(
            [sys.executable, str(DEMO), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("refund-retry-policy", payload["session_1"]["knowledge_id"])
        self.assertEqual("refund-retry-policy", payload["session_2"]["recalled_knowledge_id"])
        self.assertEqual(payload["session_1"]["fact"], payload["session_2"]["fact"])
        self.assertTrue(payload["verification"]["broken_links"])
        self.assertTrue(payload["verification"]["missing_sources"])
        self.assertEqual("cross-session retrieval verified", payload["result"])


if __name__ == "__main__":
    unittest.main()
