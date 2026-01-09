#!/bin/bash
# =============================================================================
# Iris Network - Node Agent Installer
#
# Instalación con un solo comando:
#   curl -fsSL https://iris.network/install.sh | bash
#
# O con wget:
#   wget -qO- https://iris.network/install.sh | bash
# =============================================================================

set -e

VERSION="1.0.0"
COORDINATOR_IP="168.119.10.189"
COORDINATOR_PORT="8000"
COORDINATOR_URL="http://${COORDINATOR_IP}:${COORDINATOR_PORT}"
COORDINATOR_WS="ws://${COORDINATOR_IP}:${COORDINATOR_PORT}/nodes/connect"
INSTALL_DIR="$HOME/.iris"
BIN_NAME="iris-node"

# Download URL from coordinator server
DOWNLOAD_BASE="${COORDINATOR_URL}/downloads"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# =============================================================================
# Helper Functions
# =============================================================================

print_banner() {
    clear
    echo ""
    echo -e "${CYAN}"
    echo "  ██╗██████╗ ██╗███████╗    ███╗   ██╗███████╗████████╗██╗    ██╗ ██████╗ ██████╗ ██╗  ██╗"
    echo "  ██║██╔══██╗██║██╔════╝    ████╗  ██║██╔════╝╚══██╔══╝██║    ██║██╔═══██╗██╔══██╗██║ ██╔╝"
    echo "  ██║██████╔╝██║███████╗    ██╔██╗ ██║█████╗     ██║   ██║ █╗ ██║██║   ██║██████╔╝█████╔╝ "
    echo "  ██║██╔══██╗██║╚════██║    ██║╚██╗██║██╔══╝     ██║   ██║███╗██║██║   ██║██╔══██╗██╔═██╗ "
    echo "  ██║██║  ██║██║███████║    ██║ ╚████║███████╗   ██║   ╚███╔███╔╝╚██████╔╝██║  ██║██║  ██╗"
    echo "  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝    ╚═╝  ╚═══╝╚══════╝   ╚═╝    ╚══╝╚══╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝"
    echo -e "${NC}"
    echo -e "${BOLD}  Distributed AI Inference Network - Node Installer v${VERSION}${NC}"
    echo ""
    echo "  ─────────────────────────────────────────────────────────────────────────"
    echo ""
}

print_step() {
    echo -e "\n${BLUE}▶${NC} ${BOLD}$1${NC}"
}

print_success() {
    echo -e "  ${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "  ${RED}✗${NC} $1"
}

print_warning() {
    echo -e "  ${YELLOW}!${NC} $1"
}

print_info() {
    echo -e "  ${CYAN}ℹ${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# HTTP request helper
http_request() {
    local method="$1"
    local url="$2"
    local data="$3"
    local auth="$4"

    local curl_opts="-s -w \n%{http_code}"

    if [ -n "$auth" ]; then
        curl_opts="$curl_opts -H \"Authorization: Bearer $auth\""
    fi

    if [ "$method" = "POST" ]; then
        curl_opts="$curl_opts -X POST -H \"Content-Type: application/json\""
        if [ -n "$data" ]; then
            curl_opts="$curl_opts -d '$data'"
        fi
    fi

    eval "curl $curl_opts \"$url\"" 2>/dev/null
}

# =============================================================================
# Platform Detection
# =============================================================================

detect_platform() {
    print_step "Detectando plataforma..."

    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)

    case "$ARCH" in
        x86_64|amd64) ARCH="amd64" ;;
        arm64|aarch64) ARCH="arm64" ;;
        *)
            print_error "Arquitectura no soportada: $ARCH"
            exit 1
            ;;
    esac

    case "$OS" in
        linux) PLATFORM="linux-$ARCH" ;;
        darwin) PLATFORM="darwin-$ARCH" ;;
        *)
            print_error "Sistema operativo no soportado: $OS"
            exit 1
            ;;
    esac

    print_success "Plataforma: $PLATFORM"
}

# =============================================================================
# Connectivity Check
# =============================================================================

