#!/bin/bash
# One-time setup for Semantic Image Finder on macOS.
# Safe to run again at any time.
set -e
cd "$(dirname "$0")"

BLUE='\033[1;34m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'; RED='\033[1;31m'; OFF='\033[0m'
step() { echo -e "\n${BLUE}==> $1${OFF}"; }
ok()   { echo -e "${GREEN}  ✓ $1${OFF}"; }
warn() { echo -e "${YELLOW}  ! $1${OFF}"; }
die()  { echo -e "${RED}  ✗ $1${OFF}"; exit 1; }

# shellcheck source=lib/postgres.sh
. "$(dirname "$0")/lib/postgres.sh"

echo -e "${BLUE}Semantic Image Finder - setup${OFF}"
echo "This installs everything the app needs. It may take 5-10 minutes the first time."

# ---------------------------------------------------------------- Homebrew
step "Checking Homebrew"
if ! command -v brew >/dev/null 2>&1; then
  warn "Homebrew is not installed. Installing it now (you may be asked for your Mac password)."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Apple Silicon installs to /opt/homebrew; Intel to /usr/local.
  if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
fi
command -v brew >/dev/null 2>&1 || die "Homebrew still not found. Restart Terminal and try again."
ok "Homebrew ready"

# ---------------------------------------------------------------- Postgres
step "Checking PostgreSQL"
PG_FORMULA="$(brew list --formula 2>/dev/null | grep -m1 '^postgresql@' || true)"
if [ -z "$PG_FORMULA" ]; then
  PG_FORMULA="postgresql@18"
  echo "  Installing $PG_FORMULA ..."
  brew install "$PG_FORMULA"
fi
ok "$PG_FORMULA installed"

if ! brew list --formula 2>/dev/null | grep -q '^pgvector$'; then
  echo "  Installing pgvector (the piece that makes image similarity search possible) ..."
  brew install pgvector
fi
ok "pgvector installed"

step "Starting the database"
if pg_ensure_running; then
  ok "PostgreSQL is running"
else
  echo
  pg_failure_help
  die "PostgreSQL is not accepting connections yet"
fi

# ---------------------------------------------------------------- Python
step "Checking Python"

# PyTorch 2.5 publishes ready-made packages for Python 3.10, 3.11 and 3.12 only.
# Older Python cannot run the code; newer Python has nothing to download. So we
# need an interpreter inside that range, and we install one if there isn't any.
PY_MIN=10
PY_MAX=12
PY_WANTED="3.11 3.12 3.10"   # tried in this order
PY_INSTALL="python@3.11"     # installed if none of the above are present

# Minor version number of a given interpreter, or nothing if it isn't usable.
py_minor() {
  "$1" -c 'import sys; print(sys.version_info[1] if sys.version_info[0] == 3 else "")' 2>/dev/null
}

# True when this interpreter is a version the packages actually support.
py_usable() {
  local minor
  minor="$(py_minor "$1")"
  [ -n "$minor" ] && [ "$minor" -ge "$PY_MIN" ] && [ "$minor" -le "$PY_MAX" ]
}

# First supported interpreter we can find, searching PATH and Homebrew's own
# directory (a brew-installed python is not always on PATH).
find_python() {
  local ver cand
  for ver in $PY_WANTED; do
    # Several routes, because Homebrew's layout differs between versions and
    # between Apple Silicon and Intel Macs. The first that works wins.
    for cand in "python$ver" \
                "$(brew --prefix "python@$ver" 2>/dev/null)/bin/python$ver" \
                "$(brew --prefix "python@$ver" 2>/dev/null)/libexec/bin/python3"; do
      if command -v "$cand" >/dev/null 2>&1 && py_usable "$cand"; then
        command -v "$cand"; return 0
      fi
    done
  done
  # Last resort: the default python3, if it happens to be in range.
  if command -v python3 >/dev/null 2>&1 && py_usable python3; then
    command -v python3; return 0
  fi
  return 1
}

PYTHON_BIN="$(find_python || true)"

if [ -z "$PYTHON_BIN" ]; then
  FOUND="$(python3 --version 2>/dev/null || echo 'not installed')"
  warn "Python 3.$PY_MIN-3.$PY_MAX is required, but you have: $FOUND"
  echo "  Installing $PY_INSTALL alongside it (your existing Python is left alone) ..."
  brew install "$PY_INSTALL"
  hash -r 2>/dev/null || true   # forget any cached command locations
  PYTHON_BIN="$(find_python || true)"
fi

[ -n "$PYTHON_BIN" ] || die "Could not find or install Python 3.$PY_MIN-3.$PY_MAX. Try running: brew install $PY_INSTALL"
ok "Using Python $("$PYTHON_BIN" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')  ($PYTHON_BIN)"

step "Installing Python packages (this is the slow part - CLIP and PyTorch)"
# If a previous run built the environment with a Python we no longer support,
# throw it away rather than trying to install into it.
if [ -x backend/.venv/bin/python ] && ! py_usable backend/.venv/bin/python; then
  warn "The existing environment used an unsupported Python - rebuilding it"
  rm -rf backend/.venv
fi
"$PYTHON_BIN" -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip --quiet
backend/.venv/bin/pip install -r backend/requirements.txt --quiet
ok "Python packages installed"

[ -f backend/.env ] || cp backend/.env.example backend/.env
ok "Configuration file ready (backend/.env)"

# ---------------------------------------------------------------- Node
step "Checking Node.js"
if ! command -v node >/dev/null 2>&1; then
  echo "  Installing Node.js ..."
  brew install node
fi
ok "Node $(node --version)"

step "Installing the web interface"
(cd frontend && npm install --silent)
ok "Web interface installed"

# ---------------------------------------------------------------- Model
step "Downloading the CLIP model (~600 MB, one time only)"
backend/.venv/bin/python -c "
from transformers import CLIPModel, CLIPProcessor
CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32')
CLIPModel.from_pretrained('openai/clip-vit-base-patch32')
" >/dev/null 2>&1 && ok "Model downloaded" || warn "Model will download on first search instead"

echo -e "\n${GREEN}Setup complete.${OFF}"
echo -e "Now run:  ${BLUE}./start.sh${OFF}"
