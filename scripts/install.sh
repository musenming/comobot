#!/usr/bin/env bash
# Comobot One-Click Installer for macOS / Linux
# Usage: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.sh)"
set -euo pipefail

REPO="musenming/comobot"
INSTALL_DIR_LINUX="$HOME/.local/comobot"
INSTALL_DIR_MAC="$HOME/Applications/comobot"
DATA_DIR="$HOME/.comobot"
PORT=18790

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[comobot]${NC} $*"; }
success() { echo -e "${GREEN}[comobot]${NC} $*"; }
warn()    { echo -e "${YELLOW}[comobot]${NC} $*"; }
error()   { echo -e "${RED}[comobot]${NC} $*" >&2; exit 1; }

# ── OS detection ──────────────────────────────────────────────────────────────
detect_os() {
  if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    INSTALL_DIR="$INSTALL_DIR_MAC"
    # Require macOS 12+
    MACOS_VER=$(sw_vers -productVersion | cut -d. -f1)
    [[ "$MACOS_VER" -ge 12 ]] || error "Comobot requires macOS 12 (Monterey) or later. Current: $(sw_vers -productVersion)"
  elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    INSTALL_DIR="$INSTALL_DIR_LINUX"
  else
    error "Unsupported OS: $OSTYPE. Comobot supports macOS 12+ and Linux."
  fi
  info "Detected OS: $OS"
}

# ── Homebrew (macOS) ──────────────────────────────────────────────────────────
ensure_homebrew() {
  if ! command -v brew &>/dev/null; then
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add brew to PATH for the rest of this script
    eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null)"
  fi
  success "Homebrew ready"
}

# ── Python 3.11 ───────────────────────────────────────────────────────────────
ensure_python() {
  PYTHON=""
  for cmd in python3.12 python3.11 python3; do
    if command -v "$cmd" &>/dev/null; then
      VER=$("$cmd" -c "import sys; print(sys.version_info[:2])")
      if [[ "$VER" > "(3, 10)" ]]; then
        PYTHON="$cmd"
        break
      fi
    fi
  done

  if [[ -z "$PYTHON" ]]; then
    info "Installing Python 3.11..."
    if [[ "$OS" == "macos" ]]; then
      brew install python@3.11
      PYTHON="$(brew --prefix python@3.11)/bin/python3.11"
    elif command -v apt-get &>/dev/null; then
      sudo apt-get update -qq && sudo apt-get install -y python3.11 python3.11-venv python3-pip
      PYTHON="python3.11"
    elif command -v yum &>/dev/null; then
      sudo yum install -y python3.11
      PYTHON="python3.11"
    else
      error "Cannot auto-install Python. Please install Python 3.11+ and re-run."
    fi
  fi
  success "Python: $($PYTHON --version)"
}

# ── Node.js 18+ ───────────────────────────────────────────────────────────────
ensure_node() {
  if command -v node &>/dev/null; then
    NODE_VER=$(node -e "process.exit(parseInt(process.version.slice(1)))" 2>/dev/null; echo $?)
    NODE_MAJOR=$(node -e "console.log(parseInt(process.version.slice(1)))")
    if [[ "$NODE_MAJOR" -ge 18 ]]; then
      success "Node.js: $(node --version)"
      return
    fi
  fi
  info "Installing Node.js 18 LTS..."
  if [[ "$OS" == "macos" ]]; then
    brew install node@18
    export PATH="$(brew --prefix node@18)/bin:$PATH"
  elif command -v apt-get &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
    sudo apt-get install -y nodejs
  elif command -v yum &>/dev/null; then
    curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -
    sudo yum install -y nodejs
  else
    error "Cannot auto-install Node.js. Please install Node.js 18+ and re-run."
  fi
  success "Node.js: $(node --version)"
}

# ── Download latest release ───────────────────────────────────────────────────
download_release() {
  info "Fetching latest release from GitHub..."
  LATEST_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
    | grep '"zipball_url"' | cut -d'"' -f4)
  if [[ -z "$LATEST_URL" ]]; then
    LATEST_URL="https://github.com/$REPO/archive/refs/heads/main.zip"
    warn "No release found, using main branch"
  fi

  TMP_ZIP=$(mktemp /tmp/comobot-XXXXXX.zip)
  info "Downloading $LATEST_URL ..."
  curl -fsSL -L "$LATEST_URL" -o "$TMP_ZIP"
  echo "$TMP_ZIP"
}

