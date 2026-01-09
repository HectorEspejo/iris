#!/bin/bash
# =============================================================================
# ClubAI Node Agent Installer
#
# One-line installation:
#   curl -fsSL https://clubai.network/install.sh | bash
#
# Or with wget:
#   wget -qO- https://clubai.network/install.sh | bash
# =============================================================================

set -e

VERSION="1.0.0"
COORDINATOR_DEFAULT="168.119.10.189"
COORDINATOR_PORT="8000"
INSTALL_DIR="$HOME/.clubai"
BIN_NAME="clubai-node"

# GitHub release URL (update with actual repo)
GITHUB_REPO="clubai/clubai-node"
DOWNLOAD_BASE="https://github.com/${GITHUB_REPO}/releases/download/v${VERSION}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
print_banner() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║         ClubAI Node Agent Installer v${VERSION}            ║${NC}"
    echo -e "${BLUE}║       Distributed AI Inference Network                    ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Detect platform and architecture
detect_platform() {
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)

    case "$ARCH" in
        x86_64|amd64)
            ARCH="amd64"
            ;;
        arm64|aarch64)
            ARCH="arm64"
            ;;
        *)
            print_error "Unsupported architecture: $ARCH"
            exit 1
            ;;
    esac

    case "$OS" in
        linux)
            PLATFORM="linux-$ARCH"
            ;;
        darwin)
            PLATFORM="darwin-$ARCH"
            ;;
        *)
            print_error "Unsupported operating system: $OS"
            exit 1
            ;;
    esac

    print_success "Detected platform: $PLATFORM"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Download file using curl or wget
download_file() {
    local url="$1"
    local output="$2"

    if command_exists curl; then
        curl -fsSL "$url" -o "$output"
    elif command_exists wget; then
        wget -q "$url" -O "$output"
    else
        print_error "Neither curl nor wget found. Please install one of them."
        exit 1
    fi
}

# Download the binary
download_binary() {
    DOWNLOAD_URL="${DOWNLOAD_BASE}/clubai-node-${PLATFORM}"

    print_info "Downloading ClubAI Node Agent..."
    print_info "URL: $DOWNLOAD_URL"

    mkdir -p "$INSTALL_DIR/bin"

    if ! download_file "$DOWNLOAD_URL" "$INSTALL_DIR/bin/$BIN_NAME"; then
        print_error "Failed to download binary"
        print_info "This may mean the release hasn't been published yet."
        print_info "For now, you can build from source:"
        print_info "  git clone https://github.com/${GITHUB_REPO}.git"
        print_info "  cd clubai-node && pip install pyinstaller pyyaml"
        print_info "  cd node_agent && pyinstaller clubai-node.spec"
        exit 1
    fi

    chmod +x "$INSTALL_DIR/bin/$BIN_NAME"
    print_success "Binary downloaded to $INSTALL_DIR/bin/$BIN_NAME"
}

# Validate enrollment token with coordinator
validate_token() {
    local token="$1"

    print_info "Validating enrollment token..."

    local response
    if command_exists curl; then
        response=$(curl -s -X POST "http://${COORDINATOR_DEFAULT}:${COORDINATOR_PORT}/nodes/validate-token" \
            -H "Content-Type: application/json" \
            -d "{\"token\": \"$token\"}" 2>/dev/null || echo '{"valid":false,"error":"Connection failed"}')
    else
        response=$(wget -qO- --post-data="{\"token\": \"$token\"}" \
            --header="Content-Type: application/json" \
            "http://${COORDINATOR_DEFAULT}:${COORDINATOR_PORT}/nodes/validate-token" 2>/dev/null || echo '{"valid":false,"error":"Connection failed"}')
    fi

    if echo "$response" | grep -q '"valid":true'; then
        print_success "Token is valid"
        return 0
    else
        local error=$(echo "$response" | grep -o '"error":"[^"]*"' | cut -d'"' -f4)
        print_error "Invalid token: ${error:-Unknown error}"
        return 1
    fi
}

# Interactive configuration
configure_node() {
    echo ""
    echo -e "${GREEN}=== Node Configuration ===${NC}"
    echo ""

    # Enrollment token
    while true; do
        read -p "Enter your enrollment token: " ENROLLMENT_TOKEN
        if [ -z "$ENROLLMENT_TOKEN" ]; then
            print_error "Enrollment token is required"
            continue
        fi

        if validate_token "$ENROLLMENT_TOKEN"; then
            break
        else
            echo ""
            read -p "Try again? [Y/n]: " retry
            if [[ "$retry" =~ ^[Nn]$ ]]; then
                print_error "Cannot proceed without a valid token"
                exit 1
            fi
        fi
    done

    # LM Studio URL
    echo ""
    read -p "LM Studio URL [http://localhost:1234/v1]: " LMSTUDIO_URL
    LMSTUDIO_URL=${LMSTUDIO_URL:-"http://localhost:1234/v1"}

    # Node ID
    DEFAULT_NODE_ID="node-$(hostname | tr '[:upper:]' '[:lower:]' | tr '.' '-' | cut -c1-20)-$(date +%s | tail -c 6)"
    echo ""
    read -p "Node ID [$DEFAULT_NODE_ID]: " NODE_ID
    NODE_ID=${NODE_ID:-"$DEFAULT_NODE_ID"}

    # Autostart
    echo ""
    read -p "Enable autostart on boot? [Y/n]: " AUTOSTART
    AUTOSTART=${AUTOSTART:-"Y"}

    # Create configuration file
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/data"
    mkdir -p "$INSTALL_DIR/logs"

    cat > "$INSTALL_DIR/config.yaml" << EOF
# ClubAI Node Agent Configuration
# Generated by installer on $(date -Iseconds)

node_id: "$NODE_ID"
coordinator_url: "wss://${COORDINATOR_DEFAULT}:${COORDINATOR_PORT}/nodes/connect"
lmstudio_url: "$LMSTUDIO_URL"
enrollment_token: "$ENROLLMENT_TOKEN"
data_dir: "$INSTALL_DIR/data"
log_dir: "$INSTALL_DIR/logs"
EOF

    print_success "Configuration saved to $INSTALL_DIR/config.yaml"
}

