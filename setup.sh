#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

step() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[✗]${NC} $1"; echo ""; exit 1; }
info() { echo -e "${BLUE}[→]${NC} $1"; }

cd "$(dirname "$0")"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   YT Downloader — Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ─── Resolve Python binary ───────────────────────────────────
# Try python3 first, then python, and validate it's Python 3.9+
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
fi

if [ -n "$PYTHON" ]; then
    PY_VER=$($PYTHON --version 2>&1 | awk '{print $2}')
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
        PYTHON=""
    fi
fi

# ─── Resolve pip command ─────────────────────────────────────
# Determines the working pip invocation: python -m pip > pip3 > pip
resolve_pip() {
    if "$PYTHON" -m pip --version &>/dev/null 2>&1; then
        PIP="$PYTHON -m pip"
    elif command -v pip3 &>/dev/null; then
        PIP="pip3"
    elif command -v pip &>/dev/null; then
        PIP="pip"
    else
        PIP=""
    fi
}

# ─── Check OS ───────────────────────────────────────────────
OS="$(uname -s)"
if [ "$OS" = "Darwin" ]; then
    PKG_MANAGER="brew"
elif [ "$OS" = "Linux" ]; then
    if command -v apt-get &>/dev/null; then
        PKG_MANAGER="apt"
    elif command -v dnf &>/dev/null; then
        PKG_MANAGER="dnf"
    elif command -v pacman &>/dev/null; then
        PKG_MANAGER="pacman"
    else
        PKG_MANAGER="unknown"
    fi
else
    fail "Unsupported OS: $OS. This script supports macOS and Linux."
fi

# ─── Check/Install Homebrew (macOS only) ────────────────────
if [ "$OS" = "Darwin" ] && ! command -v brew &>/dev/null; then
    warn "Homebrew not found. It's needed to install dependencies."
    echo ""
    read -p "    Install Homebrew now? (y/n): " choice
    if [ "$choice" = "y" ] || [ "$choice" = "Y" ]; then
        info "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        if ! command -v brew &>/dev/null; then
            fail "Homebrew installation failed. Install manually: https://brew.sh"
        fi
        step "Homebrew installed"
    else
        fail "Homebrew is required on macOS. Install it from https://brew.sh"
    fi
fi

# ─── Check/Install Python ──────────────────────────────────
install_python_hint() {
    case "$PKG_MANAGER" in
        brew)   echo "    brew install python3" ;;
        apt)    echo "    sudo apt-get install python3 python3-venv" ;;
        dnf)    echo "    sudo dnf install python3" ;;
        pacman) echo "    sudo pacman -S python" ;;
        *)      echo "    Install Python 3.9+ from https://www.python.org/downloads/" ;;
    esac
}

if [ -n "$PYTHON" ]; then
    PY_VER=$($PYTHON --version 2>&1 | awk '{print $2}')
    step "Python $PY_VER found (using '$PYTHON')"
else
    if command -v python3 &>/dev/null; then
        BAD_VER=$(python3 --version 2>&1 | awk '{print $2}')
        warn "Found python3 ($BAD_VER) but Python 3.9+ is required."
    elif command -v python &>/dev/null; then
        BAD_VER=$(python --version 2>&1 | awk '{print $2}')
        warn "Found 'python' ($BAD_VER) but Python 3.9+ is required."
        echo -e "    ${YELLOW}Note:${NC} 'python' points to Python $BAD_VER on this system."
        echo -e "    ${YELLOW}      ${NC} This project requires Python 3.9 or newer."
    else
        warn "No Python installation found on this system."
        echo -e "    ${YELLOW}Checked:${NC} python3, python — neither is available in PATH."
    fi
    echo ""
    read -p "    Install Python 3 now? (y/n): " choice
    if [ "$choice" = "y" ] || [ "$choice" = "Y" ]; then
        info "Installing Python..."
        case "$PKG_MANAGER" in
            brew)   brew install python3 ;;
            apt)    sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip ;;
            dnf)    sudo dnf install -y python3 python3-pip ;;
            pacman) sudo pacman -S --noconfirm python python-pip ;;
            *)      fail "Cannot auto-install Python on this system.\n$(install_python_hint)" ;;
        esac
        # Re-resolve after install
        if command -v python3 &>/dev/null; then
            PYTHON="python3"
        elif command -v python &>/dev/null; then
            PYTHON="python"
        fi
        if [ -z "$PYTHON" ]; then
            fail "Python installation failed.\n$(install_python_hint)"
        fi
        step "Python installed ($($PYTHON --version 2>&1 | awk '{print $2}'))"
    else
        echo ""
        fail "Python 3.9+ is required. Install with:\n$(install_python_hint)"
    fi
fi

