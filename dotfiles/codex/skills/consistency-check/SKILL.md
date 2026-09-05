---
name: consistency-check
description: Perform consistency-check specialist work, resuming CampaignGenerator session review when a session_workflow.yaml is present.
---

For a workflow-managed session, read the [shared campaign-cycle contract](../../../shared/campaign-cycle/contract.md), then inspect the pending task with `session_workflow resume`. The shared contract owns scope, writes, provenance, submission and human gates.

Read the [specialist workflow](references/standalone.md) for the consistency-check analysis method. In managed sessions, use only its specialist reading and reasoning; submit findings/output references through the shared engine. Its standalone page generation, direct application and downstream rerender instructions do not replace the managed task or its gates. Resolve helper scripts relative to their original skill directory (one level above references), inspecting them before use.

For an explicitly standalone session without a workflow record, use that specialist workflow as authored. Do not infer historical approval when later migrating the session.
