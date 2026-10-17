# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
[CmdletBinding()]
param([string]$OutputPath)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
if (-not $OutputPath) { $OutputPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'workshop\preview.png' }
Add-Type -AssemblyName System.Drawing
$bitmap = New-Object System.Drawing.Bitmap 1024,1024
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$background = [System.Drawing.ColorTranslator]::FromHtml('#142F2B')
$cream = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#F4EBDD'))
$muted = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#ADBBB0'))
$gold = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#DCC38B'))
$goldPen = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml('#DCC38B')),6
$bluePen = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml('#A4C4C2')),6
$thinPen = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml('#496459')),2
$format = New-Object System.Drawing.StringFormat
$format.Alignment = [System.Drawing.StringAlignment]::Center
$titleFont = New-Object System.Drawing.Font 'Segoe UI',60,([System.Drawing.FontStyle]::Bold)
$subtitleFont = New-Object System.Drawing.Font 'Segoe UI',45,([System.Drawing.FontStyle]::Regular)
$smallFont = New-Object System.Drawing.Font 'Segoe UI',22,([System.Drawing.FontStyle]::Regular)
try {
    $graphics.Clear($background)
    $graphics.DrawRectangle($thinPen,42,42,940,940)
    $graphics.DrawString('DUAL ROMANCE',$titleFont,$cream,[System.Drawing.RectangleF]::new(50,130,924,110),$format)
    $graphics.DrawString('NO TANGO',$subtitleFont,$gold,[System.Drawing.RectangleF]::new(50,245,924,90),$format)
    $graphics.DrawEllipse($goldPen,287,405,290,290)
    $graphics.DrawEllipse($bluePen,447,405,290,290)
    $graphics.DrawLine($thinPen,225,754,799,754)
    $graphics.DrawString('EXPERIMENTAL  /  0.1.4',$smallFont,$gold,[System.Drawing.RectangleF]::new(50,790,924,60),$format)
    $graphics.DrawString('Hexiao Zhang',$smallFont,$muted,[System.Drawing.RectangleF]::new(50,874,924,60),$format)
    $bitmap.Save([System.IO.Path]::GetFullPath($OutputPath),[System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $graphics.Dispose(); $bitmap.Dispose()
    foreach ($item in @($cream,$muted,$gold,$goldPen,$bluePen,$thinPen,$format,$titleFont,$subtitleFont,$smallFont)) { $item.Dispose() }
}
Write-Output $OutputPath
