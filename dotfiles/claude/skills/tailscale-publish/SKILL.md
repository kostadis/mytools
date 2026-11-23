---
name: tailscale-publish
description: Publish an existing local HTML page through a private Tailscale-only capability URL and keep the server available for review. Use when the user asks to serve, publish, share, or open a local page over Tailscale, especially for mobile review.
---

# Tailscale Publish

Publish the requested local HTML page on the machine's Tailscale IPv4 address. Return a clickable capability URL that works for devices on the same tailnet.

## Choose the server

- For an ordinary HTML page, use `scripts/serve_page.py` from this skill.
- For a review page that must save Approve / Reject / Discuss decisions, prefer `~/.claude/skills/_shared/review-artifact/serve_review.py` with its matching `review_items.json` and decisions destination.

Do not substitute public hosting when the user asks for Tailscale.

## Workflow

1. Resolve the exact page path and confirm it exists.
2. Obtain the first address from `tailscale ip -4`. If Tailscale is unavailable or has no IPv4 address, report that condition instead of binding broadly.
3. Bind the server to that exact Tailscale address. Use port 8765 unless it is occupied; select another unused high port when needed.
4. Reuse a healthy task-specific server. For a long review, prefer a durable managed process (such as an available user systemd service with automatic restart) rather than relying only on a tool execution session. Record its manager/unit, capability state and durable decisions paths. See `~/.claude/skills/_shared/review-artifact/SERVING.md`; use that reference for pagination, saved-state restoration and mobile checks.
5. Verify the returned capability URL loads the requested page. When practical, inspect it in Chrome (claude-in-chrome) at a narrow viewport or through its accessibility tree.
6. Return the clickable URL and identify the page being served. Keep the response brief.

The static server reads the file for every request, so rebuilding the same HTML file updates it without restarting or changing its URL. Other servers may load page manifests or asset allowlists only at startup; reload those deliberately. Keep the capability stable for the same review and leave the server available at the GM review gate.

## Security and lifecycle

- Serve one exact file behind a random capability path. Do not expose a directory listing.
- Bind to the Tailscale IPv4 address, not `0.0.0.0`, `::`, localhost, or a public interface.
- Treat the URL as private to the tailnet. Anyone on the tailnet who has it can read the page.
- Follow the normal runtime approval flow when binding a listening socket requires authorization.
- If access fails, inspect this service's status/logs, current bind address and exact URL before restarting it; do not restart Tailscale merely because the page server exited. Preserve the capability and saved decisions.
- If the user asks to stop publishing, stop its exact managed service, or send Ctrl-C to its execution session when that is the actual manager, and confirm it stopped.
- Before replacing an existing server, stop only the server associated with this publishing task.

## Commands

Static page:

```bash
python3 <skill-dir>/scripts/serve_page.py --page /absolute/path/page.html --host <tailscale-ip> --port 8765
```

Decision-saving review page:

```bash
python3 ~/.claude/skills/_shared/review-artifact/serve_review.py \
  --page /absolute/path/review.html \
  --items /absolute/path/review_items.json \
  --out /absolute/path/decisions.json \
  --host <tailscale-ip> \
  --port 8765
```
