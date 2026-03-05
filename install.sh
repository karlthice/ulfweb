#!/usr/bin/env bash
#
# ULF Web Install Script
# Cross-platform installer for Linux, WSL2, and macOS.
# Idempotent — safe to run multiple times.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }
header(){ echo -e "\n${BOLD}── $* ──${NC}"; }

# ── 1. Platform Detection ──────────────────────────────────────────────────
header "Platform Detection"

OS="unknown"
PKG_MGR="unknown"
IS_WSL=false
HAS_CUDA=false
HAS_NVCC=false
PYTHON_CMD=""
LLAMA_BUILD_ARGS=""

# Detect OS
case "$(uname -s)" in
    Linux*)
        OS="linux"
        # Check for WSL2
        if grep -qi "microsoft\|WSL" /proc/version 2>/dev/null; then
            IS_WSL=true
        fi
        ;;
    Darwin*)
        OS="macos"
        ;;
    *)
        err "Unsupported operating system: $(uname -s)"
        exit 1
        ;;
esac

# Detect package manager
if command -v apt-get &>/dev/null; then
    PKG_MGR="apt"
elif command -v brew &>/dev/null; then
    PKG_MGR="brew"
else
    if [ "$OS" = "macos" ]; then
        err "Homebrew not found. Install it from https://brew.sh"
        exit 1
    else
        err "No supported package manager found (apt or brew required)"
        exit 1
    fi
fi

# Detect CUDA
if command -v nvidia-smi &>/dev/null; then
    HAS_CUDA=true
fi
if command -v nvcc &>/dev/null; then
    HAS_NVCC=true
fi

# Detect Python 3.10+
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        py_version=$("$cmd" -c 'import sys; print(f"{sys.version_info.minor}")' 2>/dev/null || echo "0")
        py_major=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo "0")
        if [ "$py_major" = "3" ] && [ "$py_version" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

# Print summary
if $IS_WSL; then
    info "OS:              Linux (WSL2)"
else
    info "OS:              $OS"
fi
info "Package manager: $PKG_MGR"
if $HAS_CUDA; then
    info "NVIDIA GPU:      detected (nvidia-smi found)"
    if $HAS_NVCC; then
        info "CUDA toolkit:    installed (nvcc found)"
    else
        info "CUDA toolkit:    not installed (nvcc not found)"
    fi
else
    info "NVIDIA GPU:      not detected"
fi
if [ -n "$PYTHON_CMD" ]; then
    info "Python:          $($PYTHON_CMD --version 2>&1)"
else
    info "Python 3.10+:    not found (will install)"
fi

# ── 2. System Dependencies ─────────────────────────────────────────────────
header "System Dependencies"

if [ "$PKG_MGR" = "apt" ]; then
    PACKAGES=(
        python3 python3-venv python3-dev
        build-essential git cmake
        ffmpeg fonts-dejavu-core libsqlcipher-dev
    )

    # Add CUDA toolkit if GPU detected but nvcc not available
    if $HAS_CUDA && ! $HAS_NVCC; then
        PACKAGES+=(nvidia-cuda-toolkit)
        info "Adding nvidia-cuda-toolkit (GPU detected, nvcc missing)"
    fi

    info "Installing apt packages: ${PACKAGES[*]}"
    sudo apt-get update -qq
    sudo apt-get install -y -qq "${PACKAGES[@]}"
    ok "System packages installed"

elif [ "$PKG_MGR" = "brew" ]; then
    PACKAGES=(python@3 ffmpeg cmake git)

    info "Installing brew packages: ${PACKAGES[*]}"
    for pkg in "${PACKAGES[@]}"; do
        if brew list "$pkg" &>/dev/null; then
            ok "$pkg already installed"
        else
            brew install "$pkg"
            ok "$pkg installed"
        fi
    done

    # DejaVu fonts for PDF generation
    if ! brew list --cask font-dejavu-sans &>/dev/null 2>&1; then
        info "Installing DejaVu fonts (needed for PDF generation)"
        brew install --cask font-dejavu-sans 2>/dev/null || \
            warn "Could not install DejaVu fonts via Homebrew cask. PDF generation may fail."
    else
        ok "DejaVu fonts already installed"
    fi
fi

# Re-detect Python after installing packages
if [ -z "$PYTHON_CMD" ]; then
    for cmd in python3.12 python3.11 python3.10 python3; do
        if command -v "$cmd" &>/dev/null; then
            py_version=$("$cmd" -c 'import sys; print(f"{sys.version_info.minor}")' 2>/dev/null || echo "0")
            py_major=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo "0")
            if [ "$py_major" = "3" ] && [ "$py_version" -ge 10 ]; then
                PYTHON_CMD="$cmd"
                break
            fi
        fi
    done
