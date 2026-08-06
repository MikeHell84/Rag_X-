#!/usr/bin/env pwsh
# start-all.ps1 - Inicia todos los servicios del sistema RAG Empresarial
# Uso: pwsh -File start-all.ps1

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  RAG Empresarial - Inicio de todos los servicios" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verificar que Docker est� corriendo
Write-Host "[1/6] Verificando Docker..." -ForegroundColor Yellow
docker info | Out-Null
Write-Host "  Docker OK" -ForegroundColor Green

# 2. Levantar la base de datos y Redis
Write-Host "[2/6] Levantando base de datos y Redis..." -ForegroundColor Yellow
docker compose up -d db redis
docker compose exec db pg_isready -U rag -d rag | Out-Null
docker compose exec redis redis-cli ping | Out-Null
Write-Host "  Base de datos y Redis OK" -ForegroundColor Green

# 3. Ejecutar migraciones y collectstatic
Write-Host "[3/6] Ejecutando migraciones y collectstatic..." -ForegroundColor Yellow
docker compose up -d migrate
# Esperar a que migrate termine
do {
    Start-Sleep -Seconds 2
    $status = docker compose ps migrate | Select-String "Exited|Up"
} while ($status -notmatch "Exited 0")
Write-Host "  Migraciones y static files OK" -ForegroundColor Green

# 4. Levantar los servicios de aplicaci�n
Write-Host "[4/6] Levantando servicios de aplicaci�n (web, worker, beat)..." -ForegroundColor Yellow
docker compose up -d web worker beat
Write-Host "  Servicios de aplicaci�n OK" -ForegroundColor Green

# 5. Levantar los servicios de observabilidad y admin
Write-Host "[5/6] Levantando servicios de admin, flower y monitoring..." -ForegroundColor Yellow
docker compose up -d admin flower
Write-Host "  Servicios de admin y flower OK" -ForegroundColor Green

# 6. Verificar que todo est� funcionando
Write-Host "[6/6] Verificando estado de todos los servicios..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

$containers = docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
Write-Host ""
Write-Host $containers

# Verificaciones de salud
Write-Host ""
$healthChecks = @(
    @{ Name = "Web (Django)"; Url = "http://localhost:8000/api/health/"; Expected = 200 },
    @{ Name = "Admin Panel"; Url = "http://localhost:3000/"; Expected = 200 },
    @{ Name = "Flower"; Url = "http://localhost:5555/"; Expected = 200 },
    @{ Name = "Static admin CSS"; Url = "http://localhost:3000/static/admin/css/base.css"; Expected = 200 },
    @{ Name = "Static admin JS"; Url = "http://localhost:3000/static/admin/js/core.js"; Expected = 200 }
)

$allHealthy = $true
foreach ($check in $healthChecks) {
    try {
        $response = Invoke-WebRequest -Uri $check.Url -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq $check.Expected) {
            Write-Host "  [OK] $($check.Name)" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] $($check.Name) - Status: $($response.StatusCode)" -ForegroundColor Yellow
            $allHealthy = $false
        }
    } catch {
        Write-Host "  [FAIL] $($check.Name) - $($_.Exception.Message)" -ForegroundColor Red
        $allHealthy = $false
    }
}

Write-Host ""
if ($allHealthy) {
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  Todos los servicios est�n funcionando!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Admin Panel:  http://localhost:3000" -ForegroundColor White
    Write-Host "  Django API:   http://localhost:8000" -ForegroundColor White
    Write-Host "  Chat SPA:     http://localhost:8000/" -ForegroundColor White
    Write-Host "  Flower:       http://localhost:5555" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "  Algunos servicios no est�n saludables" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Revisa los logs con: docker compose logs" -ForegroundColor Yellow
}
