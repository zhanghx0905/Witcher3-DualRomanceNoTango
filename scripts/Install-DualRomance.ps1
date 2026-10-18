# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet('Install', 'Update', 'Disable', 'Enable', 'Verify')]
    [string]$Action = 'Install',
    [Parameter(Mandatory = $true)][string]$GamePath,
    [string]$PackageRoot
)

$ErrorActionPreference = 'Stop'

if (-not $PackageRoot) {
    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'build-manifest.json')) {
        $PackageRoot = $PSScriptRoot
    } else {
        $PackageRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'release'
    }
}
$PackageRoot = (Get-Item -LiteralPath $PackageRoot).FullName
$manifestDirectory = $PackageRoot
$payloadDirectory = $PackageRoot
if (Test-Path -LiteralPath (Join-Path $PackageRoot 'metadata\build-manifest.json')) {
    $manifestDirectory = Join-Path $PackageRoot 'metadata'
    $payloadDirectory = Join-Path $PackageRoot 'payload'
}

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$modName = 'modDualRomanceNoTango'
$disabledName = 'disabled_DualRomanceNoTango'
$gameDirectory = (Get-Item -LiteralPath $GamePath).FullName.TrimEnd('\')
$modsDirectory = [System.IO.Path]::GetFullPath((Join-Path $gameDirectory 'Mods'))
$activeDirectory = [System.IO.Path]::GetFullPath((Join-Path $modsDirectory $modName))
$disabledDirectory = [System.IO.Path]::GetFullPath((Join-Path $modsDirectory $disabledName))
$packageDirectory = Join-Path $payloadDirectory ('Mods\' + $modName)
$manifest = Get-Content -LiteralPath (Join-Path $manifestDirectory 'build-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$compatibility = Get-Content -LiteralPath (Join-Path $manifestDirectory 'compatibility.json') -Raw -Encoding UTF8 | ConvertFrom-Json

function Assert-ContainedModPath([string]$Path) {
    $resolved = [System.IO.Path]::GetFullPath($Path)
    if ((Split-Path -Parent $resolved) -ne $modsDirectory) {
        throw "Mod path is outside the intended Mods directory: $resolved"
    }
    if ((Test-Path -LiteralPath $modsDirectory) -and
        ((Get-Item -LiteralPath $modsDirectory).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw 'Mods directory is a junction/symlink. Use manual installation after checking its destination.'
    }
    if (Test-Path -LiteralPath $resolved) {
        $items = @((Get-Item -LiteralPath $resolved)) + @(Get-ChildItem -LiteralPath $resolved -Recurse -Force)
        if ($items | Where-Object { $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint }) {
            throw 'Mod directory contains junctions/symlinks; refusing to operate on it.'
        }
    }
}

function Get-Sha256([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [System.BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '')
    } finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

function Assert-ContentHashes([string]$Directory) {
    $bundle = Join-Path $Directory 'content\blob0.bundle'
    $metadata = Join-Path $Directory 'content\metadata.store'
    if ((Get-Sha256 $bundle) -ne $manifest.bundle_sha256) {
        throw "Bundle hash mismatch: $bundle"
    }
    if ((Get-Sha256 $metadata) -ne $manifest.metadata_sha256) {
        throw "Metadata hash mismatch: $metadata"
    }
}

Assert-ContainedModPath $activeDirectory
Assert-ContainedModPath $disabledDirectory
Assert-ContentHashes $packageDirectory

if ($Action -in 'Install', 'Update', 'Enable') {
    if (Get-Process -Name 'witcher3' -ErrorAction SilentlyContinue) {
        throw 'Close The Witcher 3 before changing this mod.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $gameDirectory 'bin\x64_dx12\witcher3.exe'))) {
        throw 'Expected Remastered executable was not found.'
    }
    $steamAppsDirectory = Split-Path -Parent (Split-Path -Parent $gameDirectory)
    $steamManifestPath = Join-Path $steamAppsDirectory 'appmanifest_292030.acf'
    if (-not (Test-Path -LiteralPath $steamManifestPath)) {
        throw 'This package targets the inspected Steam installation; its Steam manifest was not found.'
    }
    $steamManifestText = Get-Content -LiteralPath $steamManifestPath -Raw -Encoding UTF8
    $buildMatch = [regex]::Match($steamManifestText, '"buildid"\s+"([0-9]+)"')
    if (-not $buildMatch.Success -or $buildMatch.Groups[1].Value -ne [string]$compatibility.steam_build_id) {
        throw 'Game build changed. Rebuild/rebase the mod before installation.'
    }
}

switch ($Action) {
    'Update' {
        if (-not (Test-Path -LiteralPath $activeDirectory)) { throw 'Active mod was not found. Use -Action Install for a new installation.' }
        if (Test-Path -LiteralPath $disabledDirectory) { throw 'A disabled copy also exists; resolve the duplicate before updating.' }
        $previous = Get-Content -LiteralPath (Join-Path $manifestDirectory 'previous-version.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $installedBundle = (Get-Sha256 (Join-Path $activeDirectory 'content\blob0.bundle'))
        $installedMetadata = (Get-Sha256 (Join-Path $activeDirectory 'content\metadata.store'))
        if ($installedBundle -eq $manifest.bundle_sha256 -and $installedMetadata -eq $manifest.metadata_sha256) {
            Write-Output 'This update is already installed.'
            break
        }
        if ($installedBundle -ne $previous.bundle_sha256 -or $installedMetadata -ne $previous.metadata_sha256) {
            throw 'Installed files differ from the known previous version. Refusing to overwrite an unknown modification.'
        }
        $backupRoot = Join-Path $gameDirectory 'ModBackups\DualRomanceNoTango'
        $backupDirectory = [System.IO.Path]::GetFullPath((Join-Path $backupRoot (Get-Date -Format 'yyyyMMdd-HHmmss-fff')))
        if ((Split-Path -Parent $backupDirectory) -ne [System.IO.Path]::GetFullPath($backupRoot)) { throw 'Unexpected backup path.' }
        if ($PSCmdlet.ShouldProcess($activeDirectory, 'Back up version 0.1.9 and install version 0.1.10')) {
            New-Item -ItemType Directory -Path $backupDirectory | Out-Null
            Copy-Item -LiteralPath (Join-Path $activeDirectory 'content') -Destination $backupDirectory -Recurse
            try {
                foreach ($fileName in 'blob0.bundle', 'metadata.store') {
                    Copy-Item -LiteralPath (Join-Path $packageDirectory ('content\' + $fileName)) -Destination (Join-Path $activeDirectory ('content\' + $fileName)) -Force
                }
                Assert-ContentHashes $activeDirectory
            } catch {
                foreach ($fileName in 'blob0.bundle', 'metadata.store') {
                    Copy-Item -LiteralPath (Join-Path $backupDirectory ('content\' + $fileName)) -Destination (Join-Path $activeDirectory ('content\' + $fileName)) -Force
                }
                throw
            }
            Write-Output 'Updated to 0.1.10-experimental. Restart the game, travel to another map and return to Corvo Bianco to reload the romance-specific manor layout.'
            Write-Output "Previous version backup: $backupDirectory"
        }
    }
    'Install' {
        if ((Test-Path -LiteralPath $activeDirectory) -or (Test-Path -LiteralPath $disabledDirectory)) {
            throw 'This mod is already present. Use Verify, Enable or Disable; existing files will not be overwritten.'
        }
        if ($PSCmdlet.ShouldProcess($activeDirectory, 'Install experimental Dual Romance mod')) {
            New-Item -ItemType Directory -Path $modsDirectory -Force | Out-Null
            Copy-Item -LiteralPath $packageDirectory -Destination $modsDirectory -Recurse
            Assert-ContentHashes $activeDirectory
            Write-Output "Installed: $activeDirectory"
            Write-Output 'Use a save before the scene being tested. In-game testing is still required.'
        }
    }
    'Disable' {
        if (Get-Process -Name 'witcher3' -ErrorAction SilentlyContinue) {
            throw 'Close The Witcher 3 first.'
        }
        if (-not (Test-Path -LiteralPath $activeDirectory)) { throw 'Active mod was not found.' }
        if (Test-Path -LiteralPath $disabledDirectory) { throw 'A disabled copy already exists.' }
        if ($PSCmdlet.ShouldProcess($activeDirectory, 'Disable by renaming this mod folder')) {
            Rename-Item -LiteralPath $activeDirectory -NewName $disabledName
            Write-Output "Disabled: $disabledDirectory"
            Write-Output 'To return to the original quest state, load your pre-install manual save.'
        }
    }
    'Enable' {
        if (-not (Test-Path -LiteralPath $disabledDirectory)) { throw 'Disabled mod was not found.' }
        if (Test-Path -LiteralPath $activeDirectory) { throw 'An active copy already exists.' }
        Assert-ContentHashes $disabledDirectory
        if ($PSCmdlet.ShouldProcess($disabledDirectory, 'Enable this mod folder')) {
            Rename-Item -LiteralPath $disabledDirectory -NewName $modName
            Write-Output "Enabled: $activeDirectory"
        }
    }
    'Verify' {
        Write-Output 'Package content hashes: OK'
        $verificationDirectory = $null
        if (Test-Path -LiteralPath $activeDirectory) {
            $verificationDirectory = $activeDirectory
        } elseif (Test-Path -LiteralPath $disabledDirectory) {
            $verificationDirectory = $disabledDirectory
        } else {
            Write-Output 'This mod is not installed.'
        }
        if ($verificationDirectory) {
            $actualBundle = (Get-Sha256 (Join-Path $verificationDirectory 'content\blob0.bundle'))
            $actualMetadata = (Get-Sha256 (Join-Path $verificationDirectory 'content\metadata.store'))
            if ($actualBundle -eq $manifest.bundle_sha256 -and $actualMetadata -eq $manifest.metadata_sha256) {
                Write-Output 'Installed content hashes: OK (0.1.10-experimental)'
            } else {
                $previous = Get-Content -LiteralPath (Join-Path $manifestDirectory 'previous-version.json') -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($actualBundle -ne $previous.bundle_sha256 -or $actualMetadata -ne $previous.metadata_sha256) {
                    throw 'Installed files match neither this package nor the known previous version.'
                }
                Write-Output ('Installed content matches known previous version: ' + $previous.version + '. Update is pending.')
            }
        }
        Write-Output 'Hash verification does not confirm in-game behavior.'
    }
}