# ─── Check/Install venv module ─────────────────────────────
if ! $PYTHON -m venv --help &>/dev/null 2>&1; then
    warn "Python venv module not found."
    echo -e "    ${YELLOW}Tried:${NC} $PYTHON -m venv — module not available."
    echo ""
    if [ "$PKG_MANAGER" = "apt" ]; then
        read -p "    Install python3-venv now? (y/n): " choice
        if [ "$choice" = "y" ] || [ "$choice" = "Y" ]; then
            info "Installing python3-venv..."
            sudo apt-get install -y python3-venv
            if ! $PYTHON -m venv --help &>/dev/null 2>&1; then
                fail "Failed to install python3-venv. Run manually:\n    sudo apt-get install python3-venv"
            fi
            step "python3-venv installed"
        else
            fail "python3-venv is required. Install with:\n    sudo apt-get install python3-venv"
        fi
    else
        fail "Python venv module is missing. Reinstall Python:\n$(install_python_hint)"
    fi
else
    step "Python venv module available"
fi

# ─── Check/Install ffmpeg ──────────────────────────────────
install_ffmpeg_hint() {
    case "$PKG_MANAGER" in
        brew)   echo "    brew install ffmpeg" ;;
        apt)    echo "    sudo apt-get install ffmpeg" ;;
        dnf)    echo "    sudo dnf install ffmpeg" ;;
        pacman) echo "    sudo pacman -S ffmpeg" ;;
        *)      echo "    Install ffmpeg from https://ffmpeg.org/download.html" ;;
    esac
}

if command -v ffmpeg &>/dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')
    step "ffmpeg $FFMPEG_VERSION found"
else
    warn "ffmpeg not found. It's required for video processing."
    echo ""
    read -p "    Install ffmpeg now? (y/n): " choice
    if [ "$choice" = "y" ] || [ "$choice" = "Y" ]; then
        info "Installing ffmpeg..."
        case "$PKG_MANAGER" in
            brew)   brew install ffmpeg ;;
            apt)    sudo apt-get update && sudo apt-get install -y ffmpeg ;;
            dnf)    sudo dnf install -y ffmpeg ;;
            pacman) sudo pacman -S --noconfirm ffmpeg ;;
            *)      fail "Cannot auto-install ffmpeg on this system.\n$(install_ffmpeg_hint)" ;;
        esac
        if ! command -v ffmpeg &>/dev/null; then
            fail "ffmpeg installation failed.\n$(install_ffmpeg_hint)"
        fi
        step "ffmpeg installed"
    else
        echo ""
        fail "ffmpeg is required. Install with:\n$(install_ffmpeg_hint)"
    fi
fi

# ─── Create directories ───────────────────────────────────
mkdir -p static downloads
step "Directories ready"

# ─── Create virtual environment ───────────────────────────
if [ -d "venv" ]; then
    step "Virtual environment exists"
else
    info "Creating virtual environment..."
    $PYTHON -m venv venv
    if [ ! -f "venv/bin/activate" ]; then
        fail "Failed to create virtual environment. Check disk space and permissions."
    fi
    step "Virtual environment created"
fi

# ─── Activate venv ────────────────────────────────────────
source venv/bin/activate || fail "Failed to activate virtual environment."

# ─── Install dependencies ─────────────────────────────────
if [ ! -f "requirements.txt" ]; then
    fail "requirements.txt not found. Make sure you're running this from the project directory."
fi

resolve_pip
if [ -z "$PIP" ]; then
    fail "pip is not available inside the virtual environment.\n    Tried: $PYTHON -m pip, pip3, pip — none worked.\n    Try recreating the venv: rm -rf venv && ./setup.sh"
fi
step "Using pip: $PIP"

info "Installing Python packages..."
$PIP install --upgrade pip -q 2>/dev/null || warn "Could not upgrade pip (non-critical)"
$PIP install -r requirements.txt -q 2>&1 | tail -5
if [ $? -ne 0 ]; then
    fail "Failed to install dependencies. Check your internet connection and try again."
fi
step "Dependencies installed"

# ─── Verify everything works ──────────────────────────────
info "Verifying installation..."

VERIFY_OUTPUT=$($PYTHON -c "
import sys
errors = []
try:
    import flask
except ImportError:
    errors.append('flask')
try:
    import yt_dlp
except ImportError:
    errors.append('yt-dlp')
try:
    import gunicorn
except ImportError:
    errors.append('gunicorn')
if errors:
    print('MISSING:' + ','.join(errors))
    sys.exit(1)
print('OK')
" 2>&1)

if [ "$VERIFY_OUTPUT" = "OK" ]; then
    step "All packages verified"
else
    MISSING=$(echo "$VERIFY_OUTPUT" | grep "MISSING:" | cut -d: -f2)
    fail "Missing packages: $MISSING\n    Try: $PIP install $MISSING"
fi

# ─── Check if app.py exists ───────────────────────────────
if [ ! -f "app.py" ]; then
    fail "app.py not found. Make sure all project files are present."
fi

if [ ! -f "static/index.html" ]; then
    fail "static/index.html not found. Make sure all project files are present."
fi

step "Project files verified"

# ─── Done ─────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "   ${GREEN}Setup complete!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Start the server:"
echo -e "    ${BLUE}./run.sh${NC}"
echo ""
echo "  Then open:"
echo -e "    ${BLUE}http://127.0.0.1:5000${NC}"
echo ""
