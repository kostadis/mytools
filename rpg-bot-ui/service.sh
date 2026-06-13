#!/usr/bin/env bash
# RPGBOT Builder service manager
# Usage: ./service.sh start|stop|restart|status|logs|tail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/.builder.pid"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/builder.log"
PORT="${PORT:-5110}"
HOST="${HOST:-127.0.0.1}"

mkdir -p "$LOG_DIR"

_is_running() {
    [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

cmd_start() {
    if _is_running; then
        echo "Already running (pid $(cat "$PID_FILE"))"
        return 1
    fi
    if [[ ! -f "$SCRIPT_DIR/rpgbot.db" ]]; then
        echo "rpgbot.db not found — running seed.py first"
        python3 "$SCRIPT_DIR/seed.py" || { echo "seed.py failed"; return 1; }
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting builder on ${HOST}:${PORT}" >> "$LOG_FILE"
    nohup python3 -m uvicorn app:app \
        --host "$HOST" \
        --port "$PORT" \
        --app-dir "$SCRIPT_DIR" \
        >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 0.6
    if _is_running; then
        echo "Started (pid $(cat "$PID_FILE")) — http://${HOST}:${PORT}"
        echo "Logs: $LOG_FILE"
    else
        echo "Failed to start — check $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

cmd_stop() {
    if ! _is_running; then
        echo "Not running"
        rm -f "$PID_FILE"
        return 0
    fi
    local pid
    pid=$(cat "$PID_FILE")
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Stopping builder (pid $pid)" >> "$LOG_FILE"
    kill "$pid"
    for i in $(seq 1 10); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid"
    fi
    rm -f "$PID_FILE"
    echo "Stopped"
}

cmd_status() {
    if _is_running; then
        echo "Running (pid $(cat "$PID_FILE")) — http://${HOST}:${PORT}"
    else
        echo "Not running"
        [[ -f "$PID_FILE" ]] && { echo "Stale PID file — removing"; rm -f "$PID_FILE"; }
    fi
}

cmd_logs() {
    local lines="${1:-50}"
    [[ -f "$LOG_FILE" ]] && tail -n "$lines" "$LOG_FILE" || echo "No log file yet"
}

cmd_tail() {
    [[ -f "$LOG_FILE" ]] && { echo "Tailing $LOG_FILE (Ctrl-C to stop)"; tail -f "$LOG_FILE"; } || echo "No log file yet"
}

case "${1:-}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_stop; cmd_start ;;
    status)  cmd_status ;;
    logs)    cmd_logs "${2:-50}" ;;
    tail)    cmd_tail ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs [N]|tail}"
        echo ""
        echo "  start    — seed DB if needed, then start server in background"
        echo "  stop     — stop server"
        echo "  restart  — stop then start"
        echo "  status   — show running state"
        echo "  logs [N] — print last N log lines (default 50)"
        echo "  tail     — follow log live"
        echo ""
        echo "Env vars: PORT (default: 5110), HOST (default: 127.0.0.1)"
        exit 1
        ;;
esac
