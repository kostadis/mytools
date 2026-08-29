---
name: project-narration-next-steps
description: "Read docs/design/NarrationNextSteps_handoff.md before picking up narration/voice-critic work — the ordered plan, plus the two design docs whose ownership is split."
metadata:
  node_type: memory
  type: project
  originSessionId: 5d070cc8-7585-4313-b8da-56ee146f00f3
  modified: 2026-08-12T21:26:40.559Z
---

Narration work has an ordered pickup plan on `main`:
`docs/design/NarrationNextSteps_handoff.md` (written 2026-08-11, merged in PR #280). Read it
before touching Pass 5, `/voice-critic`, or the genre config — it starts with a re-verify
block because it has a shelf life, and **its status table is already stale**: it lists §5
(the #245 capstone) as not-run, but the capstone was run on 2026-08-12 and its record is
`~/src/campaigns/Phandalin/summaries/20260729/capstone_20260729.pr284` (extensionless; it
inlines its own rendered scenes, so the corpus survived the render going to scratch).

**The old blocker is resolved and its framing inverted.** §3 was ruled 2026-08-12: option A,
the rulebook lives in the file at `paths.genre_file`. So mytools#125's D2 as written —
"read `narrate.genre`, *not* `voice/_genre.md`, they are separate copies" — targets a key
#284 deleted. #125 was implemented against the inverted target (mytools#129, CG#294,
campaigns#164, all open 2026-08-13); the correction is now a comment on #125 itself.

Two things measured while doing it that are easy to trip over again:

- **No campaign has been migrated.** `paths.genre_file` is UNSET on Phandalin,
  out-of-the-abyss and toee, so Pass 5 currently runs with **no genre directive at all** —
  and Phandalin was healthy before #284, so for that campaign the ship was a regression
  until the migration runs. Filed as CG#295. Check this first when a render reads generic.
- **A campaign can legitimately have no rule.** Phandalin's and toee's rulebooks define no
  bookkeeping/filing register at all, so the right `voice_lint` result there is *skipped*,
  not *clean*. Absent ≠ passing is the general shape of the F4 bug.

Two companion docs, with ownership deliberately split:
`Issue245Followups_handoff.md` is the execution record (per-WO specs, standing constraints,
benchmark numbers, status table); `VoiceCriticAlignment_proposal.md` is the analysis
(findings F1–F11, designs D1–D8). Don't record new status in the analysis note.

Related: [[project_245_narrate_fixes]], [[project_alias_identity_not_substitution]],
[[reference_worktree_editable_install_shadowing]].
