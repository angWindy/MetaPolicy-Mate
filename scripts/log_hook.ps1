param(
    [string]$Tool = "codex"
)

# Native Windows logger for Codex hooks. It avoids depending on Bash or on a
# Python installation outside the repository sandbox.
$utf8NoBom = New-Object Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$rawInput = [Console]::In.ReadToEnd().Trim()
if (-not $rawInput) {
    exit 0
}

try {
    $data = $rawInput | ConvertFrom-Json
} catch {
    exit 0
}

function Invoke-GitValue {
    param([string[]]$Arguments)

    try {
        return (& git @Arguments 2>$null | Out-String).Trim()
    } catch {
        return ""
    }
}

function Limit-Text {
    param(
        [AllowNull()][object]$Value,
        [int]$Length
    )

    if ($null -eq $Value) {
        return ""
    }

    $text = [string]$Value
    if ($text.Length -le $Length) {
        return $text
    }

    return $text.Substring(0, $Length)
}

$origin = Invoke-GitValue @("remote", "get-url", "origin")
if (-not $origin) {
    exit 0
}

$repo = ($origin.TrimEnd("/") -split "/")[-1]
if ($repo.EndsWith(".git")) {
    $repo = $repo.Substring(0, $repo.Length - 4)
}

$eventName = if ($data.hook_event_name) {
    [string]$data.hook_event_name
} else {
    [string]$data.event
}
$prompt = Limit-Text $data.prompt 1000

if (-not $prompt -and $eventName -notin @("Stop", "SessionEnd")) {
    exit 0
}

$entry = [ordered]@{
    ts              = [DateTimeOffset]::Now.ToString("o")
    tool            = $Tool.ToLowerInvariant()
    event           = $eventName
    session_id      = Limit-Text $data.session_id 200
    model           = Limit-Text $data.model 200
    repo            = $repo
    branch          = Invoke-GitValue @("rev-parse", "--abbrev-ref", "HEAD")
    commit          = Invoke-GitValue @("rev-parse", "--short", "HEAD")
    student         = Invoke-GitValue @("config", "user.email")
    prompt          = $prompt
    turn_id         = Limit-Text $data.turn_id 200
    transcript_path = Limit-Text $data.transcript_path 1000
}

$logDirectory = if ($env:AI_LOG_DIR) { $env:AI_LOG_DIR } else { ".ai-log" }
[IO.Directory]::CreateDirectory($logDirectory) | Out-Null
$logFile = Join-Path $logDirectory "session.jsonl"
$jsonLine = ($entry | ConvertTo-Json -Compress -Depth 10) + [Environment]::NewLine
[IO.File]::AppendAllText($logFile, $jsonLine, $utf8NoBom)

# Codex parses stdout as a hook control response. Keep the response within the
# documented common hook schema so Stop does not reject an otherwise successful
# logging run as invalid JSON output.
Write-Output '{"continue":true}'
