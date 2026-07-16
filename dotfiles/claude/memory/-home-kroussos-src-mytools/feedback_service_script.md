---
name: Always use ./service.sh to start/stop rpg-lib services
description: In /home/kroussos/src/mytools/rpg-lib/, never spawn the library backend directly — always go through ./service.sh {start|stop|restart|status|logs|tail}. Applies to the Python library_server.py; the Vite frontend is not in scope yet.
type: feedback
originSessionId: 2513f838-f10d-4b88-a4a1-e9106c78d0c7
---
In `/home/kroussos/src/mytools/rpg-lib/`, always use `./service.sh` to start and stop services. Do not run `python3 library_server.py` directly, do not `kill <pid>` manually, do not background a process with `&` or `nohup` yourself.

**Commands the script supports:**
- `./service.sh start` — start the library backend in background (port 8000 default, env vars `DB` and `PORT` override)
- `./service.sh stop` — graceful stop with SIGTERM, SIGKILL fallback after 5s
- `./service.sh restart` — stop then start
- `./service.sh status` — is it running, and on which PID
- `./service.sh logs [N]` — tail last N lines of `logs/library.log` (default 50)
- `./service.sh tail` — follow the log live

**Why:** the script manages `.library.pid` as the lifecycle source of truth and writes timestamped start/stop entries to `logs/library.log`. Spawning `library_server.py` directly leaks a PID that `status`/`stop`/`restart` cannot see, breaking the user's ability to manage the service. The script also handles stale-PID cleanup and the SIGTERM→SIGKILL escalation.

**Scope caveat:** the script currently only manages the Python **backend** (`library_server.py`). The Vite **frontend** dev/preview servers (`npm run dev`, `npm run preview`) are NOT covered. If I need to start the frontend, either:
1. Ask the user first — they may want the script extended to cover it, or they may want to start it themselves, or
2. Use `npm run dev` / `npm run preview` directly ONLY if the user has confirmed in the current session that bypassing the script is okay.

**How to apply:** any time I catch myself about to write `python3 library_server.py`, `nohup`, `kill <pid>`, or `ps | grep library` in the rpg-lib tree, stop and reach for `./service.sh` instead. Only bypass the script if the user has explicitly said "not this time" or the action the script doesn't cover (e.g. frontend) has been confirmed.
