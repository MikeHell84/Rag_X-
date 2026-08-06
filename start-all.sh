#!/bin/bash
# start-all.sh - Inicia todos los servicios del sistema RAG Empresarial
# Uso: ./start-all.sh

set -e

echo "============================================"
echo "  RAG Empresarial - Inicio de todos los servicios"
echo "============================================"
echo ""

# 1. Verificar que Docker est� corriendo
echo "[1/6] Verificando Docker..."
docker info > /dev/null 2>&1
echo "  Docker OK"

# 2. Levantar la base de datos y Redis
echo "[2/6] Levantando base de datos y Redis..."
docker compose up -d db redis
docker compose exec -T db pg_isready -U rag -d rag > /dev/null 2>&1
docker compose exec -T redis redis-cli ping > /dev/null 2>&1
echo "  Base de datos y Redis OK"

# 3. Ejecutar migraciones y collectstatic
echo "[3/6] Ejecutando migraciones y collectstatic..."
docker compose up -d migrate
# Esperar a que migrate termine
while docker compose ps migrate | grep -q "Up\|Starting"; do
    sleep 2
done
echo "  Migraciones y static files OK"

# 4. Levantar los servicios de aplicaci�n
echo "[4/6] Levantando servicios de aplicaci�n (web, worker, beat)..."
docker compose up -d web worker beat
echo "  Servicios de aplicaci�n OK"

# 5. Levantar los servicios de observabilidad y admin
echo "[5/6] Levantando servicios de admin, flower y monitoring..."
docker compose up -d admin flower
echo "  Servicios de admin y flower OK"

# 6. Verificar que todo est� funcionando
echo "[6/6] Verificando estado de todos los servicios..."
sleep 3

echo ""
docker compose ps

# Verificaciones de salud
echo ""
HEALTH_OK=true

check_health() {
    local name="$1"
    local url="$2"
    local expected="${3:-200}"
    if curl -sf -o /dev/null -w "%{http_code}" "$url" 2>/dev/null | grep -q "^${expected}$"; then
        echo "  [OK] $name"
    else
        echo "  [FAIL] $name"
        HEALTH_OK=false
    fi
}

check_health "Web (Django)" "http://localhost:8000/api/health/" 200
check_health "Admin Panel" "http://localhost:3000/" 200
check_health "Flower" "http://localhost:5555/" 200
check_health "Static admin CSS" "http://localhost:3000/static/admin/css/base.css" 200
check_health "Static admin JS" "http://localhost:3000/static/admin/js/core.js" 200

echo ""
if $HEALTH_OK; then
    echo "============================================"
    echo "  Todos los servicios est�n funcionando!"
    echo "============================================"
    echo ""
    echo "  Admin Panel:  http://localhost:3000"
    echo "  Django API:   http://localhost:8000"
    echo "  Chat SPA:     http://localhost:8000/"
    echo "  Flower:       http://localhost:5555"
    echo ""
else
    echo "============================================"
    echo "  Algunos servicios no est�n saludables"
    echo "============================================"
    echo ""
    echo "  Revisa los logs con: docker compose logs"
fi