check_coordinator() {
    print_step "Verificando conexión al coordinador..."

    local response
    response=$(curl -s --connect-timeout 5 "${COORDINATOR_URL}/health" 2>/dev/null)

    if echo "$response" | grep -q '"status":"healthy"'; then
        local nodes=$(echo "$response" | grep -o '"nodes_connected":[0-9]*' | cut -d: -f2)
        print_success "Coordinador activo ($nodes nodos conectados)"
        return 0
    else
        print_error "No se puede conectar al coordinador en ${COORDINATOR_IP}:${COORDINATOR_PORT}"
        print_info "Verifica tu conexión a internet"
        exit 1
    fi
}

# =============================================================================
# Node.js Check
# =============================================================================

check_nodejs() {
    print_step "Verificando Node.js..."

    if command_exists node; then
        local node_version=$(node --version 2>/dev/null)
        local major_version=$(echo "$node_version" | sed 's/v//' | cut -d. -f1)

        if [ "$major_version" -ge 16 ]; then
            print_success "Node.js $node_version detectado"
            NODEJS_AVAILABLE=true
            return 0
        else
            print_warning "Node.js $node_version es muy antiguo (se requiere v16+)"
        fi
    fi

    print_warning "Node.js no detectado"
    echo ""
    echo -e "  ${YELLOW}Node.js es necesario para el dashboard (TUI).${NC}"
    echo -e "  ${CYAN}Opciones de instalación:${NC}"
    echo ""
    echo -e "  ${BOLD}macOS:${NC}"
    echo -e "    brew install node"
    echo ""
    echo -e "  ${BOLD}Linux (Ubuntu/Debian):${NC}"
    echo -e "    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
    echo -e "    sudo apt-get install -y nodejs"
    echo ""
    echo -e "  ${BOLD}Linux (otras distros):${NC}"
    echo -e "    https://nodejs.org/en/download/"
    echo ""

    read -p "  ¿Intentar instalar Node.js automáticamente? [S/n]: " install_node
    if [[ ! "$install_node" =~ ^[Nn]$ ]]; then
        install_nodejs
    else
        print_warning "TUI no estará disponible sin Node.js"
        NODEJS_AVAILABLE=false
    fi
}

install_nodejs() {
    print_info "Instalando Node.js..."

    if [ "$OS" = "darwin" ]; then
        # macOS - use Homebrew
        if command_exists brew; then
            brew install node
            if command_exists node; then
                print_success "Node.js instalado via Homebrew"
                NODEJS_AVAILABLE=true
                return 0
            fi
        else
            print_warning "Homebrew no encontrado. Instala Node.js manualmente."
            NODEJS_AVAILABLE=false
            return 1
        fi
    elif [ "$OS" = "linux" ]; then
        # Linux - use NodeSource
        if command_exists apt-get; then
            print_info "Instalando via NodeSource (requiere sudo)..."
            curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - 2>/dev/null
            sudo apt-get install -y nodejs 2>/dev/null
            if command_exists node; then
                print_success "Node.js instalado via apt"
                NODEJS_AVAILABLE=true
                return 0
            fi
        elif command_exists dnf; then
            sudo dnf install -y nodejs 2>/dev/null
            if command_exists node; then
                print_success "Node.js instalado via dnf"
                NODEJS_AVAILABLE=true
                return 0
            fi
        elif command_exists yum; then
            curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash - 2>/dev/null
            sudo yum install -y nodejs 2>/dev/null
            if command_exists node; then
                print_success "Node.js instalado via yum"
                NODEJS_AVAILABLE=true
                return 0
            fi
        fi
    fi

    print_error "No se pudo instalar Node.js automáticamente"
    print_info "Instala manualmente desde https://nodejs.org"
    NODEJS_AVAILABLE=false
    return 1
}

# =============================================================================
# LM Studio Check
# =============================================================================

