# Capture closeout: executable example

Use this after an authorized, verified knowledge item passes the write gate.
The [example](../examples/verify_capture.py) consumes an existing successful
capture response from stdin. It is not a Runner subcommand, does not capture,
does not infer knowledge, and does not repair findings. It invokes the packaged
Runner with argument arrays (`shell=False`), forwarding every changed/new path
and the exact project/domain/pattern scope. Check and audit may persist health
reports. Use the same root, project and date as capture.

## End-to-end sequence

1. Finish the engineering task and evaluate each atomic knowledge item against
   the write gate. Load the relevant writing rules before capture.
2. Create or revise through capture with its ASCII request envelope. Check its
   exit code before treating stdout as a successful receipt.
3. For a non-skipped write, show `user_summary` **verbatim in the next
   user-facing message**, including when warnings occurred. Console output is
   not a substitute for the agent's message. Keep the receipt in memory across
   this message; do not capture again to recreate it or write a request file.
4. Pass the receipt to the example. It validates the scope and path arrays,
   runs check, then audit only if check returns Deep. Inspect its JSON and exit
   code. Exit 0 means orchestration completed or no new write was made; it does
   not mean there are no findings or that the knowledge is factually true.
5. Report write, warnings, check, audit and unresolved findings separately.
   Before the final reply, re-evaluate affected IDs if source, tests, commit,
   tag or release changed. Revise only material changes, then check again and
   read the decisive Current body/evidence in full.

## Bash / Zsh

`REQUEST_ENVELOPE` contains the existing encoder's ASCII output; `TODAY` is
the task date. The existing Quick Start describes creating the request.

```bash
CAPTURE_JSON=$(printf '%s' "$REQUEST_ENVELOPE" | python "$SKILL_DIR/scripts/tracebook_runner.py" \
  capture --root "$ROOT" --cwd "$CWD" --request - --today "$TODAY")
CAPTURE_EXIT=$?
# Stop on a nonzero CAPTURE_EXIT.
```

Pause here: inspect the receipt and send `user_summary` verbatim to the user.
Retain `CAPTURE_JSON` in host state; then execute verification separately:

```bash
if [ "$CAPTURE_EXIT" -eq 0 ]; then
  printf '%s' "$CAPTURE_JSON" | python "$SKILL_DIR/examples/verify_capture.py" \
    --root "$ROOT" --cwd "$CWD" --today "$TODAY"
fi
```

## PowerShell 5.1 / 7

`$request` is a JSON here-string, not a temporary file. Native stdout must be
decoded as UTF-8 **before** re-enveloping the receipt: an envelope cannot repair
text already corrupted by console decoding. Preserve the caller's settings.

```powershell
$oldConsoleEncoding = [Console]::OutputEncoding
$oldOutputEncoding = $OutputEncoding
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $OutputEncoding = [Console]::OutputEncoding
    $captureLines = & "$SKILL_DIR/scripts/New-TracebookRequestEnvelope.ps1" -Json $request |
        python "$SKILL_DIR/scripts/tracebook_runner.py" capture --root $ROOT --cwd $CWD --request - --today $TODAY
    $captureExit = $LASTEXITCODE
    if ($captureExit -ne 0) { throw "capture failed: $captureLines" }
    $captureJson = $captureLines -join "`n"
    $receipt = $captureJson | ConvertFrom-Json
}
finally {
    [Console]::OutputEncoding = $oldConsoleEncoding
    $OutputEncoding = $oldOutputEncoding
}
```

Pause here: send `$receipt.user_summary` verbatim to the user. Retain
`$captureJson` in host state. After that message, this ASCII-safe pipeline needs
no console encoding change:

```powershell
& "$SKILL_DIR/scripts/New-TracebookRequestEnvelope.ps1" -Json $captureJson |
    python "$SKILL_DIR/examples/verify_capture.py" --root $ROOT --cwd $CWD --today $TODAY
$verifyExit = $LASTEXITCODE
# Inspect JSON even when verifyExit is nonzero: capture may be committed.
```

A host that runs each tool in a fresh shell must retain the receipt in its own
session state, and restore UTF-8 settings in each shell invocation. Do not
assume shell variables survive a tool boundary.

## Paths through a JavaScript host

Setting a variable does not remove escaping requirements at the layer where
the literal is parsed. In JavaScript use `"C:\\Users\\name\\知识 库"` or
`"C:/Users/name/知识 库"`, not `"C:\Users\name\知识 库"`. Prefer a structured
process argv API when the host offers one. If generating PowerShell syntax,
single-quote each path and double embedded single quotes; do not interpolate
raw paths into a command string. Python should pass a list to subprocess,
not interpolate paths into `python -c` source. The example already does this.

## Outcomes and diagnostic layers

| Observation | Accurate conclusion / next action |
| --- | --- |
| `skipped_no_new_write` | No new write; no new health run. Prior health status is unknown, not newly verified. |
| capture `warnings` | Write committed; report cleanup warnings and continue checking. |
| `receipt_transport` / `receipt_validation` | Check not run; recover the original receipt/coordinates. Do not repeat capture. |
| JS parser / shell syntax error | Runner might never have started. Inspect the host's actual command and quoting first. |
| `process_start` | Health process could not start; fix interpreter/path availability. |
| `runner` | Inspect returned structured error and any persisted paths; capture remains committed. |
| `response_decode` / `response_contract` | Health progress uncertain; inspect stdout/stderr and encoding/version, not knowledge content. |
| `timeout` | Health persistence may be partial. Inspect transaction diagnostics before an authorized recovery. |
| check completed, audit failed | Check ran; Deep verification remains incomplete. Fix that audit failure, not capture. |
| `completed` with findings | Commands completed; findings remain review candidates, not proof of correctness or incorrectness. |

No automatic retries, rollback, lifecycle changes, or authority-page repairs
are performed. Fix the demonstrated layer, then run only the still-required
health operation when safe. This example has no persistent missing-check
ledger and cannot establish that an earlier skipped event was checked.