# ── Extract & setup ───────────────────────────────────────────────────────────
install_comobot() {
  local ZIP="$1"

  info "Installing to $INSTALL_DIR ..."
  mkdir -p "$INSTALL_DIR"
  TMP_DIR=$(mktemp -d)
  unzip -q "$TMP_ZIP" -d "$TMP_DIR"
  # Move extracted contents (GitHub adds a prefix dir)
  EXTRACTED=$(ls "$TMP_DIR" | head -1)
  cp -r "$TMP_DIR/$EXTRACTED/." "$INSTALL_DIR/"
  rm -rf "$TMP_DIR" "$ZIP"

  # Create venv
  info "Creating Python virtual environment..."
  "$PYTHON" -m venv "$INSTALL_DIR/.venv"
  "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip setuptools wheel -q
  "$INSTALL_DIR/.venv/bin/pip" install -e "$INSTALL_DIR" -q
  success "Python dependencies installed"

  # Build frontend
  if [[ -d "$INSTALL_DIR/web" ]]; then
    info "Building frontend..."
    (cd "$INSTALL_DIR/web" && npm ci --silent && npm run build --silent)
    success "Frontend built"
  fi

  # Create data directory
  mkdir -p "$DATA_DIR/workspace"
  success "Data directory: $DATA_DIR"
}

# ── macOS LaunchAgent (autostart) ─────────────────────────────────────────────
setup_macos_autostart() {
  PLIST_DIR="$HOME/Library/LaunchAgents"
  PLIST="$PLIST_DIR/ai.comobot.gateway.plist"
  mkdir -p "$PLIST_DIR"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>ai.comobot.gateway</string>
  <key>ProgramArguments</key>
  <array>
    <string>$INSTALL_DIR/.venv/bin/comobot</string>
    <string>gateway</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$DATA_DIR/gateway.log</string>
  <key>StandardErrorPath</key>
  <string>$DATA_DIR/gateway-error.log</string>
</dict>
</plist>
EOF
  launchctl load "$PLIST" 2>/dev/null || true
  success "macOS autostart configured"
}

# ── Linux systemd (optional) ──────────────────────────────────────────────────
setup_linux_autostart() {
  if ! command -v systemctl &>/dev/null; then return; fi
  SERVICE="$HOME/.config/systemd/user/comobot.service"
  mkdir -p "$(dirname "$SERVICE")"
  cat > "$SERVICE" <<EOF
[Unit]
Description=Comobot Gateway
After=network.target

[Service]
ExecStart=$INSTALL_DIR/.venv/bin/comobot gateway
Restart=always
RestartSec=5
StandardOutput=append:$DATA_DIR/gateway.log
StandardError=append:$DATA_DIR/gateway-error.log

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now comobot 2>/dev/null || true
  success "Linux systemd service enabled"
}

# ── Desktop shortcut ──────────────────────────────────────────────────────────
create_shortcut() {
  if [[ "$OS" == "macos" ]]; then
    SHORTCUT="$HOME/Desktop/Comobot.command"
    cat > "$SHORTCUT" <<EOF
#!/bin/bash
open http://localhost:$PORT
EOF
    chmod +x "$SHORTCUT"
    success "Desktop shortcut: $SHORTCUT"
  fi
}

# ── Start service ─────────────────────────────────────────────────────────────
start_service() {
  info "Starting Comobot gateway..."
  nohup "$INSTALL_DIR/.venv/bin/comobot" gateway \
    > "$DATA_DIR/gateway.log" 2>&1 &
  sleep 2
  if kill -0 $! 2>/dev/null; then
    success "Gateway started (PID $!)"
  else
    warn "Gateway may have failed to start. Check $DATA_DIR/gateway.log"
  fi
}

# ── Open browser ──────────────────────────────────────────────────────────────
open_browser() {
  URL="http://localhost:$PORT"
  info "Opening $URL ..."
  sleep 1
  if [[ "$OS" == "macos" ]]; then
    open "$URL"
  elif command -v xdg-open &>/dev/null; then
    xdg-open "$URL"
  else
    info "Please open $URL in your browser"
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  echo ""
  echo "  ╔═══════════════════════════════╗"
  echo "  ║   Comobot Installer v1.0      ║"
  echo "  ╚═══════════════════════════════╝"
  echo ""

  detect_os
  [[ "$OS" == "macos" ]] && ensure_homebrew
  ensure_python
  ensure_node

  ZIP=$(download_release)
  install_comobot "$ZIP"

  [[ "$OS" == "macos" ]] && setup_macos_autostart
  [[ "$OS" == "linux" ]] && setup_linux_autostart
  create_shortcut
  start_service
  open_browser

  echo ""
  success "Installation complete!"
  echo -e "  ${GREEN}→${NC} Open http://localhost:$PORT to configure Comobot"
  echo -e "  ${GREEN}→${NC} Data stored in $DATA_DIR"
  echo ""
}

main "$@"