check_lmstudio() {
    print_step "Verificando LM Studio..."

    local lmstudio_url="${LMSTUDIO_URL:-http://localhost:1234/v1}"
    local response
    response=$(curl -s --connect-timeout 3 "${lmstudio_url}/models" 2>/dev/null)

    if echo "$response" | grep -q '"data"'; then
        local model=$(echo "$response" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
        print_success "LM Studio activo - Modelo: ${model:-desconocido}"
        DETECTED_LMSTUDIO_URL="$lmstudio_url"
        return 0
    else
        print_warning "LM Studio no detectado en $lmstudio_url"
        echo ""
        echo -e "  ${YELLOW}LM Studio es necesario para ejecutar inferencias.${NC}"
        echo -e "  ${CYAN}1.${NC} Descarga LM Studio: https://lmstudio.ai"
        echo -e "  ${CYAN}2.${NC} Carga un modelo"
        echo -e "  ${CYAN}3.${NC} Inicia el servidor local (puerto 1234)"
        echo ""
        read -p "  ¿Continuar sin LM Studio? [s/N]: " continue_without
        if [[ ! "$continue_without" =~ ^[SsYy]$ ]]; then
            print_info "Instala LM Studio y vuelve a ejecutar el instalador"
            exit 0
        fi
        DETECTED_LMSTUDIO_URL="$lmstudio_url"
        return 1
    fi
}

# =============================================================================
# User Authentication
# =============================================================================

authenticate_user() {
    print_step "Autenticación de usuario"
    echo ""
    echo -e "  ${CYAN}¿Ya tienes cuenta en Iris Network?${NC}"
    echo -e "  ${BOLD}1)${NC} Sí, iniciar sesión"
    echo -e "  ${BOLD}2)${NC} No, crear cuenta nueva"
    echo ""
    read -p "  Selecciona [1/2]: " auth_choice

    case "$auth_choice" in
        1) login_user ;;
        2) register_user ;;
        *)
            print_error "Opción inválida"
            authenticate_user
            ;;
    esac
}

register_user() {
    echo ""
    print_info "Registro de nueva cuenta"
    echo ""

    read -p "  Email: " user_email
    read -s -p "  Contraseña: " user_password
    echo ""
    read -s -p "  Confirmar contraseña: " user_password_confirm
    echo ""

    if [ "$user_password" != "$user_password_confirm" ]; then
        print_error "Las contraseñas no coinciden"
        register_user
        return
    fi

    print_info "Registrando usuario..."

    local response
    response=$(curl -s -X POST "${COORDINATOR_URL}/auth/register" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$user_email\", \"password\": \"$user_password\"}" 2>/dev/null)

    if echo "$response" | grep -q '"id"'; then
        print_success "Cuenta creada exitosamente"
        USER_EMAIL="$user_email"
        USER_PASSWORD="$user_password"
        do_login
    else
        local error=$(echo "$response" | grep -o '"detail":"[^"]*"' | cut -d'"' -f4)
        print_error "Error al registrar: ${error:-Error desconocido}"
        echo ""
        read -p "  ¿Intentar iniciar sesión en su lugar? [S/n]: " try_login
        if [[ ! "$try_login" =~ ^[Nn]$ ]]; then
            USER_EMAIL="$user_email"
            USER_PASSWORD="$user_password"
            do_login
        else
            exit 1
        fi
    fi
}

login_user() {
    echo ""
    print_info "Inicio de sesión"
    echo ""

    read -p "  Email: " user_email
    read -s -p "  Contraseña: " user_password
    echo ""

    USER_EMAIL="$user_email"
    USER_PASSWORD="$user_password"
    do_login
}

