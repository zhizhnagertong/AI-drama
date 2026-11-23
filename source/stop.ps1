# AI 漫剧智能制作平台 - 一键停止脚本
# 用法: powershell -ExecutionPolicy Bypass -File .\stop.ps1
$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root ".run.pids"

Write-Host "=== AI 漫剧平台 停止 ===" -ForegroundColor Cyan

# 1) 按 PID 文件停止
if (Test-Path $PidFile) {
    Get-Content $PidFile | ForEach-Object {
        $pid_ = $_.Trim()
        if ($pid_ -match '^\d+$') {
            $p = Get-Process -Id ([int]$pid_) -ErrorAction SilentlyContinue
            if ($p) {
                Stop-Process -Id ([int]$pid_) -Force -ErrorAction SilentlyContinue
                Write-Host "已停止进程 PID=$pid_ ($($p.ProcessName))" -ForegroundColor Yellow
            }
        }
    }
    Remove-Item $PidFile -Force
}

# 2) 兜底：按端口清理（8010=后端 uvicorn，5173=前端 vite；注意不要动 8000，可能有其他服务）
foreach ($port in 8010, 5173) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $procId = $c.OwningProcess
        $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($p) {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Write-Host "已停止端口 $port 上的进程 PID=$procId ($($p.ProcessName))" -ForegroundColor Yellow
        }
    }
}

Start-Sleep -Seconds 1
$left = Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue
$left2 = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
if (-not $left -and -not $left2) { Write-Host "=== 已全部停止，端口 8010/5173 已释放 ===" -ForegroundColor Green }
else { Write-Host "警告: 仍有端口未释放，请手动检查" -ForegroundColor Red }
