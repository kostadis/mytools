---
name: reference-github-label-set
description: "Canonical shared GitHub label set standardized across kostadis repos (CampaignGenerator, mytools, turbovecdb)"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 906f9907-b713-4afd-8297-a169e4536564
---

Kostadis standardizes the **same 19-label set** across his GitHub repos so labels are consistent at high code-generation velocity. Applied 2026-06-19 to `kostadis/CampaignGenerator`, `kostadis/mytools`, `kostadis/turbovecdb` (verified identical via diff).

**Defaults kept (9):** bug, enhancement, documentation, question, duplicate, wontfix, invalid, good first issue, help wanted

**Added — type (4):** refactor (1d76db), tech-debt (d93f0b), infra (0e8a16), test (bfd4f2)
**Added — priority (3):** priority:high (b60205), priority:med (fbca04), priority:low (c2e0c6)
**Added — status (3):** blocked (e99695), needs-design (5319e7), wip (fef2c0)

Idempotent sync for a new/other repo — `gh label create "<name>" --color <hex> --description "..." --force -R kostadis/<repo>` per label (the 10 added ones). Re-running is safe; `--force` updates rather than errors.