fi

if [ -z "$PYTHON_CMD" ]; then
    err "Python 3.10+ not found even after installing packages"
    exit 1
fi
ok "Using $($PYTHON_CMD --version 2>&1)"

# ── 3. Python Virtual Environment ──────────────────────────────────────────
header "Python Virtual Environment"

if [ -d ".venv" ]; then
    ok "Virtual environment already exists"
else
    info "Creating virtual environment..."
    "$PYTHON_CMD" -m venv .venv
    ok "Virtual environment created"
fi

# Activate venv
# shellcheck disable=SC1091
source .venv/bin/activate

info "Upgrading pip, setuptools, wheel..."
pip install --upgrade pip setuptools wheel -q
ok "pip tools upgraded"

info "Installing Python dependencies from requirements.txt..."
pip install -r requirements.txt -q
ok "Python dependencies installed"

# ── 4. Build llama.cpp ──────────────────────────────────────────────────────
header "Build llama.cpp"

LLAMA_DIR="$SCRIPT_DIR/../llama.cpp"

if [ -d "$LLAMA_DIR" ]; then
    ok "llama.cpp already cloned at $LLAMA_DIR"
else
    info "Cloning llama.cpp..."
    git clone https://github.com/ggml-org/llama.cpp.git "$LLAMA_DIR"
    ok "llama.cpp cloned"
fi

# Determine build flags
CMAKE_ARGS=()
if $HAS_CUDA && (command -v nvcc &>/dev/null); then
    CMAKE_ARGS+=("-DGGML_CUDA=ON")
    info "Build mode: CUDA (GPU acceleration)"
elif [ "$OS" = "macos" ]; then
    CMAKE_ARGS+=("-DGGML_METAL=ON")
    info "Build mode: Metal (Apple Silicon GPU acceleration)"
else
    info "Build mode: CPU only"
fi

info "Building llama.cpp..."
cmake -S "$LLAMA_DIR" -B "$LLAMA_DIR/build" "${CMAKE_ARGS[@]}" -DCMAKE_BUILD_TYPE=Release -Wno-dev 2>&1 | tail -3
cmake --build "$LLAMA_DIR/build" --config Release -j "$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)" 2>&1 | tail -5

LLAMA_SERVER="$LLAMA_DIR/build/bin/llama-server"
if [ -f "$LLAMA_SERVER" ]; then
    ok "llama-server built successfully: $LLAMA_SERVER"
else
    err "llama-server binary not found after build"
    err "Expected at: $LLAMA_SERVER"
    exit 1
fi

# ── 5. Generate config.yaml ────────────────────────────────────────────────
header "Configuration"

# Resolve to absolute path for config
LLAMA_SERVER_ABS="$(cd "$LLAMA_DIR/build/bin" && pwd)/llama-server"
LLAMA_DIR_ABS="$(cd "$LLAMA_DIR" && pwd)"
MODELS_DIR_ABS="$SCRIPT_DIR/models"

if [ -f "config.yaml" ]; then
    ok "config.yaml already exists (not overwriting)"
else
    info "Creating config.yaml with detected paths..."
    cat > config.yaml << YAML
server:
  host: "0.0.0.0"
  port: 8000

llama:
  url: "http://localhost:8080"

tilde:
  url: "http://localhost:8081"

database:
  path: "data/ulfweb.db"

defaults:
  temperature: 0.7
  top_k: 40
  top_p: 0.9
  repeat_penalty: 1.1
  max_tokens: 2048
  system_prompt: "You are a helpful assistant. When asked to create diagrams, charts, or flowcharts, use mermaid syntax in a \`\`\`mermaid code block."
  model: ""

models:
  path: "$MODELS_DIR_ABS,$LLAMA_DIR_ABS/models"
  llama_server: "$LLAMA_SERVER_ABS"

encryption:
  enabled: true
  key_file: "data/encryption.key"
YAML
    ok "config.yaml created"
fi

# ── 6. Create Data Directories ─────────────────────────────────────────────
header "Data Directories"

for dir in data data/logs data/voices models; do
    if [ -d "$dir" ]; then
        ok "$dir/ exists"
    else
        mkdir -p "$dir"
        ok "$dir/ created"
    fi
done

# ── 7. Caddy Reverse Proxy & HTTPS ──────────────────────────────────────────
header "Caddy Reverse Proxy & HTTPS"

