$ErrorActionPreference = "Stop"

$startMessage = "Tracebook workflow: if this is nontrivial software-repository work " +
    "(analysis, debugging, review, code/config changes, tests, builds, " +
    "deployment, CI/CD, or incident diagnosis), invoke the Tracebook Skill " +
    "and resolve/read its minimal external context before proceeding. Before " +
    "the final response, capture and check only new, verified, durable " +
    "knowledge, or report exactly one skip reason: not-project-work, " +
    "no-durable-conclusion, unverified, already-known, or user-disabled. An " +
    "explicit no-write request disables capture, not relevant read-only context."

$stopMessage = "Tracebook final gate: ensure the response reports either the verified " +
    "capture plus health-check result, or one controlled skip reason " +
    "(not-project-work, no-durable-conclusion, unverified, already-known, " +
    "user-disabled). Do not capture raw logs, temporary answers, or inference."

try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $rawPayload = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($rawPayload)) {
        exit 0
    }

    try {
        $payload = $rawPayload | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        exit 0
    }

    if ($null -eq $payload -or $payload -isnot [pscustomobject]) {
        exit 0
    }

    $cwd = $payload.cwd
    if ($cwd -isnot [string] -or [string]::IsNullOrWhiteSpace($cwd) -or -not [IO.Directory]::Exists($cwd)) {
        exit 0
    }

    $git = Get-Command git -CommandType Application -ErrorAction SilentlyContinue
    if ($null -eq $git) {
        exit 0
    }

    $gitOutput = & $git.Path -C $cwd rev-parse --is-inside-work-tree 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::Join("`n", $gitOutput).Trim() -ne "true") {
        exit 0
    }

    $message = switch ($payload.hook_event_name) {
        "UserPromptSubmit" { $startMessage; break }
        "Stop" { $stopMessage; break }
        default { $null }
    }

    if ($null -ne $message) {
        [pscustomobject]@{
            continue = $true
            systemMessage = $message
        } | ConvertTo-Json -Compress
    }
}
catch {
    # Hooks must fail open: Codex work continues without a lifecycle reminder.
}

exit 0
