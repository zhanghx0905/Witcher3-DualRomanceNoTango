# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$GamePath,
    [string]$PythonExecutable = 'python'
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$repoRoot = Split-Path -Parent $PSScriptRoot
$project = Get-Content -LiteralPath (Join-Path $repoRoot 'project.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$gameDirectory = (Get-Item -LiteralPath $GamePath).FullName
$runDirectory = Join-Path $repoRoot ('build\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
$stageDirectory = Join-Path $runDirectory ('DualRomanceNoTango-v' + $project.version)
New-Item -ItemType Directory -Path $stageDirectory | Out-Null

function Invoke-ProjectPython([string[]]$PythonArguments) {
    & $PythonExecutable @PythonArguments
    if ($LASTEXITCODE -ne 0) { throw ('Python command failed with exit code ' + $LASTEXITCODE) }
}

Invoke-ProjectPython @((Join-Path $repoRoot 'scripts\check_release.py'))
Invoke-ProjectPython @((Join-Path $repoRoot 'src\build.py'), '--game', $gameDirectory, '--out', $stageDirectory)
Invoke-ProjectPython @((Join-Path $repoRoot 'src\verify.py'), '--game', $gameDirectory, '--report', (Join-Path $stageDirectory 'validation.json'))
Invoke-ProjectPython @((Join-Path $repoRoot 'src\audit_coexistence.py'), '--game', $gameDirectory, '--content', (Join-Path $stageDirectory 'Mods\modDualRomanceNoTango\content'), '--out', (Join-Path $stageDirectory 'coexistence-audit.json'))
Invoke-ProjectPython @((Join-Path $repoRoot 'scripts\package_release.py'), '--stage', $stageDirectory)
Write-Output ('Build complete: ' + $runDirectory)
