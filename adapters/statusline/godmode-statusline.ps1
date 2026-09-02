# Godmode statusline segment: prints the cached badge in milliseconds.
#
# The session-start hook writes ~/.claude/godmode-statusline.txt with the
# current enforcement marker ([GM ✓] proven HARD, [GM ~] partial/degraded,
# [GM ?] soft, [GM !] unavailable). This script only reads that cache -
# a statusline runs on every render and must never pay the CLI's startup.
# Wire it into the host statusLine command chain alongside other segments.
$cache = Join-Path $env:USERPROFILE ".claude\godmode-statusline.txt"
if (Test-Path $cache) {
  [Console]::Write((Get-Content $cache -Raw).Trim())
} else {
  [Console]::Write("[GM ]")
}
