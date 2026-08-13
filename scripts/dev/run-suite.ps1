# scripts/dev/run-suite.ps1 - shard the unittest suite across processes.
# Each shard's FULL log is the deciding artefact (never pipe it); this
# wrapper only aggregates exit codes.
param([int]$Shards = 4)
$tests = Get-ChildItem tests -Filter "test_*.py" | Sort-Object Name | Select-Object -ExpandProperty BaseName
$jobs = @()
for ($s = 0; $s -lt $Shards; $s++) {
    $mine = @(); for ($i = $s; $i -lt $tests.Count; $i += $Shards) { $mine += "tests.$($tests[$i])" }
    $log = Join-Path $env:TEMP "suite-shard-$s.log"
    $jobs += Start-Job -ScriptBlock {
        param($modules, $log, $cwd)
        Set-Location $cwd
        & python -m unittest @modules *> $log
        $LASTEXITCODE
    } -ArgumentList ($mine, $log, (Get-Location).Path)
}
$codes = $jobs | ForEach-Object { Receive-Job -Job $_ -Wait }
$jobs | Remove-Job
$total = 0
for ($s = 0; $s -lt $Shards; $s++) {
    $log = Join-Path $env:TEMP "suite-shard-$s.log"
    $ran = (Select-String -Path $log -Pattern "^Ran (\d+) tests").Matches | ForEach-Object { $_.Groups[1].Value }
    "shard $s : Ran $ran, exit $($codes[$s]) -> $log"
    $total += [int]$ran
}
"total_tests=$total"
if (($codes | Measure-Object -Maximum).Maximum -gt 0) { "VERDICT=FAILED (read the shard logs)"; exit 1 }
"VERDICT=OK"; exit 0
