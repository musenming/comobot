#!/usr/bin/env bash
# Comobot Installer for macOS / Linux
#
# Global users:
#   curl -fsSL https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.sh | bash
#
# China users (auto-detected, or explicit):
#   curl -fsSL https://dl.comindx.com/scripts/install.sh | bash
#   COMOBOT_MIRROR=cn curl -fsSL https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.sh | bash
set -euo pipefail

REPO="musenming/comobot"
INSTALL_DIR="$HOME/.comobot/bin"
CLEANUP_DIR=""
SHELL_RC=""

# Mirror configuration
CN_MIRROR_BASE="https://dl.comindx.com"
GITHUB_MIRROR_BASE="https://github.com/$REPO"
MIRROR="${COMOBOT_MIRROR:-}"   # "cn" | "github" | "" (auto-detect)

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[comobot]${NC} $*"; }
success() { echo -e "${GREEN}[comobot]${NC} $*"; }
warn()    { echo -e "${YELLOW}[comobot]${NC} $*"; }
error()   { echo -e "${RED}[comobot]${NC} $*" >&2; exit 1; }

# ── Mirror auto-detection ─────────────────────────────────────────────────────
detect_mirror() {
    if [[ "$MIRROR" == "cn" || "$MIRROR" == "github" ]]; then
        return  # user explicit, skip detection
    fi
    # Try GitHub with a short timeout; fall back to CN mirror on failure
    if ! curl -fsSI --connect-timeout 4 --max-time 5 "https://github.com" &>/dev/null; then
        warn "GitHub is unreachable, switching to CN mirror automatically."
        MIRROR="cn"
    else
        MIRROR="github"
    fi
}

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

# ── Fetch latest release info (CN mirror) ────────────────────────────────────
_get_version_cn() {
    VERSION=$(curl -fsSL --connect-timeout 8 "$CN_MIRROR_BASE/releases/latest/version.txt" \
        2>/dev/null | tr -d '[:space:]') || true
    if [[ -z "$VERSION" ]]; then
        error "Failed to fetch version from CN mirror ($CN_MIRROR_BASE). Please retry later."
    fi
    ASSET_NAME="comobot-${VERSION}-${TARGET}.tar.gz"
    DOWNLOAD_URL="$CN_MIRROR_BASE/releases/v${VERSION}/${ASSET_NAME}"
}

