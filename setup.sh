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
brew services start "$PG_FORMULA" >/dev/null 2>&1 || true
for _ in $(seq 1 20); do
  if pg_isready -q 2>/dev/null; then break; fi
  sleep 1
done
pg_isready -q 2>/dev/null || die "PostgreSQL did not start. Try: brew services restart $PG_FORMULA"
ok "PostgreSQL is running"

# ---------------------------------------------------------------- Python
step "Checking Python"
command -v python3 >/dev/null 2>&1 || brew install python@3.11
PYV="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
ok "Python $PYV"

step "Installing Python packages (this is the slow part - CLIP and PyTorch)"
python3 -m venv backend/.venv
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
