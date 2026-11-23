# AI 漫剧智能制作平台 - 一键启动脚本
# 用法: powershell -ExecutionPolicy Bypass -File .\start.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$PidFile = Join-Path $Root ".run.pids"

Write-Host "=== AI 漫剧平台 启动 ===" -ForegroundColor Cyan

# 0) 若已在运行则先停止
if (Test-Path $PidFile) {
    Write-Host "检测到已有运行实例，先停止..." -ForegroundColor Yellow
    & (Join-Path $Root "stop.ps1") | Out-Null
}

# 1) 检查依赖环境
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "未找到 python，请先安装 Python 3.10+" }
$node = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $node) { throw "未找到 node，请先安装 Node.js 18+" }

# 2) 后端虚拟环境与依赖
$venvPython = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[1/4] 创建后端虚拟环境..." -ForegroundColor Green
    & $python -m venv (Join-Path $Backend ".venv")
}
if (-not (Test-Path (Join-Path $Backend ".venv\.installed"))) {
    Write-Host "[1/4] 安装后端依赖（首次较慢）..." -ForegroundColor Green
    & $venvPython -m pip install -q --upgrade pip
    & $venvPython -m pip install -q -r (Join-Path $Backend "requirements.txt") -i https://pypi.tuna.tsinghua.edu.cn/simple
    New-Item -ItemType File -Path (Join-Path $Backend ".venv\.installed") -Force | Out-Null
}

# 3) 前端依赖
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "[2/4] 安装前端依赖（首次较慢）..." -ForegroundColor Green
    Push-Location $Frontend
    npm install --registry=https://registry.npmmirror.com
    Pop-Location
}

# 4) 启动后端 (8010，避开本机 8000 端口上的其他服务)
Write-Host "[3/4] 启动后端 http://localhost:8010 ..." -ForegroundColor Green
$backendLog = Join-Path $Backend "uvicorn.log"
$backendErr = Join-Path $Backend "uvicorn.err.log"
$backendProc = Start-Process -FilePath $venvPython -ArgumentList "-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8010" -WorkingDirectory $Backend -WindowStyle Hidden -PassThru -RedirectStandardOutput $backendLog -RedirectStandardError $backendErr
$backendProc.Id | Out-File $PidFile -Encoding ascii

# 5) 启动前端 (5173)
Write-Host "[4/4] 启动前端 http://localhost:5173 ..." -ForegroundColor Green
$npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $npmCmd) { $npmCmd = "npm" }
$frontendProc = Start-Process -FilePath $npmCmd -ArgumentList "run","dev" -WorkingDirectory $Frontend -WindowStyle Hidden -PassThru
Add-Content $PidFile $frontendProc.Id -Encoding ascii

# 6) 启动验证
Write-Host "等待服务就绪..." -NoNewline
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 2
    Write-Host "." -NoNewline
    try {
        $h = Invoke-RestMethod -Uri "http://localhost:8010/health" -TimeoutSec 3
        if ($h.status -eq "ok") { $ok = $true; break }
    } catch {}
}
Write-Host ""
if ($ok) { Write-Host "后端就绪: http://localhost:8010/health  (docs: /docs)" -ForegroundColor Green }
else { Write-Host "警告: 后端健康检查未通过，请查看日志 backend/uvicorn.log" -ForegroundColor Yellow }

$feOk = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 3 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $feOk = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if ($feOk) { Write-Host "前端就绪: http://localhost:5173" -ForegroundColor Green }
else { Write-Host "警告: 前端未就绪，请稍后手动访问 http://localhost:5173" -ForegroundColor Yellow }

Write-Host "=== 启动完成 === PID 记录: $PidFile  停止请运行 stop.ps1" -ForegroundColor Cyan
