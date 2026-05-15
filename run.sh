#!/bin/bash
cd "$(dirname "$0")"

RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

source venv/bin/activate 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${RED}[✗]${NC} Could not activate virtual environment."
    echo "    Run ./setup.sh first to create the environment."
    exit 1
fi

# Resolve Python binary
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo -e "${RED}[✗]${NC} Python not found. Run ./setup.sh first."
    exit 1
fi

# Try to run gunicorn via python -m first (most reliable), then direct command
if $PYTHON -m gunicorn --version &>/dev/null 2>&1; then
    exec $PYTHON -m gunicorn app:app --bind 127.0.0.1:5000 --workers 2 --threads 4 --timeout 600
elif command -v gunicorn &>/dev/null; then
    exec gunicorn app:app --bind 127.0.0.1:5000 --workers 2 --threads 4 --timeout 600
else
    echo -e "${RED}[✗]${NC} gunicorn is not available."
    echo ""
    echo -e "    ${YELLOW}Tried:${NC}"
    echo "      • $PYTHON -m gunicorn  → module not found"
    echo "      • gunicorn (direct)    → command not found"
    echo ""
    echo "    This usually means packages weren't installed into the venv."
    echo "    Fix it by running:"
    echo ""
    echo "      rm -rf venv && ./setup.sh"
    echo ""
    exit 1
fi
