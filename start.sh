#!/bin/bash
# Starts the Semantic Image Finder and opens it in your browser.
# Press Control-C in this window to stop it.
cd "$(dirname "$0")"

BLUE='\033[1;34m'; GREEN='\033[1;32m'; RED='\033[1;31m'; OFF='\033[0m'

API_PORT="${API_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
export API_PORT FRONTEND_PORT

if [ ! -d backend/.venv ] || [ ! -d frontend/node_modules ]; then
  echo -e "${RED}Not set up yet. Run ./setup.sh first.${OFF}"; exit 1
fi

# Make sure PostgreSQL is awake before the backend tries to create its database.
# shellcheck source=lib/postgres.sh
. "$(dirname "$0")/lib/postgres.sh"
if ! pg_isready -q 2>/dev/null; then
  echo "Starting PostgreSQL ..."
  pg_ensure_running || { echo -e "${RED}"; pg_failure_help; echo -e "${OFF}"; exit 1; }
fi

free_port() {
  local pid; pid="$(lsof -ti tcp:"$1" 2>/dev/null || true)"
  [ -n "$pid" ] && { echo "Freeing port $1 ..."; kill -9 $pid 2>/dev/null; sleep 1; }
}
free_port "$API_PORT"
free_port "$FRONTEND_PORT"

cleanup() { echo -e "\nStopping ..."; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0; }
trap cleanup INT TERM

echo -e "${BLUE}Starting the search engine ...${OFF}"
backend/.venv/bin/python -m uvicorn app.main:app \
  --app-dir backend --host 127.0.0.1 --port "$API_PORT" &
BACKEND_PID=$!

# Wait for the API to answer before starting the UI.
for _ in $(seq 1 60); do
  curl -fs "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1 && break
  sleep 1
done

echo -e "${BLUE}Starting the web page ...${OFF}"
(cd frontend && npm run dev --silent) &
FRONTEND_PID=$!

sleep 3
URL="http://localhost:$FRONTEND_PORT"
echo -e "\n${GREEN}Ready. Opening $URL${OFF}"
echo -e "Leave this window open. Press ${BLUE}Control-C${OFF} to stop.\n"
open "$URL" 2>/dev/null

wait
