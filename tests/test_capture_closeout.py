"""Observable closeout branches, using real CLI flows separately for integration."""
import copy
import base64
import json
import re
from pathlib import Path
import subprocess
import shutil
import shlex
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.examples import verify_capture as example
from plugins.tracebook.skills.tracebook.scripts.request_transport import encode_envelope


class CaptureCloseoutTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="tb-closeout-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "知识 库's"
        self.root.mkdir()
        self.source = self.base / "源 码's"
        self.source.mkdir()
        self.receipt = dict(skipped=False, health_scope="project", warnings=[],
                            changed_paths=[str(self.root / "规则's.md"), str(self.root / "index.md")],
                            new_paths=[str(self.root / "规则's.md")], user_summary="已写入规则。")

    def verify(self, receipt=None):
        return example.verify(self.receipt if receipt is None else receipt,
                              root=self.root, cwd=self.source, today="2026-09-09")

    def response(self, check_type="Light", code=0, **extra):
        payload = dict(check_type=check_type, findings={"review_candidates": ["review, not fact"]},
                       report="Candidate requires review", changed_paths=[])
        payload.update(extra)
        return subprocess.CompletedProcess([], code, json.dumps(payload).encode(), b"")

    def test_all_paths_scope_warnings_and_findings_survive(self):
        for scope in ("project", "domain", "pattern"):
            with self.subTest(scope=scope), patch.object(example.subprocess, "run", return_value=self.response()) as run:
                self.receipt.update(health_scope=scope, warnings=["snapshot prune warning"])
                result = self.verify()
                self.assertEqual("completed", result["verification"])
                self.assertEqual(self.receipt, result["capture"])
                self.assertEqual("not_run", result["audit"]["state"])
                argv = run.call_args.args[0]
                self.assertEqual(scope, argv[argv.index("--scope") + 1])
                self.assertEqual(self.receipt["changed_paths"],
                                 [argv[i+1] for i, item in enumerate(argv) if item == "--changed"])
                self.assertEqual(self.receipt["new_paths"],
                                 [argv[i+1] for i, item in enumerate(argv) if item == "--new-path"])
                self.assertFalse(run.call_args.kwargs["shell"])
                self.assertTrue(result["check"]["response"]["findings"])

    def test_invalid_receipts_never_start_health_or_replay_capture(self):
        malformed = []
        for key in ("skipped", "changed_paths", "new_paths", "health_scope"):
            receipt = copy.deepcopy(self.receipt)
            del receipt[key]
            malformed.append(receipt)
        for changes in (dict(health_scope="all"), dict(changed_paths=[]),
                        dict(changed_paths="not-an-array"), dict(new_paths=[None]),
                        dict(skipped="false"), dict(skipped=True), dict(error="capture failed"),
                        dict(warnings="warning"), dict(new_paths=[str(self.root / "unreported")]),
                        dict(changed_paths=[str(self.source / "outside.md")]),
                        dict(changed_paths=["relative.md"]), dict(changed_paths=["bad\tpath"])):
            malformed.append(dict(self.receipt, **changes))
        for receipt in malformed:
            with self.subTest(receipt=receipt), patch.object(example.subprocess, "run") as run:
                result = self.verify(receipt)
                self.assertEqual("incomplete", result["verification"])
                self.assertEqual("receipt_validation", result["phase"])
                run.assert_not_called()

    def test_skip_does_not_claim_previous_event_checked(self):
        with patch.object(example.subprocess, "run") as run:
            result = self.verify(dict(self.receipt, skipped=True, changed_paths=[], new_paths=[]))
        self.assertEqual("skipped_no_new_write", result["verification"])
        self.assertEqual("not_run", result["check"]["state"])
        run.assert_not_called()

    def test_invalid_coordinates_and_timeout_are_rejected_before_health(self):
        for changes in (dict(root=self.base / "missing"), dict(cwd=self.base / "missing"),
                        dict(today="not-a-date"), dict(timeout=0), dict(timeout=float("nan")),
                        dict(timeout=float("inf"))):
            with self.subTest(changes=changes), patch.object(example.subprocess, "run") as run:
                options = dict(root=self.root, cwd=self.source, today="2026-09-09")
                options.update(changes)
                result = example.verify(self.receipt, **options)
                self.assertEqual("receipt_validation", result["phase"])
                run.assert_not_called()

    def test_deep_needs_successful_audit_with_identical_coordinates(self):
        for fail in (False, True):
            with self.subTest(fail=fail), patch.object(example.subprocess, "run", side_effect=[
                    self.response("Deep"), self.response(code=2 if fail else 0)]) as run:
                result = self.verify()
                self.assertEqual("completed", result["check"]["state"])
                self.assertEqual("incomplete" if fail else "completed", result["verification"])
                check_argv, audit_argv = [call.args[0] for call in run.call_args_list]
                self.assertEqual("audit", audit_argv[3])
                self.assertEqual(check_argv[4:check_argv.index("--changed")], audit_argv[4:])
                self.assertEqual(self.receipt, result["capture"])

    def test_process_runner_and_response_failures_preserve_write(self):
        cases = [(OSError("missing interpreter"), "process_start"),
                 (subprocess.TimeoutExpired("check", 1), "timeout"),
                 (self.response(code=2, error={"code": "AGGREGATE_FAILED", "changed_paths": ["report"]}), "runner"),
                 (subprocess.CompletedProcess([], 0, b"not json", b"diagnostic"), "response_decode"),
                 (self.response(check_type="Unknown"), "response_contract"),
                 (self.response(findings=None), "response_contract")]
        for outcome, phase in cases:
            with self.subTest(phase=phase), patch.object(example.subprocess, "run") as run:
                if isinstance(outcome, Exception):
                    run.side_effect = outcome
                else:
                    run.return_value = outcome
                result = self.verify()
                self.assertEqual(phase, result["check"]["phase"])
                self.assertEqual("incomplete", result["verification"])
                self.assertEqual(self.receipt, result["capture"])
                self.assertEqual("not_run", result["audit"]["state"])
                self.assertEqual(1, run.call_count)

    def test_cli_receipt_transport_is_lossless_and_invalid_input_is_nonmutating(self):
        receipt = dict(self.receipt, skipped=True, changed_paths=[], new_paths=[])
        raw = json.dumps(receipt, ensure_ascii=False).encode("utf-8")
        for payload, expected in ((raw, 0), (encode_envelope(raw), 0), (b"{", 2)):
            with self.subTest(payload=payload[:20]):
                result = subprocess.run([sys.executable, "-B", example.__file__,
                                         "--root", str(self.root), "--cwd", str(self.source)],
                                        input=payload, capture_output=True, timeout=20)
                self.assertEqual(expected, result.returncode, result.stderr)
                decoded = json.loads(result.stdout.decode("ascii"))
                if expected == 0:
                    self.assertEqual(receipt, decoded["capture"])
                else:
                    self.assertEqual("receipt_transport", decoded["phase"])
                self.assertEqual([], list(self.root.iterdir()))

    @unittest.skipUnless(sys.platform == "win32", "Windows native pipeline")
    def test_documented_powershell_closeout_with_unicode_and_quote_paths(self):
        skill = example.SCRIPTS.parent
        reference = (skill / "references/closeout-workflow.md").read_text(encoding="utf-8")
        # Join the two tool phases; the agent message between them is a host
        # acceptance concern, not something a subprocess test can establish.
        template = "\n".join(re.findall(r"```powershell\n(.*?)```", reference, re.S))
        (self.source / "retry.py").write_text("ATTEMPTS = 2\n", encoding="utf-8")
        request = json.dumps(dict(operation="create", knowledge_id="retry-limit", scope="project",
                                 kind="decision", title="重试规则", body="配置 ATTEMPTS = 2。",
                                 evidence=["retry.py:L1"]), ensure_ascii=False)
        def quote(value):
            return "'" + str(value).replace("'", "''") + "'"
        for engine in ("powershell", "pwsh"):
            if not shutil.which(engine):
                continue
            with self.subTest(engine=engine):
                root = self.root / engine
                assignments = "\n".join(f"${key} = {quote(value)}" for key, value in
                                         dict(SKILL_DIR=skill, ROOT=root, CWD=self.source,
                                              TODAY="2026-09-09", request=request).items())
                command = assignments + "\n" + template
                encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
                process = subprocess.run([engine, "-NoProfile", "-EncodedCommand", encoded],
                                         capture_output=True, timeout=90)
                self.assertEqual(0, process.returncode, process.stderr)
                result = json.loads(process.stdout)
                self.assertEqual("completed", result["verification"], result)
                self.assertTrue(all(Path(path).is_relative_to(root)
                                    for path in result["capture"]["changed_paths"]))
                page = next(root.rglob("retry-limit.md"))
                self.assertIn("重试规则", page.read_text(encoding="utf-8"))
                self.assertEqual([], result["check"]["response"]["findings"]["missing_sources"])

    @unittest.skipIf(sys.platform == "win32", "POSIX native pipeline")
    def test_documented_posix_closeout_with_unicode_and_quote_paths(self):
        skill = example.SCRIPTS.parent
        reference = (skill / "references/closeout-workflow.md").read_text(encoding="utf-8")
        template = "\n".join(re.findall(r"```bash\n(.*?)```", reference, re.S))
        (self.source / "retry.py").write_text("ATTEMPTS = 2\n", encoding="utf-8")
        request = dict(operation="create", knowledge_id="retry-limit", scope="project",
                       kind="decision", title="重试规则", body="ATTEMPTS = 2", evidence=["retry.py:L1"])
        envelope = encode_envelope(json.dumps(request).encode()).decode("ascii")
        for engine in ("bash", "zsh"):
            if not shutil.which(engine):
                continue
            with self.subTest(engine=engine):
                root = self.root / engine
                assignments = "\n".join(f"{key}={shlex.quote(str(value))}" for key, value in
                                         dict(SKILL_DIR=skill, ROOT=root, CWD=self.source,
                                              TODAY="2026-09-09", REQUEST_ENVELOPE=envelope).items())
                process = subprocess.run([engine, "-c", assignments + "\n" + template],
                                         capture_output=True, timeout=90)
                self.assertEqual(0, process.returncode, process.stderr)
                result = json.loads(process.stdout)
                self.assertEqual("completed", result["verification"], result)
                self.assertIn("重试规则", next(root.rglob("retry-limit.md")).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
