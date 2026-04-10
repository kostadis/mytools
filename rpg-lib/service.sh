#!/bin/bash
# RPG Library service manager
# Usage: ./service.sh start|stop|restart|status|logs|tail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/.library.pid"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/library.log"
DB_PATH="${DB:-$SCRIPT_DIR/rpg_library.db}"
PORT="${PORT:-8000}"

mkdir -p "$LOG_DIR"

_is_running() {
    [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

cmd_start() {
    if _is_running; then
        echo "Already running (pid $(cat "$PID_FILE"))"
        return 1
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting library server on port $PORT" >> "$LOG_FILE"
    nohup python3 "$SCRIPT_DIR/library_server.py" \
        --db "$DB_PATH" \
        --port "$PORT" \
        >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 0.5
    if _is_running; then
        echo "Started (pid $(cat "$PID_FILE")) — logs at $LOG_FILE"
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
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Stopping library server (pid $pid)" >> "$LOG_FILE"
    kill "$pid"
    # Wait up to 5s for clean exit
    for i in $(seq 1 10); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null; then
        echo "Process didn't exit cleanly, sending SIGKILL"
        kill -9 "$pid"
    fi
    rm -f "$PID_FILE"
    echo "Stopped"
}

cmd_status() {
    if _is_running; then
        echo "Running (pid $(cat "$PID_FILE")) on port $PORT"
    else
        echo "Not running"
        [[ -f "$PID_FILE" ]] && { echo "Stale PID file — removing"; rm -f "$PID_FILE"; }
    fi
}

cmd_logs() {
    local lines="${1:-50}"
    if [[ -f "$LOG_FILE" ]]; then
        tail -n "$lines" "$LOG_FILE"
    else
        echo "No log file yet at $LOG_FILE"
    fi
}

cmd_tail() {
    if [[ -f "$LOG_FILE" ]]; then
        echo "Tailing $LOG_FILE (Ctrl-C to stop)"
        tail -f "$LOG_FILE"
    else
        echo "No log file yet at $LOG_FILE"
    fi
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
        echo "  start    — start server in background"
        echo "  stop     — stop server"
        echo "  restart  — stop then start"
        echo "  status   — show whether it is running"
        echo "  logs [N] — print last N lines of log (default 50)"
        echo "  tail     — follow log output live"
        echo ""
        echo "Env vars: DB=<path> (default: rpg_library.db), PORT=<num> (default: 8000)"
        exit 1
        ;;
esac
