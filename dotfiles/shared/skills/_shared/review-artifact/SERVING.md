# Durable local review delivery

Use this reference for long Tailscale reviews, paginated queues, or returning to
saved decisions. The owning skill sets the review threshold and approval scope.
Do not replace the shared save contract or publish a private page publicly.

## Queue, page, phase

- Cap pages at 100 decision items. Each page has its own review ID, exact item
  subset, decisions destination and a membership receipt proving full coverage
  exactly once. Group bulk buttons affect only their page and score group.
- Small queues can keep separate requested Clef groups and individual questions
  on one page. Put explicit named picks in individual review; a predicted approval
  is not a named choice. Cache scores only against the complete displayed proposal,
  exact write scope and decision context; changed inputs invalidate that score.
- Keep the capability/index stable when appropriate. Current-phase page counts
  and Previous/Next navigation exclude completed phases, which belong in clearly
  labelled history. Retain earlier questions and saves as history.
- Keep the frozen question, apply map and saved decision record in durable stage
  storage. Audio and server state needed during review must outlive temporary
  job/session cleanup. Keep live capability tokens and machine-specific delivery
  configuration outside committed review records.

## Process lifetime

An execution-session identifier alone does not guarantee that a server survives
turns, tool cleanup or a disconnected shell. When a service manager is available
and a long-lived review is requested, prefer a task-specific managed process,
for example a user systemd service with `Restart=always`. Reuse a healthy existing
review service before creating another. This does not require changing the
machine's network or login configuration on every run.

Record the exact service/unit or other manager, executable, working directory,
bind IP/port, bundle manifest and decisions paths. Bind user delivery only to the
current Tailscale IPv4 address; loopback is for local tests. Keep credentials and
capability tokens out of logs shared beyond the intended review audience.

If review access fails, inspect process/service status, exit logs, current
Tailscale address, port binding and the exact capability URL before restarting.
Restart only this task's service, preserving capability and decisions files.
Restarting the daemon is not a repair for invalid assets or a malformed manifest.
For a managed service, use its manager to stop/restart it; Ctrl-C in an unrelated
terminal does not stop that service. Do not restart Tailscale or kill every Python
server when only the review process failed.

With systemd, the basic diagnostics are `systemctl --user status <review.service>`
and `journalctl --user -u <review.service> -n 40 --no-pager`; restart or stop that
exact unit. Keep the unit name in the checkpoint. On hosts without a service
manager, use the best available durable runtime and disclose its lifetime limit.

Static page content may be read on every GET, so changing that file need not
restart the server. A page manifest or asset allowlist loaded at startup needs an
explicit reload/restart. Check the actual server implementation before assuming
which data is live. Keep the server available at the review gate.

## Saved state and follow-up chat

A fresh page has empty decisions, picks and notes. To restore the same frozen
queue, validate its on-disk save through `normalize()` against its exact items
file, then hydrate all supported state: verdicts, named picks, notes and exceptions
pulled from bulk lists. Do not restore by ID alone against changed questions, and
do not use browser storage as the authoritative record. Unsaved changes may be
lost; tell the user to save before navigation.

Retain the original saved export when a later chat answer resolves Discuss or
unmarked items. Record the exact follow-up options, the GM's reply and the derived
scoped ruling separately. A “done” message triggers read-back; it does not approve
unmarked cards or override discussion notes.

Test hydration with a temporary output/fixture. Never write synthetic approvals
to a live decision endpoint. A new queue with no real save must remain unmarked.

## Verify before handoff

- GET the exact capability page; check current-phase navigation and Save to VM
  marker. Reject malformed saves and unknown item/review IDs without writing a
  decisions file. Do not infer an approval from a successful GET.
- For [audio](AUDIO.md), verify original-source and clip hashes, clip bounds and
  duration, unknown-path rejection, and byte-range seeking (206). Use short
  allowlisted clips and `preload="none"`; avoid embedding large audio collections.
- Inspect an actual narrow/mobile viewport. Wrap long file paths and quoted
  proposed text (for example, `overflow-wrap:anywhere`); check document scroll
  width against viewport/client width. A headless screenshot size can crop a
  larger layout, so use device emulation or inspect layout dimensions when unsure.
- Check executable script blocks as JavaScript and JSON data blocks as JSON;
  passing an `application/json` block to `node --check` is a test error.
- Confirm saved progress, notes and named picks survive reload/navigation in the
  temporary fixture, while the live queue remains free of synthetic choices.

Stop after handing off. Resume on the user's saved-ruling signal, not a loop
polling for decisions. UI/lifecycle changes alone do not authorize content edits.
