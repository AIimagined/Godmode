# Godmode statusline segment: prints the cached badge in milliseconds.
#
# The session-start hook writes ~/.claude/godmode-statusline.txt with the
# current enforcement marker ([GM ✓] proven HARD, [GM ~] partial/degraded,
# [GM ?] soft, [GM !] unavailable). This script only reads that cache -
# a statusline runs on every render and must never pay the CLI's startup.
# Wire it into the host statusLine command chain alongside other segments.
#
# Color carries the marker's meaning at a glance: green when enforcement
# is proven, yellow when partial, dim when soft, red when unavailable.
# Override with GODMODE_STATUSLINE_COLOR=off for a monochrome terminal.
$cache = Join-Path $env:USERPROFILE ".claude\godmode-statusline.txt"
$badge = if (Test-Path $cache) { (Get-Content $cache -Raw).Trim() } else { "[GM ]" }
if ($env:GODMODE_STATUSLINE_COLOR -eq "off") {
  [Console]::Write($badge)
} else {
  $esc = [char]27
  $color = switch -Regex ($badge) {
    "\[GM ✓" { "38;5;42" }   # proven HARD: green
    "\[GM ~"      { "38;5;178" }  # partial/degraded: amber
    "\[GM \?"     { "38;5;245" }  # soft: dim gray
    "\[GM !"      { "38;5;196" }  # unavailable: red
    default       { "38;5;245" }
  }
  [Console]::Write("$esc[$color" + "m$badge$esc[0m")
}
