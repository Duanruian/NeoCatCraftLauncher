$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$buildDir = Join-Path $root 'build'
$distDir = Join-Path $root 'dist'
$releaseDir = Join-Path $root 'release'
$stageDir = Join-Path $distDir 'NeoCatCraftLauncher-win32-x64'
$appDir = Join-Path $stageDir 'resources\app'
$electronDir = Join-Path $root 'node_modules\electron\dist'
$pythonDir = Join-Path $root '.runtime\python'
$iconJpg = Join-Path $root 'icon.jpg'
$iconIco = Join-Path $buildDir 'icon.ico'
$installerScript = Join-Path $PSScriptRoot 'installer.nsi'
$package = Get-Content -Raw -Encoding UTF8 (Join-Path $root 'package.json') | ConvertFrom-Json
$version = [string]$package.version
$outFile = Join-Path $releaseDir "NeoCatCraftLauncher-Setup-$version-x64.exe"

function Assert-ChildPath([string]$path, [string]$parent) {
  $resolvedPath = [System.IO.Path]::GetFullPath($path)
  $resolvedParent = [System.IO.Path]::GetFullPath($parent).TrimEnd('\') + '\'
  if (-not $resolvedPath.StartsWith($resolvedParent, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe output path: $resolvedPath"
  }
}

function Remove-PrivatePath([string]$path, [string]$parent) {
  if (-not (Test-Path -LiteralPath $path)) { return }
  Assert-ChildPath $path $parent
  Remove-Item -LiteralPath $path -Recurse -Force
}

function Remove-UnusedPythonPackages([string]$sitePackages) {
  if (-not (Test-Path -LiteralPath $sitePackages)) { return }
  $patterns = @(
    '^pip($|-)',
    '^websockets($|-)',
    '^watchfiles($|-)',
    '^httptools($|-)',
    '^yaml$',
    '^_yaml$',
    '^PyYAML-',
    '^pyyaml-',
    '^dotenv$',
    '^python_dotenv-'
  )
  Get-ChildItem -LiteralPath $sitePackages -Directory -Force |
    Where-Object {
      $name = $_.Name
      @($patterns | Where-Object { $name -match $_ }).Count -gt 0
    } |
    ForEach-Object { Remove-PrivatePath $_.FullName $sitePackages }
}

function New-MultiSizeIcon([string]$source, [string]$target) {
  Add-Type -AssemblyName System.Drawing
  $image = [System.Drawing.Image]::FromFile($source)
  $sizes = @(16, 24, 32, 48, 64, 128, 256)
  $images = @()
  try {
    foreach ($size in $sizes) {
      $bitmap = New-Object System.Drawing.Bitmap($size, $size)
      $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
      try {
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $graphics.DrawImage($image, 0, 0, $size, $size)
        $stream = New-Object System.IO.MemoryStream
        $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
        $images += ,$stream.ToArray()
        $stream.Dispose()
      } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
      }
    }
  } finally {
    $image.Dispose()
  }

  $headerSize = 6 + (16 * $sizes.Count)
  $offset = $headerSize
  $file = [System.IO.File]::Open($target, [System.IO.FileMode]::Create)
  $writer = New-Object System.IO.BinaryWriter($file)
  try {
    $writer.Write([UInt16]0)
    $writer.Write([UInt16]1)
    $writer.Write([UInt16]$sizes.Count)
    for ($index = 0; $index -lt $sizes.Count; $index += 1) {
      $size = $sizes[$index]
      $dimension = if ($size -ge 256) { 0 } else { $size }
      $writer.Write([byte]$dimension)
      $writer.Write([byte]$dimension)
      $writer.Write([byte]0)
      $writer.Write([byte]0)
      $writer.Write([UInt16]1)
      $writer.Write([UInt16]32)
      $writer.Write([UInt32]$images[$index].Length)
      $writer.Write([UInt32]$offset)
      $offset += $images[$index].Length
    }
    foreach ($bytes in $images) {
      $writer.Write($bytes)
    }
  } finally {
    $writer.Dispose()
    $file.Dispose()
  }
}

if (-not (Test-Path -LiteralPath (Join-Path $electronDir 'electron.exe'))) {
  throw 'Electron runtime is missing. Run npm install first.'
}
if (-not (Test-Path -LiteralPath (Join-Path $pythonDir 'python.exe'))) {
  throw 'Embedded Python is missing. Run npm run setup first.'
}

foreach ($generatedDir in @($buildDir, $distDir, $releaseDir)) {
  Assert-ChildPath $generatedDir $root
  if (Test-Path -LiteralPath $generatedDir) {
    Remove-Item -LiteralPath $generatedDir -Recurse -Force
  }
}

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
New-Item -ItemType Directory -Force -Path $distDir | Out-Null
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $stageDir | Out-Null
Copy-Item -Path (Join-Path $electronDir '*') -Destination $stageDir -Recurse -Force

# Keep only the locales used by the launcher. Electron falls back to en-US.
$localesDir = Join-Path $stageDir 'locales'
if (Test-Path -LiteralPath $localesDir) {
  Get-ChildItem -LiteralPath $localesDir -File -Filter '*.pak' |
    Where-Object { $_.Name -notin @('zh-CN.pak', 'en-US.pak') } |
    ForEach-Object { Remove-PrivatePath $_.FullName $localesDir }
}
$defaultApp = Join-Path $stageDir 'resources\default_app.asar'
Remove-PrivatePath $defaultApp (Join-Path $stageDir 'resources')

$electronExe = Join-Path $stageDir 'electron.exe'
$appExe = Join-Path $stageDir 'NeoCatCraftLauncher.exe'
Move-Item -LiteralPath $electronExe -Destination $appExe

New-Item -ItemType Directory -Force -Path $appDir | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'electron') -Destination $appDir -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $appDir 'frontend') | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'frontend\dist') -Destination (Join-Path $appDir 'frontend') -Recurse -Force
Copy-Item -LiteralPath (Join-Path $root 'backend') -Destination $appDir -Recurse -Force
Copy-Item -LiteralPath (Join-Path $root 'package.json') -Destination $appDir
Copy-Item -LiteralPath $iconJpg -Destination $appDir
$embeddedPython = Join-Path $appDir '.runtime\python'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $embeddedPython) | Out-Null
Copy-Item -LiteralPath $pythonDir -Destination $embeddedPython -Recurse -Force

