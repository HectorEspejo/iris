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

# GitHub release URL
GITHUB_REPO="iris-network/iris-node"
DOWNLOAD_BASE="https://github.com/${GITHUB_REPO}/releases/download/v${VERSION}"

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
        print_success "Sesión iniciada correctamente"
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
        print_info "Usando instalación desde Python..."
        PYTHON_MODE=true
    fi
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

    # Try to create symlink in /usr/local/bin
    if [ -d "/usr/local/bin" ]; then
        if [ -w "/usr/local/bin" ]; then
            ln -sf "$INSTALL_DIR/bin/$BIN_NAME" "/usr/local/bin/$BIN_NAME"
            print_success "Symlink creado: /usr/local/bin/$BIN_NAME"
            PATH_CONFIGURED=true
            return
        elif command_exists sudo; then
            print_info "Se requiere sudo para crear symlink en /usr/local/bin"
            if sudo ln -sf "$INSTALL_DIR/bin/$BIN_NAME" "/usr/local/bin/$BIN_NAME" 2>/dev/null; then
                print_success "Symlink creado: /usr/local/bin/$BIN_NAME"
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
    echo -e "    Config:      ${CYAN}$INSTALL_DIR/config.yaml${NC}"
    echo ""
    echo -e "  ${BOLD}Comandos útiles:${NC}"

    if [ "$PYTHON_MODE" = true ]; then
        echo -e "    ${CYAN}Iniciar:${NC}    cd $(dirname $INSTALL_DIR) && python -m node_agent.standalone_main --config $INSTALL_DIR/config.yaml"
    elif [ "$PATH_CONFIGURED" = true ]; then
        echo -e "    ${CYAN}Iniciar:${NC}    iris-node --config $INSTALL_DIR/config.yaml"
        echo -e "    ${CYAN}Ayuda:${NC}      iris-node --help"
    else
        echo -e "    ${CYAN}Iniciar:${NC}    $INSTALL_DIR/bin/$BIN_NAME --config $INSTALL_DIR/config.yaml"
    fi

    echo -e "    ${CYAN}Ver logs:${NC}   tail -f $INSTALL_DIR/logs/node.log"

    if [ "$OS" = "linux" ]; then
        echo -e "    ${CYAN}Estado:${NC}     systemctl status iris-node"
        echo -e "    ${CYAN}Reiniciar:${NC}  sudo systemctl restart iris-node"
        echo -e "    ${CYAN}Detener:${NC}    sudo systemctl stop iris-node"
    elif [ "$OS" = "darwin" ]; then
        echo -e "    ${CYAN}Estado:${NC}     launchctl list | grep iris"
        echo -e "    ${CYAN}Detener:${NC}    launchctl unload ~/Library/LaunchAgents/network.iris.node.plist"
    fi

    echo ""
    echo -e "  ${GREEN}¡Tu nodo ahora es parte de Iris Network!${NC}"
    echo ""
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
        echo ""
        exit 0
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

    # Step 3: Check LM Studio
    check_lmstudio

    # Step 4: Authentication (if no token provided)
    if [ -z "$ENROLLMENT_TOKEN" ]; then
        authenticate_user
        generate_enrollment_token
    else
        print_step "Usando token proporcionado"
        print_success "Token: ${ENROLLMENT_TOKEN:0:20}..."
    fi

    # Step 5: Download binary
    download_binary

    # Step 6: Setup PATH
    if [ "$PYTHON_MODE" != true ]; then
        setup_path
    fi

    # Step 7: Configure
    configure_node

    # Step 8: Service installation
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
