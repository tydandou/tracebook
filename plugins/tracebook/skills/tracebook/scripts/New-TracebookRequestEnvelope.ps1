[CmdletBinding(DefaultParameterSetName = 'Text')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Text')]
    [string] $Json,

    [Parameter(Mandatory = $true, ParameterSetName = 'File')]
    [string] $InputPath
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false, $true)

if ($PSCmdlet.ParameterSetName -eq 'File') {
    $resolvedPath = (Resolve-Path -LiteralPath $InputPath -ErrorAction Stop).Path
    $inputBytes = [System.IO.File]::ReadAllBytes($resolvedPath)
    if ($inputBytes.Length -ge 3 -and
        $inputBytes[0] -eq 0xEF -and
        $inputBytes[1] -eq 0xBB -and
        $inputBytes[2] -eq 0xBF) {
        $Json = $utf8.GetString($inputBytes, 3, $inputBytes.Length - 3)
    }
    else {
        $Json = $utf8.GetString($inputBytes)
    }
}

# Parse before wrapping so an invalid document never looks transport-valid.
$null = $Json | ConvertFrom-Json -ErrorAction Stop
$payloadBytes = $utf8.GetBytes($Json)
$sha = [System.Security.Cryptography.SHA256]::Create()
try {
    $digest = ([System.BitConverter]::ToString($sha.ComputeHash($payloadBytes))).Replace('-', '').ToLowerInvariant()
}
finally {
    $sha.Dispose()
}

$envelope = [ordered]@{
    transport_version = 1
    encoding = 'base64+utf-8'
    payload = [System.Convert]::ToBase64String($payloadBytes)
    sha256 = $digest
} | ConvertTo-Json -Compress

# Keep the value on PowerShell's success stream so it participates in a caller's
# pipeline. Windows PowerShell 5.1 may encode this stream as ASCII for a native
# command, which is safe because every envelope character is ASCII by design.
Write-Output $envelope
