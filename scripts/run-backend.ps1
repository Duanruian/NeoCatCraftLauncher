# NeoCatCraftLauncher - 单独启动 Python 后端（调试用）
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$candidates = @(
  $env:NEO_PYTHON,
  (Join-Path $root '.runtime\python\python.exe'),
  'python'
) | Where-Object { $_ }

$python = $null
foreach ($candidate in $candidates) {
  if ($candidate -eq 'python') { $python = $candidate; break }
  if (Test-Path $candidate) { $python = $candidate; break }
}

if (-not $python) { throw '未找到 Python，请先运行 npm run setup' }

$env:NEO_PORT = if ($env:NEO_PORT) { $env:NEO_PORT } else { '47821' }
$env:PYTHONPATH = Join-Path $root 'backend'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

Write-Host "[neo] 使用解释器: $python"
Write-Host "[neo] 后端监听: http://127.0.0.1:$($env:NEO_PORT)"

& $python (Join-Path $root 'backend\main.py')
