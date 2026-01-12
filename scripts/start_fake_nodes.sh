#!/bin/bash
#
# Iris Fake Nodes Startup Script
#
# Inicia multiples fake nodes con diferentes modelos de OpenRouter.
# Cada fake node actua como un nodo normal pero llama a OpenRouter
# en lugar de LM Studio.
#
# Los fake nodes tienen penalizacion para que las tareas vayan
# preferentemente a nodos reales:
# - TPS bajo reportado (5.0 vs 20+ de nodos reales)
# - Load artificial alto (3) en heartbeats
#
# Uso:
#   ./scripts/start_fake_nodes.sh
#
# El script carga automaticamente el archivo .env del directorio raiz.
#
# Variables de entorno requeridas (en .env o exportadas):
#   OPENROUTER_API_KEY - API key de OpenRouter
#   IRIS_ACCOUNT_KEY   - Account key para los fake nodes
#
# Variables opcionales:
#   COORDINATOR_URL    - URL del coordinator (default: ws://168.119.10.189:8000/nodes/connect)
#   FAKE_NODE_TPS      - TPS reportado (default: 5.0)
#   FAKE_NODE_LOAD     - Load artificial (default: 3)
#

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Obtener directorio raiz del repo (donde esta el .env)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Cargar .env si existe
ENV_FILE="$REPO_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    echo -e "${BLUE}Loading .env from:${NC} $ENV_FILE"
    # Exportar variables del .env (ignorando comentarios y lineas vacias)
    set -a
    source "$ENV_FILE"
    set +a
else
    echo -e "${YELLOW}Warning: .env file not found at $ENV_FILE${NC}"
fi

# Verificar variables requeridas
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo -e "${RED}ERROR: OPENROUTER_API_KEY not set${NC}"
    echo "Get your API key from: https://openrouter.ai/keys"
    echo "Then: export OPENROUTER_API_KEY=\"sk-or-v1-...\""
    exit 1
fi

if [ -z "$IRIS_ACCOUNT_KEY" ]; then
    echo -e "${RED}ERROR: IRIS_ACCOUNT_KEY not set${NC}"
    echo "Generate one with: iris account generate"
    echo "Then: export IRIS_ACCOUNT_KEY=\"1234 5678 9012 3456\""
    exit 1
fi

# Defaults
COORDINATOR_URL="${COORDINATOR_URL:-ws://168.119.10.189:8000/nodes/connect}"
FAKE_NODE_TPS="${FAKE_NODE_TPS:-5.0}"
FAKE_NODE_LOAD="${FAKE_NODE_LOAD:-3}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   IRIS FAKE NODES STARTUP${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Coordinator:${NC} $COORDINATOR_URL"
echo -e "${YELLOW}Reported TPS:${NC} $FAKE_NODE_TPS (penalty: low)"
echo -e "${YELLOW}Artificial Load:${NC} $FAKE_NODE_LOAD (penalty)"
echo ""

# Array de modelos a iniciar
# Formato: "NODE_ID:MODEL:TPS:PARAMS"
MODELS=(
    "openrouter-qwen-72b:qwen/qwen-2.5-72b-instruct:5.0:72.0"
    # "openrouter-llama-70b:meta-llama/llama-3.1-70b-instruct:4.0:70.0"
    # "openrouter-deepseek:deepseek/deepseek-chat:3.0:685.0"
)

# PIDs de los procesos iniciados
PIDS=()

# Funcion para limpiar al salir
cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping fake nodes...${NC}"
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait
    echo -e "${GREEN}All fake nodes stopped${NC}"
}

trap cleanup EXIT INT TERM

# Iniciar cada fake node
for model_config in "${MODELS[@]}"; do
    IFS=':' read -r NODE_ID MODEL TPS PARAMS <<< "$model_config"

    echo -e "${GREEN}Starting:${NC} $NODE_ID"
    echo -e "  Model: $MODEL"
    echo -e "  TPS: $TPS, Params: ${PARAMS}B"

    NODE_ID="$NODE_ID" \
    OPENROUTER_MODEL="$MODEL" \
    COORDINATOR_URL="$COORDINATOR_URL" \
    FAKE_NODE_TPS="$TPS" \
    FAKE_NODE_ARTIFICIAL_LOAD="$FAKE_NODE_LOAD" \
    FAKE_NODE_PARAMS="$PARAMS" \
    python -m node_agent.node_agent_openrouter &

    PIDS+=($!)

    # Esperar un poco entre inicios
    sleep 2
done

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}${#PIDS[@]} fake node(s) started${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all fake nodes${NC}"
echo ""

# Esperar a que terminen
wait
