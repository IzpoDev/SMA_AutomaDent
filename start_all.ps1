# start_all.ps1 — Levanta todos los servicios de AutomaDent en terminales separadas
# ==============================================================================
# Uso:
#   .\start_all.ps1
#
# Servicios que levanta:
#   - MCP Server     → http://localhost:8001/mcp
#   - API REST       → http://localhost:8000   (Swagger: /docs)
#   - Bot Telegram   → Polling activo
#   - Dashboard      → http://localhost:8502
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
    "cd '$project\bot'; Write-Host 'MCP SERVER — puerto 8001' -ForegroundColor Green; `$env:PYTHONPATH = '$project\shared'; & '$project\venv\Scripts\python.exe' mcp_server.py"

Start-Sleep -Seconds 3

# 2. API REST FastAPI (puerto 8000)
Write-Host "[2/4] Iniciando API REST en puerto 8000..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$project\api'; Write-Host 'API REST — puerto 8000 | Swagger: http://localhost:8000/docs' -ForegroundColor Green; `$env:PYTHONPATH = '$project\shared'; & '$project\venv\Scripts\python.exe' -m uvicorn main:app --reload --port 8000"

Start-Sleep -Seconds 2

# 3. Dashboard Streamlit (puerto 8502)
Write-Host "[3/4] Iniciando Dashboard Streamlit en puerto 8502..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$project\dashboard'; Write-Host 'DASHBOARD — http://localhost:8502' -ForegroundColor Green; `$env:PYTHONPATH = '$project\shared'; & '$project\venv\Scripts\streamlit.exe' run app.py --server.port 8502"

Start-Sleep -Seconds 2

# 4. Bot de Telegram
Write-Host "[4/4] Iniciando Bot de Telegram..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$project\bot'; Write-Host 'BOT TELEGRAM — Polling activo' -ForegroundColor Green; `$env:PYTHONPATH = '$project\shared'; & '$project\venv\Scripts\python.exe' main.py"

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "   Todos los servicios iniciados:" -ForegroundColor Green
Write-Host ""
Write-Host "   MCP Server  → http://localhost:8001/mcp" -ForegroundColor White
Write-Host "   API REST    → http://localhost:8000" -ForegroundColor White
Write-Host "   Swagger UI  → http://localhost:8000/docs" -ForegroundColor White
Write-Host "   Dashboard   → http://localhost:8502" -ForegroundColor White
Write-Host "   Bot         → Activo en Telegram" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Para detener: cierra cada ventana de PowerShell." -ForegroundColor Gray
