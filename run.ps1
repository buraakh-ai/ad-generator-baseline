<#
.SYNOPSIS
    Runs Python for this project, working around a Windows Smart App Control
    block on the venv's small launcher stub (.venv\Scripts\python.exe).

.DESCRIPTION
    Smart App Control can retroactively flag and block small, unsigned
    launcher stubs like the one venv/uv venv creates at
    .venv\Scripts\python.exe, even after it's run fine for a while - it's a
    delayed reputation re-check, not something wrong with this specific
    file or this project. The actual full Python interpreter underneath
    (installed via uv, referenced by the venv's pyvenv.cfg "home =" line)
    is not blocked, so this script calls that interpreter directly and
    points PYTHONPATH at the venv's site-packages instead of relying on the
    blocked stub.

    If Smart App Control ever stops blocking .venv\Scripts\python.exe (or
    you're on a machine without this issue), you don't need this script -
    just use .venv\Scripts\python.exe (or an activated venv) as usual.

.EXAMPLE
    .\run.ps1 -m uvicorn backend.main:app --reload

.EXAMPLE
    .\run.ps1 -m streamlit run frontend/streamlit_app.py
#>
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"

$venvDir = Join-Path $PSScriptRoot ".venv"
$cfgPath = Join-Path $venvDir "pyvenv.cfg"
if (-not (Test-Path $cfgPath)) {
    throw "No .venv found at $venvDir - create it first (see README.md's Setup section)."
}

$homeLine = Get-Content $cfgPath | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
if (-not $homeLine) {
    throw "Could not find a 'home =' line in $cfgPath - is this a normal venv?"
}
$baseDir = ($homeLine -split '=', 2)[1].Trim()
$basePython = Join-Path $baseDir "python.exe"
if (-not (Test-Path $basePython)) {
    throw "Base interpreter not found at $basePython (from $cfgPath) - was it moved or uninstalled?"
}

$env:PYTHONPATH = Join-Path $venvDir "Lib\site-packages"

& $basePython @Args
exit $LASTEXITCODE
