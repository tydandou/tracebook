import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.check_knowledge import run_check
from plugins.tracebook.skills.tracebook.scripts.request_transport import (
    decode_request,
    encode_envelope,
    suspicious_text_findings,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "plugins" / "tracebook" / "skills" / "tracebook" / "scripts" / "tracebook_runner.py"
POWERSHELL_ENVELOPE = ROOT / "plugins" / "tracebook" / "skills" / "tracebook" / "scripts" / "New-TracebookRequestEnvelope.ps1"
MULTILINGUAL_REQUEST = ROOT / "tests" / "fixtures" / "multilingual-request.json"


class RequestTransportTest(unittest.TestCase):
    def test_envelope_round_trips_multilingual_unicode_without_normalization(self) -> None:
        values = [
            "English",
            "\u4e2d\u6587",
            "\u65e5\u672c\u8a9e",
            "\u0627\u0644\u0639\u0631\u0628\u064a\u0629\u061f",
            "\u0420\u0443\u0441\u0441\u043a\u0438\u0439",
            "caf\u00e9",
            "cafe\u0301",
            "\u200fRTL",
            "\U0001f680",
        ]
        payload = {"operation": "create", "knowledge_id": "unicode", "values": values}
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        envelope = encode_envelope(raw)
        decoded = decode_request(envelope)

        self.assertTrue(envelope.isascii())
        self.assertEqual(payload, decoded.payload)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), decoded.sha256)
        self.assertEqual("base64+utf-8", decoded.transport)

    def test_envelope_rejects_tampering_and_non_strict_base64(self) -> None:
        raw = b'{"operation":"create","knowledge_id":"x"}'
        envelope = json.loads(encode_envelope(raw))
        envelope["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            decode_request(json.dumps(envelope).encode("ascii"))
        envelope["payload"] += "!"
        with self.assertRaisesRegex(ValueError, "strict base64"):
            decode_request(json.dumps(envelope).encode("ascii"))

    def test_envelope_preserves_and_accepts_a_utf8_bom_request(self) -> None:
        raw = b'\xef\xbb\xbf{"operation":"create","knowledge_id":"bom"}'
        decoded = decode_request(encode_envelope(raw))
        self.assertEqual("bom", decoded.payload["knowledge_id"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), decoded.sha256)

    def test_language_neutral_corruption_gate_preserves_real_punctuation(self) -> None:
        valid = "Why? \u0644\u0645\u0627\u0630\u0627\u061f \u306a\u305c\uff1f \u00bfPor qu\u00e9?"
        self.assertEqual([], suspicious_text_findings(valid))
        findings = suspicious_text_findings({"title": "???????"})
        self.assertEqual(1, len(findings))
        with self.assertRaisesRegex(ValueError, "SUSPECTED_LOSSY_ENCODING"):
            decode_request(b'{"operation":"create","knowledge_id":"x","title":"????"}')
        decoded = decode_request(
            b'{"operation":"create","knowledge_id":"x","title":"????"}',
            allow_suspicious=True,
        )
        self.assertEqual("????", decoded.payload["title"])

    def test_invalid_capture_is_rejected_before_root_initialization(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            repo = base / "repo"
            repo.mkdir()
            result = subprocess.run(
                [sys.executable, str(RUNNER), "capture", "--root", str(root),
                 "--cwd", str(repo), "--request", "-"],
                cwd=base,
                input=b'{"operation":"create","knowledge_id":"x","title":"????"}',
                capture_output=True,
                check=False,
            )
            response = json.loads(result.stdout.decode("utf-8"))
            self.assertEqual(2, result.returncode, response)
            self.assertIn("SUSPECTED_LOSSY_ENCODING", response["error"])
            self.assertFalse(root.exists())

    @unittest.skipUnless(sys.platform == "win32", "PowerShell compatibility is Windows-specific")
    def test_installed_powershell_versions_emit_valid_ascii_envelopes(self) -> None:
        engines = [name for name in ("powershell", "pwsh") if shutil.which(name)]
        self.assertTrue(engines)
        expected = json.loads(MULTILINGUAL_REQUEST.read_text(encoding="utf-8"))
        for engine in engines:
            with self.subTest(engine=engine):
                result = subprocess.run(
                    [engine, "-NoProfile", "-File", str(POWERSHELL_ENVELOPE),
                     "-InputPath", str(MULTILINGUAL_REQUEST)],
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))
                self.assertTrue(result.stdout.isascii())
                self.assertEqual(expected, decode_request(result.stdout).payload)

    @unittest.skipUnless(sys.platform == "win32", "PowerShell compatibility is Windows-specific")
    def test_powershell_envelope_participates_in_a_real_native_pipeline(self) -> None:
        engines = [name for name in ("powershell", "pwsh") if shutil.which(name)]
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "repo"
            repo.mkdir()
            for engine in engines:
                root = base / f"knowledge-{engine}"
                command = (
                    f"& '{POWERSHELL_ENVELOPE}' -InputPath '{MULTILINGUAL_REQUEST}' | "
                    f"& '{sys.executable}' '{RUNNER}' capture --root '{root}' "
                    f"--cwd '{repo}' --request - --today 2026-08-12"
                )
                with self.subTest(engine=engine):
                    result = subprocess.run(
                        [engine, "-NoProfile", "-Command", command],
                        capture_output=True,
                        check=False,
                    )
                    response = json.loads(result.stdout.decode("utf-8"))
                    self.assertEqual(0, result.returncode, response)
                    self.assertEqual("base64+utf-8", response["request_transport"])
                    page = next(root.rglob("multilingual-transport-smoke.md"))
                    self.assertIn(
                        "Unicode transport: \u4e2d\u6587",
                        page.read_text(encoding="utf-8"),
                    )

    def test_health_check_reports_existing_lossy_text_with_line_evidence(self) -> None:
        from datetime import date

        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "01-projects" / "demo"
            project.mkdir(parents=True)
            page = project / "broken.md"
            page.write_text("# ???????\n", encoding="utf-8")
            report = run_check(root, project, [page], date(2026, 8, 12))
            self.assertEqual(1, len(report.content_integrity_issues))
            self.assertIn("broken.md:L1", report.content_integrity_issues[0])


if __name__ == "__main__":
    unittest.main()