# Install Caddy
if command -v caddy &>/dev/null; then
    ok "Caddy already installed: $(caddy version 2>/dev/null | head -1)"
else
    info "Installing Caddy..."
    if [ "$PKG_MGR" = "apt" ]; then
        sudo apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
        sudo apt-get update -qq
        sudo apt-get install -y -qq caddy
    elif [ "$PKG_MGR" = "brew" ]; then
        brew install caddy
    fi

    if command -v caddy &>/dev/null; then
        ok "Caddy installed: $(caddy version 2>/dev/null | head -1)"
    else
        warn "Could not install Caddy. HTTPS reverse proxy will not be available."
        warn "You can still use ULF Web over HTTP on port 8000."
    fi
fi

# Allow Caddy to bind to port 443 without root (Linux only)
if [ "$OS" = "linux" ] && command -v caddy &>/dev/null; then
    CADDY_BIN="$(which caddy)"
    if ! getcap "$CADDY_BIN" 2>/dev/null | grep -q cap_net_bind_service; then
        info "Granting Caddy permission to bind to port 443..."
        sudo setcap cap_net_bind_service=+ep "$CADDY_BIN"
        ok "Caddy can now bind to port 443 without root"
    else
        ok "Caddy already has port 443 bind capability"
    fi
fi

# Generate self-signed TLS certificate for LAN access
CERT_FILE="data/caddy-cert.pem"
KEY_FILE="data/caddy-key.pem"

if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    ok "TLS certificate already exists"
else
    info "Generating self-signed TLS certificate for LAN access..."

    # Detect LAN IP address
    LAN_IP=""
    if command -v ip &>/dev/null; then
        LAN_IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[0-9.]+' || true)
    fi
    if [ -z "$LAN_IP" ] && command -v ifconfig &>/dev/null; then
        LAN_IP=$(ifconfig 2>/dev/null | grep 'inet ' | grep -v '127.0.0.1' | head -1 | awk '{print $2}')
    fi

    # Build SAN list
    SAN="DNS:localhost,IP:127.0.0.1"
    if [ -n "$LAN_IP" ]; then
        SAN="$SAN,IP:$LAN_IP"
        info "Detected LAN IP: $LAN_IP"
    fi

    openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout "$KEY_FILE" -out "$CERT_FILE" \
        -days 3650 -subj "/CN=ULF Web" \
        -addext "subjectAltName=$SAN" 2>/dev/null
    chmod 600 "$KEY_FILE"
    ok "Self-signed TLS certificate generated (valid for 10 years)"
fi

# ── 8. Final Summary ───────────────────────────────────────────────────────
header "Installation Complete"

echo ""
echo -e "${GREEN}${BOLD}ULF Web is ready!${NC}"
echo ""
echo "  Detected environment:"
if $IS_WSL; then
    echo "    Platform:     Linux (WSL2)"
else
    echo "    Platform:     $OS"
fi
echo "    Python:       $($PYTHON_CMD --version 2>&1)"
if $HAS_CUDA && (command -v nvcc &>/dev/null); then
    echo "    GPU:          CUDA (NVIDIA)"
elif [ "$OS" = "macos" ]; then
    echo "    GPU:          Metal (Apple Silicon)"
else
    echo "    GPU:          None (CPU only)"
fi
echo "    llama-server: $LLAMA_SERVER_ABS"
if command -v caddy &>/dev/null; then
    echo "    Caddy:        $(caddy version 2>/dev/null | head -1)"
fi
echo ""
echo "  Next steps:"
echo ""
echo "    1. Download a GGUF model into the models/ directory."
echo "       Example (Qwen3 4B):"
echo "         wget -P models/ https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/qwen3-4b-q4_k_m.gguf"
echo ""
echo "    2. Start ULF Web:"
echo "         source .venv/bin/activate"
echo "         python3 -m backend.main"
echo ""
if command -v caddy &>/dev/null; then
    echo "    3. Start Caddy for HTTPS (in a separate terminal):"
    echo "         caddy run --config Caddyfile"
    echo ""
    echo "    4. Open https://localhost in your browser."
    if [ -n "${LAN_IP:-}" ]; then
        echo "       LAN access: https://$LAN_IP"
    fi
    echo "       (Accept the self-signed certificate warning on first visit)"
    echo "       HTTPS is required for microphone access (dictation) over LAN."
else
    echo "    3. Open http://localhost:8000 in your browser."
fi
echo "       Default login: admin / admin"
echo ""
