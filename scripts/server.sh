#!/usr/bin/env bash
# Usage: ./scripts/server.sh [start|stop|restart|status]
# Enforces a single uvicorn instance on port 8400 via a PID file.

set -euo pipefail

PIDFILE="/tmp/ai-dev-platform.pid"
HOST="127.0.0.1"
PORT="8400"
CMD="python3 -m uvicorn app.api.main:app --host $HOST --port $PORT"

is_running() {
  if [[ -f "$PIDFILE" ]]; then
    local pid
    pid=$(cat "$PIDFILE")
    kill -0 "$pid" 2>/dev/null
  else
    return 1
  fi
}

do_stop() {
  # Kill via PID file first
  if [[ -f "$PIDFILE" ]]; then
    local pid
    pid=$(cat "$PIDFILE")
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping server (pid $pid)..."
      kill "$pid"
      local i=0
      while kill -0 "$pid" 2>/dev/null && (( i < 10 )); do
        sleep 0.5; (( i++ ))
      done
    fi
    rm -f "$PIDFILE"
  fi
  # Also kill any stray processes still holding the port
  local stray
  stray=$(lsof -ti "tcp:$PORT" 2>/dev/null || true)
  if [[ -n "$stray" ]]; then
    echo "Killing stray process(es) on port $PORT: $stray"
    echo "$stray" | xargs kill -9 2>/dev/null || true
  fi
}

do_start() {
  if is_running; then
    echo "Server already running (pid $(cat "$PIDFILE")). Use 'restart' to replace it."
    exit 0
  fi
  do_stop  # clear any orphan before starting
  cd "$(dirname "$0")/.."
  echo "Starting server on $HOST:$PORT..."
  nohup $CMD >> /tmp/ai-dev-platform.log 2>&1 &
  echo $! > "$PIDFILE"
  # Wait for startup
  local i=0
  while (( i < 20 )); do
    if curl -sf "http://$HOST:$PORT/api/health" -H "X-Api-Token: $(grep APP_API_TOKEN .env 2>/dev/null | cut -d= -f2)" > /dev/null 2>&1; then
      echo "Server started (pid $(cat "$PIDFILE"))."
      exit 0
    fi
    sleep 0.5; (( i++ ))
  done
  echo "Warning: server started but health check did not respond in 10s. Check /tmp/ai-dev-platform.log"
}

case "${1:-status}" in
  start)   do_start ;;
  stop)    do_stop; echo "Server stopped." ;;
  restart) do_stop; sleep 1; do_start ;;
  status)
    if is_running; then
      echo "Running (pid $(cat "$PIDFILE"))"
    else
      echo "Not running"
    fi
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac
