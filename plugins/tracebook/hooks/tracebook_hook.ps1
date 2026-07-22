param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("UserPromptSubmit", "Stop")]
    [string]$HookEvent
)

$ErrorActionPreference = "Stop"

$startMessage = "Tracebook workflow: if this is nontrivial software-repository work " +
    "(analysis, debugging, review, code/config changes, tests, builds, " +
    "deployment, CI/CD, or incident diagnosis), invoke the Tracebook Skill " +
    "and resolve/read its minimal external context before proceeding, then use " +
    "deterministic context retrieval for task-relevant authority pages. Before " +
    "the final response, assess whether new verified durable knowledge exists " +
    "and capture/check it only when it does. An " +
    "explicit no-write request disables capture, not relevant read-only context."

$stopMessage = "Tracebook final reminder: assess whether this task produced verified, " +
    "durable knowledge. Capture and check it only when it did; routine tasks " +
    "need no skip report. Do not capture raw logs, temporary answers, or inference."

try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $null = [Console]::In.ReadToEnd()

    $cwd = (Get-Location).Path
    if ([string]::IsNullOrWhiteSpace($cwd) -or -not [IO.Directory]::Exists($cwd)) {
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

    $message = switch ($HookEvent) {
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
