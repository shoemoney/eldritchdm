#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
# 🐉  EldritchDM — install.sh
#
#  Bootstraps a working Python environment, installs all dependencies, and
#  verifies that the required local services (oMLX + dm20) are reachable.
#
#  Created by Jeremy Schoemaker (shoemoney) · MIT licensed · 2026
#  Usage:  ./install.sh         # interactive, verbose
#          ./install.sh --quiet # less chatty
#          ./install.sh --no-venv # use the current python instead of creating .venv
# ════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── 🎨 Pretty output helpers ────────────────────────────────────────────────
RED=$'\033[0;31m'; GRN=$'\033[0;32m'; YLW=$'\033[0;33m'; BLU=$'\033[0;34m'
MGN=$'\033[0;35m'; CYN=$'\033[0;36m'; BLD=$'\033[1m'; DIM=$'\033[2m'; RST=$'\033[0m'

QUIET=0
NO_VENV=0
for arg in "$@"; do
  case "$arg" in
    --quiet) QUIET=1 ;;
    --no-venv) NO_VENV=1 ;;
    -h|--help)
      cat <<HELP
🐉 EldritchDM installer

Usage: ./install.sh [--quiet] [--no-venv]

  --quiet     less verbose output
  --no-venv   skip creating .venv (use the active python)
  -h, --help  show this help
HELP
      exit 0
      ;;
    *) echo "${RED}❌ Unknown arg: $arg${RST}" >&2; exit 2 ;;
  esac
done

say()  { [ "$QUIET" -eq 1 ] && return 0; printf '%s\n' "$*"; }
hdr()  { say ""; say "${BLD}${BLU}═══ $* ═══${RST}"; }
ok()   { say "${GRN}✅ $*${RST}"; }
warn() { say "${YLW}⚠️  $*${RST}"; }
err()  { printf '%s\n' "${RED}❌ $*${RST}" >&2; }
info() { say "${CYN}ℹ️  $*${RST}"; }
step() { say "${MGN}▶  $*${RST}"; }

