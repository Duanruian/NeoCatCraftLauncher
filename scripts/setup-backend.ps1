# NeoCatCraftLauncher - 一次性后端环境准备
# 全部下载走国内镜像：Python 使用 npmmirror，pip 使用清华 PyPI 镜像
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root '.runtime'
$pythonDir = Join-Path $runtime 'python'
$pythonExe = Join-Path $pythonDir 'python.exe'
$pythonVersion = '3.12.10'
$zipName = "python-$pythonVersion-embed-amd64.zip"
$pythonMirror = 'https://registry.npmmirror.com/-/binary/python'
$pipIndex = 'https://pypi.tuna.tsinghua.edu.cn/simple'
$pipTrusted = 'pypi.tuna.tsinghua.edu.cn'

Write-Host "[neo] 项目根目录: $root"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null

if (-not (Test-Path $pythonExe)) {
  Write-Host "[neo] 下载便携 Python $pythonVersion（npmmirror 镜像）…"
  $archive = Join-Path $runtime $zipName
  $url = "$pythonMirror/$pythonVersion/$zipName"
  Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing

  Write-Host "[neo] 解压到 .runtime\python …"
  if (Test-Path $pythonDir) { Remove-Item -Recurse -Force $pythonDir }
  Expand-Archive -Path $archive -DestinationPath $pythonDir -Force
  Remove-Item -Force $archive

  $pth = Get-ChildItem -Path $pythonDir -Filter 'python*._pth' | Select-Object -First 1
  if ($pth) {
    $content = @(
      'python312.zip',
      '.',
      'Lib\site-packages',
      'import site'
    ) -join "`r`n"
    [System.IO.File]::WriteAllText($pth.FullName, $content, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "[neo] 已启用 site-packages: $($pth.Name)"
  }
} else {
  Write-Host "[neo] 便携 Python 已存在，跳过下载"
}

$pipConfig = Join-Path $runtime 'pip.ini'
$pipConfigText = @"
[global]
index-url = $pipIndex
trusted-host = $pipTrusted
timeout = 60
"@
[System.IO.File]::WriteAllText($pipConfig, $pipConfigText, (New-Object System.Text.UTF8Encoding($false)))
$env:PIP_CONFIG_FILE = $pipConfig
Write-Host "[neo] pip 镜像配置: $pipConfig"

& $pythonExe -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host "[neo] 引导安装 pip …"
  $getPip = Join-Path $runtime 'get-pip.py'
  $sources = @(
    'https://mirrors.aliyun.com/pypi/get-pip.py',
    'https://bootstrap.pypa.io/get-pip.py'
  )
  $downloaded = $false
  foreach ($source in $sources) {
    try {
      Invoke-WebRequest -Uri $source -OutFile $getPip -UseBasicParsing
      $downloaded = $true
      break
    } catch {
      Write-Host "[neo] 下载失败，尝试下一个源: $source"
    }
  }
  if (-not $downloaded) { throw '无法下载 get-pip.py，请检查网络或代理设置' }
  & $pythonExe $getPip --no-warn-script-location
  Remove-Item -Force $getPip
}

Write-Host "[neo] 安装后端依赖（清华镜像）…"
& $pythonExe -m pip install --upgrade pip -i $pipIndex --trusted-host $pipTrusted
& $pythonExe -m pip install -r (Join-Path $root 'backend\requirements.txt') -i $pipIndex --trusted-host $pipTrusted
if ($LASTEXITCODE -ne 0) { throw '后端依赖安装失败' }

& $pythonExe -c "import fastapi, uvicorn, httpx, minecraft_launcher_lib, mcauth3; print('[neo] 依赖自检通过')"
if ($LASTEXITCODE -ne 0) { throw '后端依赖自检失败' }

Write-Host '[neo] 环境准备完成，可以运行 npm start'
