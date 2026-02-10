#!/usr/bin/env bash
# setup.sh — Check and install dependencies for the media-ingest plugin.
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$1"; }
warn() { printf "${YELLOW}  ! %s${NC}\n" "$1"; }
fail() { printf "${RED}  ✗ %s${NC}\n" "$1"; }

echo ""
echo "media-ingest — dependency check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

errors=0

# Python 3
if command -v python3 &>/dev/null; then
    py_version=$(python3 --version 2>&1)
    ok "Python 3 found ($py_version)"
else
    fail "Python 3 not found"
    warn "Install: https://www.python.org/downloads/"
    errors=$((errors + 1))
fi

# ffmpeg
if command -v ffmpeg &>/dev/null; then
    ff_version=$(ffmpeg -version 2>&1 | head -1)
    ok "ffmpeg found ($ff_version)"
else
    fail "ffmpeg not found"
    if command -v brew &>/dev/null; then
        warn "Install: brew install ffmpeg"
    elif command -v apt &>/dev/null; then
        warn "Install: sudo apt install ffmpeg"
    else
        warn "Install: https://ffmpeg.org/download.html"
    fi
    errors=$((errors + 1))
fi

# ffprobe
if command -v ffprobe &>/dev/null; then
    ok "ffprobe found"
else
    fail "ffprobe not found (usually bundled with ffmpeg)"
    errors=$((errors + 1))
fi

# Pillow
if python3 -c "import PIL" &>/dev/null 2>&1; then
    pil_version=$(python3 -c "import PIL; print(PIL.__version__)")
    ok "Pillow found ($pil_version)"
else
    warn "Pillow not found — installing..."
    if python3 -m pip install Pillow; then
        ok "Pillow installed"
    else
        fail "Failed to install Pillow"
        warn "Try: pip3 install Pillow"
        errors=$((errors + 1))
    fi
fi

echo ""
if [ "$errors" -eq 0 ]; then
    printf "${GREEN}All dependencies satisfied.${NC}\n"
else
    printf "${RED}%d missing dependency(ies). See above for install instructions.${NC}\n" "$errors"
    exit 1
fi
echo ""