# ── 0. Banner ───────────────────────────────────────────────────────────────
cat <<'BANNER'
   ____    _       _      _    _       _       _____   __  __
  | ___|  | |   __| | _ _(_) |_| |__   |     | |     | |  \/  |
  |  _|   | |  / _` | '_| | |  _| '_ \ |   |   | | | | | |\/| |
  |____|  |_|  \__,_|_| |_| |\__|_| |_||___|___||_|_|_| |_|  |_|
                                  🐉  ShoeGPT, your forever DM
BANNER

say ""
info "Created by ${BLD}Jeremy Schoemaker${RST}${CYN} · MIT licensed · 2026${RST}"

# ── 1. Check we're at the project root ──────────────────────────────────────
hdr "1/8 ⏱️  Pre-flight"
if [ ! -f ".env.example" ]; then
  err "Run this from the EldritchDM project root (where .env.example lives)."
  exit 1
fi
ok "Project root confirmed."

# ── 2. Check Python version ─────────────────────────────────────────────────
hdr "2/8 🐍 Python"
if ! command -v python3 >/dev/null 2>&1; then
  err "python3 not found. Install Python 3.11+ first (brew install python@3.11)."
  exit 1
fi
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
PYMAJ=$(echo "$PYV" | cut -d. -f1)
PYMIN=$(echo "$PYV" | cut -d. -f2)
if [ "$PYMAJ" -lt 3 ] || { [ "$PYMAJ" -eq 3 ] && [ "$PYMIN" -lt 11 ]; }; then
  err "Python $PYV detected, need ≥3.11."
  err "Hint: brew install python@3.11 && hash -r"
  exit 1
fi
ok "Python $PYV ✓"

# ── 3. Check / install uv ───────────────────────────────────────────────────
hdr "3/8 📦 uv"
if ! command -v uv >/dev/null 2>&1; then
  warn "uv not found — installing via Astral's official script."
  info "(uv is a fast, hermetic Python package manager — recommended over pip.)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # shellcheck disable=SC1090,SC1091
  if [ -f "$HOME/.cargo/env" ]; then source "$HOME/.cargo/env"; fi
  if ! command -v uv >/dev/null 2>&1; then
    err "uv installation seems to have failed."
    err "Try manually: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
  fi
fi
UV_VERSION=$(uv --version 2>/dev/null | head -1 || echo unknown)
ok "uv installed ($UV_VERSION)"

# ── 4. Virtualenv ───────────────────────────────────────────────────────────
hdr "4/8 🌱 Virtual environment"
if [ "$NO_VENV" -eq 1 ]; then
  warn "--no-venv: using the current Python ($(which python3)) without isolation."
else
  if [ ! -d ".venv" ]; then
    step "Creating .venv with Python $PYV…"
    uv venv --python "$PYV"
  else
    info ".venv already exists — reusing."
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  ok "Virtualenv active: $(python -c 'import sys; print(sys.executable)')"
fi

# ── 5. Python dependencies ──────────────────────────────────────────────────
hdr "5/8 📚 Python dependencies"
step "Installing project dependencies…"

# When pyproject.toml exists, prefer editable install.
# Until then (project is in planning), install the known dep set directly.
DEPS=(
  "discord.py>=2.7.1,<3.0"
  "httpx>=0.27,<0.29"
  "aiosqlite>=0.20,<0.22"
  "pydantic>=2.8,<3.0"
  "tenacity>=8.5,<10.0"
  "structlog>=24.4,<26.0"
  "PyMuPDF>=1.24,<2.0"
  "pypdf>=4.3,<6.0"
  "python-dotenv>=1.0,<2.0"
)
DEV_DEPS=(
  "pytest>=8.0,<9.0"
  "pytest-asyncio>=0.23,<1.0"
  "pytest-cov>=5.0,<6.0"
  "ruff>=0.6,<1.0"
  "respx>=0.21,<1.0"      # httpx mocking
)

if [ -f "pyproject.toml" ]; then
  step "Found pyproject.toml — installing as editable package with [dev] extras."
  uv pip install -e ".[dev]" || {
    err "uv pip install -e .[dev] failed."
    exit 1
  }
else
  warn "No pyproject.toml yet (project is in planning phase) — installing pinned deps directly."
  uv pip install "${DEPS[@]}" "${DEV_DEPS[@]}"
fi

# Platform-conditional OCR
PLATFORM=$(uname -s)
if [ "$PLATFORM" = "Darwin" ]; then
  step "Detected macOS — installing ocrmac (Apple Vision OCR)…"
  uv pip install "ocrmac>=1.0,<2.0" || warn "ocrmac install failed — OCR will be unavailable on this host."
else
  step "Detected $PLATFORM — installing easyocr fallback (Linux/CUDA path)…"
  warn "easyocr drags in PyTorch — this is a big download (~2 GB)."
  uv pip install "easyocr>=1.7,<2.0" || warn "easyocr install failed — OCR will be unavailable."
fi

ok "All Python dependencies installed."

# ── 6. Verify oMLX reachable ────────────────────────────────────────────────
hdr "6/8 🧠 oMLX reachability"
OMLX_BASE="${OMLX_ENDPOINT:-http://localhost:8765/v1}"
if curl -fsS --max-time 3 "${OMLX_BASE}/models" >/dev/null 2>&1; then
  MODELS=$(curl -fsS "${OMLX_BASE}/models" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(", ".join(m["id"] for m in d.get("data", [])))' 2>/dev/null || echo "?")
  ok "oMLX at ${OMLX_BASE} is up. Loaded models: ${MODELS}"
  if echo "$MODELS" | grep -q "ShoeGPT"; then
    ok "✨ 'ShoeGPT' model is loaded — narration is ready."
  else
    warn "'ShoeGPT' model NOT loaded. Set OMLX_MODEL in .env to a model that IS loaded."
  fi
else
  warn "Couldn't reach oMLX at ${OMLX_BASE}."
  info "→ Install: https://github.com/macabdul9/omlx"
  info "→ Then run: omlx serve --model ShoeGPT  (or whatever model you've quantized)"
  info "→ The bot will start anyway but every interaction will report '🔌 DM is offline' until oMLX is up."
fi

# ── 7. Verify dm20 MCP exposed ──────────────────────────────────────────────
hdr "7/8 🛠️  dm20 MCP tools"
MCP_TOOLS_URL_DEFAULT="${MCP_TOOLS_URL:-http://localhost:8765/v1/mcp/tools}"
if curl -fsS --max-time 3 "${MCP_TOOLS_URL_DEFAULT}" >/dev/null 2>&1; then
  TOOL_COUNT=$(curl -fsS "${MCP_TOOLS_URL_DEFAULT}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d) if isinstance(d, list) else len(d.get("tools", [])))' 2>/dev/null || echo "?")
  DM20_COUNT=$(curl -fsS "${MCP_TOOLS_URL_DEFAULT}" | python3 -c 'import json,sys; d=json.load(sys.stdin); items=d if isinstance(d,list) else d.get("tools",[]); print(sum(1 for t in items if t.get("name","").startswith("dm20__")))' 2>/dev/null || echo "?")
  ok "${TOOL_COUNT} MCP tools exposed — dm20 contributes ${DM20_COUNT} of them."
  if [ "$DM20_COUNT" = "?" ] || [ "${DM20_COUNT:-0}" -lt 50 ]; then
    warn "Expected ≥50 dm20 tools — your dm20 server may be partially loaded."
    info "Try: dm20-server --reload   (or whatever your launchd unit does)"
  fi
else
  warn "Couldn't reach MCP tools endpoint at ${MCP_TOOLS_URL_DEFAULT}."
  info "→ Install: https://github.com/Polloinfilzato/dm20-protocol"
  info "→ Make sure dm20 is started by oMLX (check your oMLX --mcp-config)."
fi

# ── 8. Final hint ───────────────────────────────────────────────────────────
hdr "8/8 🎉 Done"
ok "Installation complete."
say ""
info "Next steps:"
say "  ${BLD}1.${RST} ${DIM}cp .env.example .env${RST}        ← copy the template"
say "  ${BLD}2.${RST} ${DIM}\$EDITOR .env${RST}                ← fill in DISCORD_TOKEN"
say "  ${BLD}3.${RST} ${DIM}python -m eldritch_dm.bootstrap${RST}  ← create local SQLite + verify deps"
say "  ${BLD}4.${RST} ${DIM}python run.py${RST}                ← roll initiative 🎲"
say ""
info "📜 Read the README.md for the verbose walkthrough."
info "🐛 Found a bug? Open an issue with LOG_LEVEL=DEBUG output."
say ""
say "${BLD}${MGN}May your nat 20s be many and your nat 1s be cinematic. 🐉${RST}"
