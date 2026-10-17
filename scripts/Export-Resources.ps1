# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
[CmdletBinding()]
param([string]$OutputDirectory, [string]$PythonExecutable = 'python')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $repoRoot ('build\cooked-export-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
}
& $PythonExecutable (Join-Path $PSScriptRoot 'export_resources.py') --out $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'Cooked resource export failed.' }
