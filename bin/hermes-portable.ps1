param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$HermesArgs
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Bootstrap = Join-Path $Root 'bin/bootstrap_portable.py'

$python = $env:PYTHON
if (-not $python) {
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd) {
        & py -3.11 $Bootstrap @HermesArgs
        exit $LASTEXITCODE
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source }
}

if (-not $python) {
    Write-Error 'Python 3.11+ is required to start Hermes portable. Install Python, then rerun this launcher.'
    exit 1
}

& $python $Bootstrap @HermesArgs
exit $LASTEXITCODE
