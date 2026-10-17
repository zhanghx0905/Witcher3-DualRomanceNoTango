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
$reportDirectory = Join-Path $repoRoot ('build\tests-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $reportDirectory | Out-Null
& $PythonExecutable (Join-Path $repoRoot 'scripts\check_release.py')
if ($LASTEXITCODE -ne 0) { throw 'Prebuilt release validation failed.' }
& $PythonExecutable (Join-Path $repoRoot 'src\verify.py') --game $GamePath --report (Join-Path $reportDirectory 'validation.json')
if ($LASTEXITCODE -ne 0) { throw 'Game-resource validation failed.' }
Write-Output ('Validation reports: ' + $reportDirectory)
