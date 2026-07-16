---
name: feedback-host-aliases-not-ips
description: "Refer to Spark/DGX hosts by SSH alias (spark, spark2, ...) and never by IP"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e86ee47c-6b10-4ab8-88a0-8ddea332a573
---

When referring to the user's Spark hosts in memory, docs, scripts, or commands, **use the SSH alias** (`spark`, `spark2`, …) — never the raw IP address.

**Why:** the user told me explicitly to remember `spark2` is `spark2`, "not the IP address." IPs on the LAN are DHCP-assignable and can move; the SSH alias is the stable identifier and the only one anyone should be typing.

**How to apply:**
- When documenting infrastructure (e.g. [[project-spark-local-llm-setup]]), reference hosts as `spark` and `spark2`.
- When writing commands for the user to run, use `ssh spark` / `ssh spark2`, not `ssh kostadis@192.168.1.x` or `ssh gx10-46ea.local`.
- IPs and `.local` mDNS names belong only in `~/.ssh/config` (one canonical location); everything else points at the alias.
- If a new host appears in a conversation, ask the user for its alias rather than its IP.