# ── Fetch latest release info (GitHub) ───────────────────────────────────────
_get_version_github() {
    # Primary: resolve version via GitHub redirect (no API, no rate limit)
    local redirect_url
    redirect_url=$(curl -fsSI "https://github.com/$REPO/releases/latest" 2>/dev/null \
        | grep -i '^location:' | sed 's/.*tag\/v//;s/[[:space:]]//g') || true
    VERSION="${redirect_url:-}"

    # Fallback: use GitHub API (may hit rate limit for unauthenticated requests)
    if [[ -z "$VERSION" ]]; then
        local curl_opts=(-fsSL)
        if [[ -n "${GITHUB_TOKEN:-}" ]]; then
            curl_opts+=(-H "Authorization: token $GITHUB_TOKEN")
        fi
        local release_info
        release_info=$(curl "${curl_opts[@]}" \
            "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null) || true
        if [[ -n "$release_info" ]]; then
            VERSION=$(echo "$release_info" | grep '"tag_name"' | sed 's/.*"v\(.*\)".*/\1/')
        fi
    fi

    if [[ -z "${VERSION:-}" ]]; then
        error "Failed to determine latest version. Visit https://github.com/$REPO/releases"
    fi

    ASSET_NAME="comobot-${VERSION}-${TARGET}.tar.gz"
    DOWNLOAD_URL="https://github.com/$REPO/releases/download/v${VERSION}/${ASSET_NAME}"
}

# ── Fetch latest release URL ─────────────────────────────────────────────────
get_download_url() {
    info "Fetching latest release info..."
    if [[ "$MIRROR" == "cn" ]]; then
        _get_version_cn
    else
        _get_version_github
    fi
    info "Found comobot v${VERSION} for ${TARGET}"
}

# ── Download, extract, install ────────────────────────────────────────────────
install_binary() {
    mkdir -p "$INSTALL_DIR"

    local tmp
    tmp=$(mktemp -d)
    CLEANUP_DIR="$tmp"
    trap 'rm -rf "$CLEANUP_DIR"' EXIT

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
    # 1. Symlink into /usr/local/bin so comobot is immediately available
    local symlink_dir="/usr/local/bin"
    local symlink_ok=false

    if [[ -d "$symlink_dir" && -w "$symlink_dir" ]]; then
        ln -sf "$INSTALL_DIR/comobot" "$symlink_dir/comobot" && symlink_ok=true
    elif command -v sudo &>/dev/null; then
        # When running via "curl | bash", stdin is the pipe, not the terminal.
        # Redirect sudo's stdin from /dev/tty so it can prompt for password.
        if [[ ! -d "$symlink_dir" ]]; then
            sudo mkdir -p "$symlink_dir" < /dev/tty 2>/dev/null || true
        fi
        if [[ -d "$symlink_dir" ]]; then
            sudo ln -sf "$INSTALL_DIR/comobot" "$symlink_dir/comobot" < /dev/tty 2>/dev/null \
                && symlink_ok=true
        fi
    fi

    if $symlink_ok; then
        info "Created symlink in $symlink_dir"
    fi

    # 2. Also add to shell rc for future sessions
    case "${SHELL:-}" in
        */zsh)  SHELL_RC="$HOME/.zshrc" ;;
        */bash) SHELL_RC="$HOME/.bashrc" ;;
        *)      SHELL_RC="$HOME/.profile" ;;
    esac

    if ! grep -q "$INSTALL_DIR" "$SHELL_RC" 2>/dev/null; then
        {
            echo ""
            echo "# Comobot"
            echo "export PATH=\"$INSTALL_DIR:\$PATH\""
        } >> "$SHELL_RC"
        info "Added $INSTALL_DIR to PATH in $SHELL_RC"
    fi

    export PATH="$INSTALL_DIR:$PATH"

    # 3. If symlink failed, tell the user to open a new terminal
    if ! $symlink_ok; then
        warn "Could not create symlink in $symlink_dir"
        warn "Please open a new terminal window, then comobot will be available."
    fi
}

# ── Verify ────────────────────────────────────────────────────────────────────
verify() {
    export PATH="$INSTALL_DIR:$PATH"
    if command -v comobot &>/dev/null; then
        local ver
        ver=$(comobot --version 2>/dev/null || echo "$VERSION")
        success "Comobot installed successfully! Version: $ver"
        # Report install stat (silent, non-blocking)
        curl -fsS "https://dl.comindx.com/ping?v=${VERSION}&p=${TARGET}" -o /dev/null 2>/dev/null &
        echo ""
        # Run onboard to generate config if not exists
        if [[ ! -f "$HOME/.comobot/config.json" ]]; then
            info "Running initial setup (comobot onboard)..."
            comobot onboard || warn "Onboard failed. You can run 'comobot onboard' manually later."
        fi
        echo ""
        info "Run ${GREEN}comobot gateway${NC} to start the Web UI client"
        info "First-time users can configure Provider and Channel on the Setup page"
        echo ""
        # Ask user whether to start comobot gateway now
        printf "${BLUE}[comobot]${NC} Would you like to start comobot gateway now? (yes/no): "
        local answer
        read -r answer < /dev/tty 2>/dev/null || read -r answer
        case "$answer" in
            [Yy]|[Yy][Ee][Ss])
                info "Starting comobot gateway..."
                exec comobot gateway
                ;;
            *)
                success "Installation complete! You can run 'comobot gateway' anytime to start the service."
                ;;
        esac
    else
        warn "Installation completed but 'comobot' not found in PATH."
        echo "  Please restart your terminal or run: source $SHELL_RC"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo ""
    info "Comobot Installer"
    echo ""

    detect_mirror
    detect_platform
    get_download_url
    install_binary
    setup_path
    verify
}

main "$@"