# Install systemd service (Linux)
install_systemd_service() {
    print_info "Installing systemd service..."

    SERVICE_FILE="/etc/systemd/system/clubai-node.service"

    # Check if we need sudo
    if [ "$(id -u)" -ne 0 ]; then
        if ! command_exists sudo; then
            print_warning "Cannot install service without root access"
            print_info "Run the following commands manually as root:"
            echo ""
            show_systemd_unit
            return 1
        fi
        SUDO="sudo"
    else
        SUDO=""
    fi

    $SUDO tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=ClubAI Node Agent
Documentation=https://clubai.network/docs
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
    $SUDO systemctl enable clubai-node
    $SUDO systemctl start clubai-node

    print_success "systemd service installed and started"
}

# Show systemd unit (for manual installation)
show_systemd_unit() {
    echo "# /etc/systemd/system/clubai-node.service"
    cat << EOF
[Unit]
Description=ClubAI Node Agent
After=network-online.target

[Service]
Type=simple
User=$USER
ExecStart=$INSTALL_DIR/bin/$BIN_NAME --config $INSTALL_DIR/config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
}

# Install launchd service (macOS)
install_launchd_service() {
    print_info "Installing launchd service..."

    PLIST_DIR="$HOME/Library/LaunchAgents"
    PLIST_FILE="$PLIST_DIR/com.clubai.node.plist"

    mkdir -p "$PLIST_DIR"

    cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.clubai.node</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/bin/$BIN_NAME</string>
        <string>--config</string>
        <string>$INSTALL_DIR/config.yaml</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>NetworkState</key>
        <true/>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>$INSTALL_DIR/logs/node.log</string>
    <key>StandardErrorPath</key>
    <string>$INSTALL_DIR/logs/node.log</string>
</dict>
</plist>
EOF

    launchctl load "$PLIST_FILE"

    print_success "launchd service installed and started"
}

# Print completion message
print_completion() {
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              Installation Complete!                       ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "  Node ID:      $NODE_ID"
    echo "  Config:       $INSTALL_DIR/config.yaml"
    echo "  Logs:         $INSTALL_DIR/logs/node.log"
    echo ""
    echo "  Useful Commands:"
    echo "    Start:      $INSTALL_DIR/bin/$BIN_NAME --config $INSTALL_DIR/config.yaml"
    echo "    View logs:  tail -f $INSTALL_DIR/logs/node.log"

    if [ "$OS" = "linux" ]; then
        echo "    Status:     systemctl status clubai-node"
        echo "    Stop:       sudo systemctl stop clubai-node"
        echo "    Restart:    sudo systemctl restart clubai-node"
    elif [ "$OS" = "darwin" ]; then
        echo "    Status:     launchctl list | grep clubai"
        echo "    Stop:       launchctl unload ~/Library/LaunchAgents/com.clubai.node.plist"
        echo "    Restart:    launchctl unload ~/Library/LaunchAgents/com.clubai.node.plist && launchctl load ~/Library/LaunchAgents/com.clubai.node.plist"
    fi

    echo ""
    echo "  Your node is now part of the ClubAI network!"
    echo ""
}

# Main installation flow
main() {
    print_banner

    # Check for help flag
    if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
        echo "Usage: $0 [options]"
        echo ""
        echo "Options:"
        echo "  -h, --help     Show this help message"
        echo "  --no-service   Skip service installation"
        echo ""
        echo "Environment Variables:"
        echo "  ENROLLMENT_TOKEN  Pre-set enrollment token"
        echo "  NODE_ID           Pre-set node ID"
        echo "  LMSTUDIO_URL      Pre-set LM Studio URL"
        echo ""
        exit 0
    fi

    detect_platform
    download_binary
    configure_node

    # Service installation
    if [[ "$AUTOSTART" =~ ^[Yy]$ ]] && [ "$1" != "--no-service" ]; then
        case "$OS" in
            linux)
                install_systemd_service
                ;;
            darwin)
                install_launchd_service
                ;;
        esac
    fi

    print_completion
}

# Run main function
main "$@"
