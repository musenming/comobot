#!/usr/bin/env bash
# Comobot Installer for macOS / Linux
# Usage: curl -fsSL https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.sh | bash
set -euo pipefail

REPO="musenming/comobot"
INSTALL_DIR="$HOME/.comobot/bin"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[comobot]${NC} $*"; }
success() { echo -e "${GREEN}[comobot]${NC} $*"; }
warn()    { echo -e "${YELLOW}[comobot]${NC} $*"; }
error()   { echo -e "${RED}[comobot]${NC} $*" >&2; exit 1; }

# ── Platform detection ────────────────────────────────────────────────────────
detect_platform() {
    local os arch
    os=$(uname -s | tr '[:upper:]' '[:lower:]')
    arch=$(uname -m)

    case "$os" in
        darwin) PLATFORM="macos" ;;
        linux)  PLATFORM="linux" ;;
        *)      error "Unsupported OS: $os" ;;
    esac

    case "$arch" in
        x86_64|amd64)  ARCH="x64" ;;
        arm64|aarch64) ARCH="arm64" ;;
        *)             error "Unsupported architecture: $arch" ;;
    esac

    TARGET="${PLATFORM}-${ARCH}"
    info "Detected platform: $TARGET"
}

# ── Fetch latest release URL ─────────────────────────────────────────────────
get_download_url() {
    info "Fetching latest release info..."

    local curl_opts=(-fsSL)
    # Use GITHUB_TOKEN if available to avoid API rate limits
    if [[ -n "${GITHUB_TOKEN:-}" ]]; then
        curl_opts+=(-H "Authorization: token $GITHUB_TOKEN")
    fi

    local release_info
    release_info=$(curl "${curl_opts[@]}" "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null) || true

    if [[ -n "$release_info" ]]; then
        VERSION=$(echo "$release_info" | grep '"tag_name"' | sed 's/.*"v\(.*\)".*/\1/')
    fi

    # Fallback: resolve latest tag via GitHub redirect if API fails (rate limit)
    if [[ -z "${VERSION:-}" ]]; then
        warn "API rate-limited, falling back to redirect detection..."
        local redirect_url
        redirect_url=$(curl -fsSI "https://github.com/$REPO/releases/latest" 2>/dev/null \
            | grep -i '^location:' | sed 's/.*tag\/v//;s/[[:space:]]//g') || true
        VERSION="${redirect_url:-}"
    fi

    if [[ -z "${VERSION:-}" ]]; then
        error "Failed to determine latest version. Try setting GITHUB_TOKEN or visit https://github.com/$REPO/releases"
    fi

    ASSET_NAME="comobot-${VERSION}-${TARGET}.tar.gz"
    DOWNLOAD_URL="https://github.com/$REPO/releases/download/v${VERSION}/${ASSET_NAME}"

    info "Found comobot v${VERSION} for ${TARGET}"
}

# ── Download, extract, install ────────────────────────────────────────────────
install_binary() {
    mkdir -p "$INSTALL_DIR"

    local tmp
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT

    info "Downloading $ASSET_NAME..."
    curl -fsSL "$DOWNLOAD_URL" -o "$tmp/comobot.tar.gz" \
        || error "Download failed."

    info "Extracting..."
    tar -xzf "$tmp/comobot.tar.gz" -C "$tmp"

    # The archive contains a comobot/ directory with the binary inside
    if [[ -f "$tmp/comobot/comobot" ]]; then
        cp "$tmp/comobot/comobot" "$INSTALL_DIR/comobot"
    else
        error "Unexpected archive structure. Expected comobot/comobot inside the tarball."
    fi

    chmod +x "$INSTALL_DIR/comobot"
    info "Installed to $INSTALL_DIR/comobot"
}

# ── Add to PATH ───────────────────────────────────────────────────────────────
setup_path() {
    local shell_rc=""
    case "${SHELL:-}" in
        */zsh)  shell_rc="$HOME/.zshrc" ;;
        */bash) shell_rc="$HOME/.bashrc" ;;
        *)      shell_rc="$HOME/.profile" ;;
    esac

    if ! grep -q "$INSTALL_DIR" "$shell_rc" 2>/dev/null; then
        {
            echo ""
            echo "# Comobot"
            echo "export PATH=\"$INSTALL_DIR:\$PATH\""
        } >> "$shell_rc"
        info "Added $INSTALL_DIR to PATH in $shell_rc"
    fi
}

# ── Verify ────────────────────────────────────────────────────────────────────
verify() {
    export PATH="$INSTALL_DIR:$PATH"
    if command -v comobot &>/dev/null; then
        local ver
        ver=$(comobot --version 2>/dev/null || echo "$VERSION")
        success "Comobot installed successfully! Version: $ver"
        echo "  Run 'comobot --help' to get started."
        echo "  Please restart your terminal or run: source ${shell_rc:-~/.profile}"
    else
        warn "Installation completed but verification failed. Check $INSTALL_DIR"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo ""
    info "Comobot Installer"
    echo ""

    detect_platform
    get_download_url
    install_binary
    setup_path
    verify
}

main "$@"
