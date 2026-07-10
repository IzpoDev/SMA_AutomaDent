# start_all.ps1 — Levanta todos los servicios de AutomaDent en terminales separadas
# ==============================================================================
# Uso:
#   .\start_all.ps1
# ==============================================================================

$venv = ".\venv\Scripts\python.exe"
$project = $PSScriptRoot

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   AutomaDent — Iniciando todos los servicios" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. MCP Server (puerto 8001)
Write-Host "[1/4] Iniciando MCP Server en puerto 8001..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$project'; Write-Host 'MCP SERVER — puerto 8001' -ForegroundColor Green; & '$project\venv\Scripts\python.exe' -m src.main mcp"

Start-Sleep -Seconds 3

# 2. API REST FastAPI (puerto 8000)
Write-Host "[2/4] Iniciando API REST en puerto 8000..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$project'; Write-Host 'API REST — puerto 8000 | Swagger: http://localhost:8000/docs' -ForegroundColor Green; & '$project\venv\Scripts\python.exe' -m src.main api"

Start-Sleep -Seconds 2

# 3. Dashboard Streamlit (puerto 8502)
Write-Host "[3/4] Iniciando Dashboard Streamlit en puerto 8502..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$project'; Write-Host 'DASHBOARD — http://localhost:8502' -ForegroundColor Green; & '$project\venv\Scripts\python.exe' -m src.main dashboard"

Start-Sleep -Seconds 2

# 4. Bot de Telegram
Write-Host "[4/4] Iniciando Bot de Telegram..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$project'; Write-Host 'BOT TELEGRAM — Polling activo' -ForegroundColor Green; & '$project\venv\Scripts\python.exe' -m src.main bot"

Write-Host "============================================" -ForegroundColor Green
Write-Host "   Todos los servicios iniciados." -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""


