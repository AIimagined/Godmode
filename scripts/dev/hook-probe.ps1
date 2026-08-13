# scripts/dev/hook-probe.ps1 - median PreToolUse hook latency over 7 spawns.
# The deciding artefact is the printed median; do not pipe this script's
# output through a filter when quoting it.
$payload = '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git status"}}'
$times = @()
# one unmeasured warm-up spawn so the OS file cache is comparable across runs
$payload | python hooks/godmode_session_hook.py pre-action *> $null
for ($i = 0; $i -lt 7; $i++) {
    $t0 = [Diagnostics.Stopwatch]::StartNew()
    $payload | python hooks/godmode_session_hook.py pre-action *> $null
    $t0.Stop()
    $times += $t0.Elapsed.TotalMilliseconds
}
$sorted = $times | Sort-Object
"median_ms=$([math]::Round($sorted[3], 1))"
"all=$(($sorted | ForEach-Object { [math]::Round($_, 0) }) -join ',')"