do_login() {
    print_info "Iniciando sesión..."

    local response
    response=$(curl -s -X POST "${COORDINATOR_URL}/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$USER_EMAIL\", \"password\": \"$USER_PASSWORD\"}" 2>/dev/null)

    if echo "$response" | grep -q '"access_token"'; then
        AUTH_TOKEN=$(echo "$response" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

        # Save token and credentials for TUI/CLI use
        mkdir -p "$INSTALL_DIR"
        echo "$AUTH_TOKEN" > "$INSTALL_DIR/token"
        print_success "Sesión iniciada correctamente"
        print_success "Token guardado en $INSTALL_DIR/token"
    else
        local error=$(echo "$response" | grep -o '"detail":"[^"]*"' | cut -d'"' -f4)
        print_error "Error al iniciar sesión: ${error:-Credenciales inválidas}"
        echo ""
        read -p "  ¿Reintentar? [S/n]: " retry
        if [[ ! "$retry" =~ ^[Nn]$ ]]; then
            login_user
        else
            exit 1
        fi
    fi
}

# =============================================================================
# Token Generation
# =============================================================================

generate_enrollment_token() {
    print_step "Generando token de enrollment..."

    local node_label="node-$(hostname | tr '[:upper:]' '[:lower:]' | tr '.' '-' | cut -c1-15)-$(date +%s | tail -c 5)"

    local response
    response=$(curl -s -X POST "${COORDINATOR_URL}/admin/tokens/generate" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $AUTH_TOKEN" \
        -d "{\"label\": \"$node_label\"}" 2>/dev/null)

    if echo "$response" | grep -q '"token"'; then
        ENROLLMENT_TOKEN=$(echo "$response" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
        print_success "Token generado: ${node_label}"
    else
        local error=$(echo "$response" | grep -o '"detail":"[^"]*"' | cut -d'"' -f4)
        print_error "Error al generar token: ${error:-Error desconocido}"
        exit 1
    fi
}

# =============================================================================
# Binary Download
# =============================================================================

download_binary() {
    print_step "Descargando Iris Node Agent..."

    DOWNLOAD_URL="${DOWNLOAD_BASE}/iris-node-${PLATFORM}"

    mkdir -p "$INSTALL_DIR/bin"
    mkdir -p "$INSTALL_DIR/data"
    mkdir -p "$INSTALL_DIR/logs"

    print_info "URL: $DOWNLOAD_URL"

    if curl -fsSL "$DOWNLOAD_URL" -o "$INSTALL_DIR/bin/$BIN_NAME" 2>/dev/null; then
        chmod +x "$INSTALL_DIR/bin/$BIN_NAME"
        print_success "Binario instalado en $INSTALL_DIR/bin/$BIN_NAME"
    else
        print_warning "No se pudo descargar el binario pre-compilado"
        print_info "Creando wrapper script para Python..."
        PYTHON_MODE=true
        create_python_wrapper
    fi
}

create_python_wrapper() {
    # Find Python with correct priority
    # 1. conda/miniconda (usually has packages)
    # 2. homebrew python
    # 3. system python
    PYTHON_BIN=""
    PYTHON_PATH=""

    # Check for conda Python first
    if [ -f "$HOME/miniconda3/bin/python3" ]; then
        PYTHON_PATH="$HOME/miniconda3/bin/python3"
        PYTHON_BIN="$PYTHON_PATH"
    elif [ -f "$HOME/anaconda3/bin/python3" ]; then
        PYTHON_PATH="$HOME/anaconda3/bin/python3"
        PYTHON_BIN="$PYTHON_PATH"
    elif [ -f "/opt/homebrew/bin/python3" ]; then
        PYTHON_PATH="/opt/homebrew/bin/python3"
        PYTHON_BIN="$PYTHON_PATH"
    elif [ -f "/usr/local/bin/python3" ]; then
        PYTHON_PATH="/usr/local/bin/python3"
        PYTHON_BIN="$PYTHON_PATH"
    elif command_exists python3; then
        PYTHON_PATH=$(which python3)
        PYTHON_BIN="python3"
    elif command_exists python; then
        PYTHON_PATH=$(which python)
        PYTHON_BIN="python"
    else
        print_error "Python no encontrado. Instala Python 3.9+ primero."
        exit 1
    fi

    print_info "Usando Python: $PYTHON_PATH"

    # Install dependencies using the found Python
    print_info "Instalando dependencias de Python..."
    $PYTHON_BIN -m pip install --quiet --upgrade pip 2>/dev/null || true
    $PYTHON_BIN -m pip install --quiet pyyaml httpx websockets structlog cryptography pydantic typer rich 2>/dev/null || true

    # Create iris-node wrapper script
    cat > "$INSTALL_DIR/bin/$BIN_NAME" << WRAPPER_EOF
#!${PYTHON_PATH}
"""Iris Node Agent Wrapper"""
import sys
import os

# Add project to path if running from source
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.expanduser("~/Documents/clubai")
if os.path.exists(project_root):
    sys.path.insert(0, project_root)

# Try to import and run
try:
    from node_agent.standalone_main import main
    main()
except ImportError as e:
    print(f"Error: Could not import node_agent module: {e}")
    print("\\nMake sure you have the Iris source code at ~/Documents/clubai")
    print("Or install the package: pip install iris-node")
    sys.exit(1)
WRAPPER_EOF

    chmod +x "$INSTALL_DIR/bin/$BIN_NAME"
    print_success "iris-node instalado en $INSTALL_DIR/bin/$BIN_NAME"
}

# =============================================================================
# Node.js TUI Installation
# =============================================================================

install_nodejs_tui() {
    print_step "Instalando dashboard (TUI)..."

    if [ "$NODEJS_AVAILABLE" != true ]; then
        print_warning "Node.js no disponible, saltando instalación de TUI"
        return 1
    fi

    TUI_DIR="$INSTALL_DIR/tui"
    mkdir -p "$TUI_DIR"

    # Check if source exists locally
    TUI_SOURCE="$HOME/Documents/clubai/client/tui-node"

    if [ -d "$TUI_SOURCE" ]; then
        print_info "Copiando TUI desde fuente local..."
        cp -r "$TUI_SOURCE/src" "$TUI_DIR/"
        cp "$TUI_SOURCE/package.json" "$TUI_DIR/"
    else
        print_info "Descargando TUI desde servidor..."
        # Download from coordinator (fallback)
        if ! curl -fsSL "${COORDINATOR_URL}/downloads/tui-node.tar.gz" -o "/tmp/tui-node.tar.gz" 2>/dev/null; then
            print_warning "No se pudo descargar TUI"
            print_info "Clona el repositorio: git clone https://github.com/iris-network/client ~/Documents/clubai"
            return 1
        fi
        tar -xzf "/tmp/tui-node.tar.gz" -C "$TUI_DIR"
        rm -f "/tmp/tui-node.tar.gz"
    fi

    # Install npm dependencies
    print_info "Instalando dependencias de Node.js..."
    cd "$TUI_DIR"
    npm install --quiet 2>/dev/null

    if [ $? -ne 0 ]; then
        print_warning "Error instalando dependencias npm"
        return 1
    fi

    print_success "Dependencias de TUI instaladas"

    # Create iris wrapper script (Node.js TUI)
    cat > "$INSTALL_DIR/bin/iris" << 'WRAPPER_EOF'
#!/bin/bash
# Iris Network - Dashboard & CLI Launcher

IRIS_DIR="$HOME/.iris"
TUI_DIR="$IRIS_DIR/tui"

# Check for TUI mode (no args or 'tui' arg)
if [ $# -eq 0 ] || [ "$1" = "tui" ]; then
    # Launch Node.js TUI
    if [ -d "$TUI_DIR" ] && command -v node >/dev/null 2>&1; then
        exec node "$TUI_DIR/src/index.js"
    else
        echo "Error: TUI not installed or Node.js not available"
        echo "Run the installer again to set up the TUI"
        exit 1
    fi
else
    # Pass to Python CLI
    PYTHON_BIN=""
    if [ -f "$HOME/miniconda3/bin/python3" ]; then
        PYTHON_BIN="$HOME/miniconda3/bin/python3"
    elif [ -f "$HOME/anaconda3/bin/python3" ]; then
        PYTHON_BIN="$HOME/anaconda3/bin/python3"
    elif [ -f "/opt/homebrew/bin/python3" ]; then
        PYTHON_BIN="/opt/homebrew/bin/python3"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="python"
    else
        echo "Error: Python not found"
        exit 1
    fi

    PROJECT_ROOT="$HOME/Documents/clubai"
    if [ -d "$PROJECT_ROOT" ]; then
        export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
    fi

    exec $PYTHON_BIN -m client.cli "$@"
fi
WRAPPER_EOF

    chmod +x "$INSTALL_DIR/bin/iris"
    print_success "iris (TUI/CLI) instalado en $INSTALL_DIR/bin/iris"
}

# =============================================================================
# Configuration
# =============================================================================

configure_node() {
    print_step "Configurando nodo..."

    # Generate node ID
    NODE_ID="node-$(hostname | tr '[:upper:]' '[:lower:]' | tr '.' '-' | cut -c1-20)-$(date +%s | tail -c 5)"

    # LM Studio URL
    LMSTUDIO_URL="${DETECTED_LMSTUDIO_URL:-http://localhost:1234/v1}"

    # Create config file
    cat > "$INSTALL_DIR/config.yaml" << EOF
# Iris Network - Node Configuration
# Generated: $(date -Iseconds)

node_id: "$NODE_ID"
coordinator_url: "$COORDINATOR_WS"
lmstudio_url: "$LMSTUDIO_URL"
enrollment_token: "$ENROLLMENT_TOKEN"
data_dir: "$INSTALL_DIR/data"
log_dir: "$INSTALL_DIR/logs"
EOF

    print_success "Configuración guardada en $INSTALL_DIR/config.yaml"
    print_success "Node ID: $NODE_ID"
}

# =============================================================================
# Service Installation
# =============================================================================

ask_autostart() {
    echo ""
    read -p "  ¿Iniciar automáticamente con el sistema? [S/n]: " autostart
    if [[ ! "$autostart" =~ ^[Nn]$ ]]; then
        ENABLE_AUTOSTART=true
    else
        ENABLE_AUTOSTART=false
    fi
}

install_systemd_service() {
    print_step "Instalando servicio systemd..."

    SERVICE_FILE="/etc/systemd/system/iris-node.service"

    if [ "$(id -u)" -ne 0 ]; then
        if ! command_exists sudo; then
            print_warning "Se requiere sudo para instalar el servicio"
            return 1
        fi
        SUDO="sudo"
    else
        SUDO=""
    fi

    $SUDO tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Iris Network Node Agent
Documentation=https://iris.network/docs
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
ExecStart=$INSTALL_DIR/bin/$BIN_NAME --config $INSTALL_DIR/config.yaml
Restart=always
RestartSec=10
StandardOutput=append:$INSTALL_DIR/logs/node.log
StandardError=append:$INSTALL_DIR/logs/node.log

[Install]
WantedBy=multi-user.target
EOF

    $SUDO systemctl daemon-reload
    $SUDO systemctl enable iris-node
    $SUDO systemctl start iris-node

    print_success "Servicio systemd instalado y activado"
}

install_launchd_service() {
    print_step "Instalando servicio launchd..."

    PLIST_DIR="$HOME/Library/LaunchAgents"
    PLIST_FILE="$PLIST_DIR/network.iris.node.plist"

    mkdir -p "$PLIST_DIR"

    cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>network.iris.node</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/bin/$BIN_NAME</string>
        <string>--config</string>
        <string>$INSTALL_DIR/config.yaml</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$INSTALL_DIR/logs/node.log</string>
    <key>StandardErrorPath</key>
    <string>$INSTALL_DIR/logs/node.log</string>
</dict>
</plist>
EOF

    launchctl load "$PLIST_FILE" 2>/dev/null || true

    print_success "Servicio launchd instalado y activado"
}

# =============================================================================
# PATH Setup
# =============================================================================

setup_path() {
    print_step "Configurando PATH..."

    # Try to create symlinks in /usr/local/bin
    if [ -d "/usr/local/bin" ]; then
        if [ -w "/usr/local/bin" ]; then
            ln -sf "$INSTALL_DIR/bin/$BIN_NAME" "/usr/local/bin/$BIN_NAME"
            ln -sf "$INSTALL_DIR/bin/iris" "/usr/local/bin/iris"
            print_success "Symlinks creados en /usr/local/bin"
            PATH_CONFIGURED=true
            return
        elif command_exists sudo; then
            print_info "Se requiere sudo para crear symlinks en /usr/local/bin"
            if sudo ln -sf "$INSTALL_DIR/bin/$BIN_NAME" "/usr/local/bin/$BIN_NAME" 2>/dev/null && \
               sudo ln -sf "$INSTALL_DIR/bin/iris" "/usr/local/bin/iris" 2>/dev/null; then
                print_success "Symlinks creados en /usr/local/bin"
                PATH_CONFIGURED=true
                return
            fi
        fi
    fi

    # Fallback: Add to shell config
    print_info "Agregando ~/.iris/bin al PATH..."

    SHELL_CONFIG=""
    if [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
        SHELL_CONFIG="$HOME/.zshrc"
    elif [ -n "$BASH_VERSION" ] || [ -f "$HOME/.bashrc" ]; then
        SHELL_CONFIG="$HOME/.bashrc"
    elif [ -f "$HOME/.profile" ]; then
        SHELL_CONFIG="$HOME/.profile"
    fi

    if [ -n "$SHELL_CONFIG" ]; then
        PATH_LINE='export PATH="$HOME/.iris/bin:$PATH"'

        # Check if already in config
        if ! grep -q ".iris/bin" "$SHELL_CONFIG" 2>/dev/null; then
            echo "" >> "$SHELL_CONFIG"
            echo "# Iris Network Node Agent" >> "$SHELL_CONFIG"
            echo "$PATH_LINE" >> "$SHELL_CONFIG"
            print_success "PATH agregado a $SHELL_CONFIG"
            print_warning "Ejecuta 'source $SHELL_CONFIG' o abre una nueva terminal"
        else
            print_success "PATH ya configurado en $SHELL_CONFIG"
        fi
        PATH_CONFIGURED=true
    else
        print_warning "No se pudo configurar el PATH automáticamente"
        print_info "Agrega manualmente: export PATH=\"\$HOME/.iris/bin:\$PATH\""
        PATH_CONFIGURED=false
    fi
}

# =============================================================================
# Completion
# =============================================================================

print_completion() {
    echo ""
    echo -e "${GREEN}"
    echo "  ╔═══════════════════════════════════════════════════════════════════╗"
    echo "  ║                    ¡Instalación Completada!                       ║"
    echo "  ╚═══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo -e "  ${BOLD}Tu nodo está configurado:${NC}"
    echo -e "    Node ID:     ${CYAN}$NODE_ID${NC}"
    echo -e "    Directorio:  ${CYAN}$INSTALL_DIR${NC}"
    echo ""
    echo -e "  ${BOLD}Comandos disponibles:${NC}"
    echo -e "    ${CYAN}iris${NC}           Abrir dashboard interactivo (TUI)"
    echo -e "    ${CYAN}iris-node${NC}      Iniciar el nodo"
    echo ""
    echo -e "  ${BOLD}Otros comandos:${NC}"
    echo -e "    ${CYAN}iris stats${NC}     Ver estadísticas de la red"
    echo -e "    ${CYAN}iris nodes${NC}     Ver nodos activos"
    echo -e "    ${CYAN}iris ask${NC}       Enviar prompt de inferencia"
    echo -e "    ${CYAN}iris --help${NC}    Ver todos los comandos"
    echo ""

    if [ "$OS" = "linux" ]; then
        echo -e "  ${BOLD}Control del servicio:${NC}"
        echo -e "    ${CYAN}Estado:${NC}     systemctl status iris-node"
        echo -e "    ${CYAN}Reiniciar:${NC}  sudo systemctl restart iris-node"
        echo -e "    ${CYAN}Detener:${NC}    sudo systemctl stop iris-node"
        echo ""
    elif [ "$OS" = "darwin" ]; then
        echo -e "  ${BOLD}Control del servicio:${NC}"
        echo -e "    ${CYAN}Estado:${NC}     launchctl list | grep iris"
        echo -e "    ${CYAN}Detener:${NC}    launchctl unload ~/Library/LaunchAgents/network.iris.node.plist"
        echo ""
    fi

    # Remind about new terminal if PATH was added to shell config
    if [ "$PATH_CONFIGURED" != true ]; then
        echo -e "  ${YELLOW}Nota: Abre una nueva terminal para usar los comandos${NC}"
        echo ""
    fi

    echo -e "  ${GREEN}¡Tu nodo ahora es parte de Iris Network!${NC}"
    echo ""
}

# =============================================================================
# Uninstall
# =============================================================================

uninstall_node() {
    print_banner
    print_step "Desinstalando Iris Node Agent..."

    echo ""
    echo -e "  ${YELLOW}¡ADVERTENCIA!${NC}"
    echo -e "  Esta acción eliminará:"
    echo -e "    • El binario de iris-node"
    echo -e "    • Toda la configuración"
    echo -e "    • Todos los datos y logs"
    echo -e "    • El servicio del sistema"
    echo -e "    • El nodo desaparecerá de la red"
    echo ""
    read -p "  ¿Estás seguro? Escribe 'ELIMINAR' para confirmar: " confirm

    if [ "$confirm" != "ELIMINAR" ]; then
        print_info "Desinstalación cancelada"
        exit 0
    fi

    echo ""

    # Detect OS for service removal
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')

    # Stop and remove service
    if [ "$OS" = "linux" ]; then
        if systemctl is-active --quiet iris-node 2>/dev/null; then
            print_info "Deteniendo servicio systemd..."
            sudo systemctl stop iris-node 2>/dev/null || true
            sudo systemctl disable iris-node 2>/dev/null || true
        fi
        if [ -f "/etc/systemd/system/iris-node.service" ]; then
            print_info "Eliminando servicio systemd..."
            sudo rm -f "/etc/systemd/system/iris-node.service"
            sudo systemctl daemon-reload 2>/dev/null || true
            print_success "Servicio systemd eliminado"
        fi
    elif [ "$OS" = "darwin" ]; then
        PLIST_FILE="$HOME/Library/LaunchAgents/network.iris.node.plist"
        if [ -f "$PLIST_FILE" ]; then
            print_info "Deteniendo servicio launchd..."
            launchctl unload "$PLIST_FILE" 2>/dev/null || true
            rm -f "$PLIST_FILE"
            print_success "Servicio launchd eliminado"
        fi
    fi

    # Remove symlinks from /usr/local/bin
    for cmd in "$BIN_NAME" "iris"; do
        if [ -L "/usr/local/bin/$cmd" ]; then
            print_info "Eliminando symlink $cmd..."
            if [ -w "/usr/local/bin" ]; then
                rm -f "/usr/local/bin/$cmd"
            else
                sudo rm -f "/usr/local/bin/$cmd" 2>/dev/null || true
            fi
        fi
    done
    print_success "Symlinks eliminados"

    # Remove PATH from shell config
    for config_file in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.profile"; do
        if [ -f "$config_file" ] && grep -q ".iris/bin" "$config_file"; then
            print_info "Limpiando $config_file..."
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' '/# Iris Network Node Agent/d' "$config_file" 2>/dev/null || true
                sed -i '' '/\.iris\/bin/d' "$config_file" 2>/dev/null || true
            else
                sed -i '/# Iris Network Node Agent/d' "$config_file" 2>/dev/null || true
                sed -i '/\.iris\/bin/d' "$config_file" 2>/dev/null || true
            fi
            print_success "PATH limpiado de $config_file"
        fi
    done

    # Remove installation directory
    if [ -d "$INSTALL_DIR" ]; then
        print_info "Eliminando directorio de instalación..."
        rm -rf "$INSTALL_DIR"
        print_success "Directorio $INSTALL_DIR eliminado"
    else
        print_warning "Directorio $INSTALL_DIR no encontrado"
    fi

    echo ""
    echo -e "${GREEN}"
    echo "  ╔═══════════════════════════════════════════════════════════════════╗"
    echo "  ║              Desinstalación Completada                            ║"
    echo "  ╚═══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo -e "  ${CYAN}Tu nodo ha sido eliminado de Iris Network.${NC}"
    echo -e "  Gracias por participar."
    echo ""

    exit 0
}

# =============================================================================
# Main
# =============================================================================

main() {
    # Check for help
    if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
        echo "Iris Network - Node Agent Installer"
        echo ""
        echo "Uso: $0 [opciones]"
        echo ""
        echo "Opciones:"
        echo "  -h, --help      Mostrar esta ayuda"
        echo "  --token TOKEN   Usar token de enrollment existente"
        echo "  --no-service    No instalar como servicio"
        echo "  --uninstall     Desinstalar completamente (elimina todos los datos)"
        echo ""
        exit 0
    fi

    # Check for uninstall
    if [ "$1" = "--uninstall" ]; then
        uninstall_node
    fi

    # Parse arguments
    while [ $# -gt 0 ]; do
        case "$1" in
            --token)
                ENROLLMENT_TOKEN="$2"
                SKIP_AUTH=true
                shift 2
                ;;
            --no-service)
                SKIP_SERVICE=true
                shift
                ;;
            --uninstall)
                uninstall_node
                ;;
            *)
                shift
                ;;
        esac
    done

    print_banner

    # Step 1: Platform detection
    detect_platform

    # Step 2: Check coordinator
    check_coordinator

    # Step 3: Check Node.js (for TUI)
    check_nodejs

    # Step 4: Check LM Studio
    check_lmstudio

    # Step 5: Authentication (if no token provided)
    if [ -z "$ENROLLMENT_TOKEN" ]; then
        authenticate_user
        generate_enrollment_token
    else
        print_step "Usando token proporcionado"
        print_success "Token: ${ENROLLMENT_TOKEN:0:20}..."
    fi

    # Step 6: Download binary
    download_binary

    # Step 7: Setup PATH (always, regardless of mode)
    setup_path

    # Step 8: Install Node.js TUI
    install_nodejs_tui

    # Step 9: Configure
    configure_node

    # Step 10: Service installation
    if [ "$SKIP_SERVICE" != true ]; then
        ask_autostart
        if [ "$ENABLE_AUTOSTART" = true ]; then
            case "$OS" in
                linux) install_systemd_service ;;
                darwin) install_launchd_service ;;
            esac
        fi
    fi

    # Done!
    print_completion
}

main "$@"