# Pip, local scripts and optional uvicorn extras are not used by the packaged sidecar.
Remove-PrivatePath (Join-Path $embeddedPython 'Scripts') $embeddedPython
$embeddedSitePackages = Join-Path $embeddedPython 'Lib\site-packages'
Remove-UnusedPythonPackages $embeddedSitePackages
Get-ChildItem -LiteralPath $embeddedPython -Directory -Filter '__pycache__' -Recurse -Force |
  Sort-Object { $_.FullName.Length } -Descending |
  ForEach-Object { Remove-PrivatePath $_.FullName $embeddedPython }
Get-ChildItem -LiteralPath $embeddedPython -File -Recurse -Force |
  Where-Object { $_.Extension -in @('.pyc', '.pyo') } |
  ForEach-Object { Remove-PrivatePath $_.FullName $embeddedPython }

$stagedBackend = Join-Path $appDir 'backend'
Remove-PrivatePath (Join-Path $stagedBackend 'tests') $stagedBackend
Get-ChildItem -LiteralPath $stagedBackend -Directory -Filter '__pycache__' -Recurse -Force |
  Sort-Object { $_.FullName.Length } -Descending |
  ForEach-Object { Remove-PrivatePath $_.FullName $stagedBackend }
Get-ChildItem -LiteralPath $stagedBackend -File -Recurse -Force |
  Where-Object { $_.Extension -in @('.pyc', '.pyo') } |
  ForEach-Object { Remove-PrivatePath $_.FullName $stagedBackend }

New-MultiSizeIcon $iconJpg $iconIco

$rceditCandidates = @(
  (Join-Path $env:LOCALAPPDATA 'electron-builder\Cache\winCodeSign\winCodeSign-2.6.0\rcedit-x64.exe'),
  (Join-Path $env:LOCALAPPDATA 'electron-builder\Cache\winCodeSign\winCodeSign-2.6.0\rcedit.exe')
)
$rcedit = $rceditCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $rcedit) { throw 'rcedit executable not found in electron-builder cache.' }
& $rcedit $appExe `
  --set-icon $iconIco `
  --set-file-version $version `
  --set-product-version $version `
  --set-version-string 'ProductName' 'NeoCatCraftLauncher' `
  --set-version-string 'FileDescription' 'NeoCatCraft Minecraft Launcher' `
  --set-version-string 'CompanyName' 'NeoCatCraft'
if ($LASTEXITCODE -ne 0) { throw "rcedit failed with exit code $LASTEXITCODE" }

$makensisCandidates = @(
  (Join-Path $env:LOCALAPPDATA 'electron-builder\Cache\nsis\nsis-3.0.4.1\Bin\makensis.exe'),
  (Join-Path $env:LOCALAPPDATA 'electron-builder\Cache\nsis-3.0.4.1\Bin\makensis.exe'),
  (Join-Path $env:LOCALAPPDATA 'electron-builder\Cache\nsis-3.0.4.1\nsis-3.0.4.1-w8az6\Bin\makensis.exe')
)
$makensis = $makensisCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $makensis) {
  $command = Get-Command makensis.exe -ErrorAction SilentlyContinue
  if ($command) { $makensis = $command.Source }
}
if (-not $makensis) { throw 'makensis executable not found.' }

$compiledInstallerScript = Join-Path $buildDir 'installer.generated.nsi'
$installerText = Get-Content -Raw -Encoding UTF8 $installerScript
[System.IO.File]::WriteAllText(
  $compiledInstallerScript,
  $installerText,
  (New-Object System.Text.UTF8Encoding($true))
)

& $makensis `
  "/DAPP_VERSION=$version" `
  "/DSOURCE_DIR=$stageDir" `
  "/DOUT_FILE=$outFile" `
  "/DICON_FILE=$iconIco" `
  $compiledInstallerScript
if ($LASTEXITCODE -ne 0) { throw "NSIS failed with exit code $LASTEXITCODE" }

Write-Host "[neo] Portable folder: $stageDir"
Write-Host "[neo] Installer: $outFile"
