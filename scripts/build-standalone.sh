#!/bin/bash
# =============================================================================
# ClubAI Node Agent Build Script
#
# Builds standalone executables using PyInstaller.
#
# Usage:
#   ./scripts/build-standalone.sh           # Build for current platform
#   ./scripts/build-standalone.sh --all     # Build for all platforms (requires Docker)
# =============================================================================

set -e

VERSION="1.0.0"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/dist"
NODE_AGENT_DIR="$PROJECT_ROOT/node_agent"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
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

# Check dependencies
check_dependencies() {
    print_info "Checking dependencies..."

    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required"
        exit 1
    fi

    # Check pip
    if ! python3 -m pip --version &> /dev/null; then
        print_error "pip is required"
        exit 1
    fi

    print_success "Dependencies OK"
}

# Install build dependencies
install_build_deps() {
    print_info "Installing build dependencies..."
    python3 -m pip install --upgrade pip
    python3 -m pip install pyinstaller pyyaml
    print_success "Build dependencies installed"
}

# Build for current platform
build_current_platform() {
    print_info "Building for current platform..."

    cd "$NODE_AGENT_DIR"

    # Clean previous builds
    rm -rf build dist __pycache__

    # Run PyInstaller
    python3 -m PyInstaller clubai-node.spec --clean

    # Get output name
    OUTPUT_NAME=$(ls dist/ | head -1)

    # Create version directory
    mkdir -p "$BUILD_DIR/v$VERSION"
    mv "dist/$OUTPUT_NAME" "$BUILD_DIR/v$VERSION/"

    # Clean up
    rm -rf build dist __pycache__

    print_success "Build complete: $BUILD_DIR/v$VERSION/$OUTPUT_NAME"
}

# Build for all platforms using Docker
build_all_platforms() {
    print_info "Building for all platforms using Docker..."

    if ! command -v docker &> /dev/null; then
        print_error "Docker is required for cross-platform builds"
        exit 1
    fi

    # Create output directory
    mkdir -p "$BUILD_DIR/v$VERSION"

    # Build for Linux AMD64
    print_info "Building for Linux AMD64..."
    docker run --rm -v "$PROJECT_ROOT:/src" \
        python:3.11-slim \
        /bin/bash -c "
            cd /src && \
            pip install pyinstaller pyyaml websockets httpx structlog cryptography pydantic && \
            cd node_agent && \
            python -m PyInstaller clubai-node.spec --clean && \
            cp dist/clubai-node-* /src/dist/v$VERSION/
        "

    # Build for Linux ARM64 (requires ARM Docker host or buildx)
    if docker buildx version &> /dev/null; then
        print_info "Building for Linux ARM64..."
        docker run --rm --platform linux/arm64 -v "$PROJECT_ROOT:/src" \
            python:3.11-slim \
            /bin/bash -c "
                cd /src && \
                pip install pyinstaller pyyaml websockets httpx structlog cryptography pydantic && \
                cd node_agent && \
                python -m PyInstaller clubai-node.spec --clean && \
                cp dist/clubai-node-* /src/dist/v$VERSION/
            " 2>/dev/null || print_warning "ARM64 build skipped (no ARM support)"
    fi

    print_success "Multi-platform build complete"
    ls -la "$BUILD_DIR/v$VERSION/"
}

# Create GitHub release assets
create_release_assets() {
    print_info "Creating release assets..."

    RELEASE_DIR="$BUILD_DIR/release-v$VERSION"
    mkdir -p "$RELEASE_DIR"

    # Copy binaries
    cp "$BUILD_DIR/v$VERSION/"* "$RELEASE_DIR/" 2>/dev/null || true

    # Copy installer scripts
    cp "$PROJECT_ROOT/installer/install.sh" "$RELEASE_DIR/"
    cp "$PROJECT_ROOT/installer/install.ps1" "$RELEASE_DIR/"

    # Create checksums
    cd "$RELEASE_DIR"
    sha256sum * > SHA256SUMS 2>/dev/null || shasum -a 256 * > SHA256SUMS

    print_success "Release assets created in $RELEASE_DIR"
    ls -la "$RELEASE_DIR"
}

# Print usage
print_usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --all           Build for all platforms (requires Docker)"
    echo "  --release       Create release assets with checksums"
    echo "  --clean         Clean build artifacts"
    echo "  -h, --help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0              Build for current platform"
    echo "  $0 --all        Build for all platforms"
    echo "  $0 --release    Build and create release assets"
}

# Clean build artifacts
clean_build() {
    print_info "Cleaning build artifacts..."
    rm -rf "$BUILD_DIR"
    rm -rf "$NODE_AGENT_DIR/build"
    rm -rf "$NODE_AGENT_DIR/dist"
    rm -rf "$NODE_AGENT_DIR/__pycache__"
    print_success "Clean complete"
}

# Main
main() {
    case "$1" in
        --help|-h)
            print_usage
            exit 0
            ;;
        --clean)
            clean_build
            exit 0
            ;;
        --all)
            check_dependencies
            install_build_deps
            build_all_platforms
            ;;
        --release)
            check_dependencies
            install_build_deps
            build_current_platform
            create_release_assets
            ;;
        *)
            check_dependencies
            install_build_deps
            build_current_platform
            ;;
    esac

    echo ""
    print_success "Build completed successfully!"
    echo ""
    echo "Next steps:"
    echo "  1. Test the binary: $BUILD_DIR/v$VERSION/clubai-node-* --help"
    echo "  2. Upload to GitHub releases"
    echo "  3. Update download URLs in install.sh and install.ps1"
}

main "$@"
