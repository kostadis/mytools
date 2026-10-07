# Contextual dialogue editing: permissions and lessons

Read this before reviewing a scene. These lessons come from the three-scene,
nine-output A/B/C experiment archived in campaigns PR #232 for CG #387.
They are editing guidance, not a classifier or a guarantee of future quality.

## The permitted edit

Read dialogue in its scene. Join fragments from the same speaker, remove
accidental duplication, or clarify a question only when the reviewed extraction
unambiguously establishes its intended meaning. Choose the smallest useful
rewrite. Leave effective lines alone; there is no target edit count, length,
dialogue percentage, or level of elegance.

The extraction is evidence for events, wording, attribution, and uncertainty.
The existing narration is the text being edited, not independent evidence for
new facts. Voice notes guide diction and perspective; example dialogue and
backstory are never new material for this scene.

The editing brief permits bounded changes to **derived narration** despite
generic verbatim-copy instructions in a reference. It never permits rewriting
the transcript/extraction, changing speakers, inventing responses, or treating
edited prose as a verbatim record.

Keep descriptive and inner prose intact. Small adjacent attribution or
punctuation changes necessary to a dialogue edit are permissible proposals,
shown separately. Broad tense corrections and integrated prose editing belonged
to experimental C, not this skill. Do not automatically stack A → B → C.

## What the experiment taught

| Case | Editorial lesson |
| --- | --- |
| Zenvon, Obelisk scene 1 | B merged “more effort. For the same output.” into a single sentence. The separate landing is part of the performance; preserve it. |
| Zenvon | B made “At the ravine?” an assertion. Preserve confirmation, questions, and degrees of certainty. |
| Valphine, Phandalin scene 2 | “over. Yeah” might be radio-play texture. Ambiguity is a GM ruling, not permission to delete filler. |
| Vukradin, Phandalin scene 1 | The tide calculation can become readable while keeping the wrong first answer, self-correction, and emphatic final “Six.” Removing those beats would falsify the performance. |
| Vukradin | Valphine's “What… What do I?” could be clarified because the extraction explicitly says she asks what she is expected to know. The same completion without that evidence would be invented. |
| Vukradin | Preserve his pleasure in the studio, charitable restraint, and Old Hesp reflection. Sincere inner voice must not be edited into cynicism or factual summary. |
| All three | Repetition may be emphasis, as in “We're gonna get it back” twice. Two speakers each saying “Yes” express separate agreement. A duplicated sentence inside one quote can still be accidental. Read speaker and intent. |

For Zenvon, preserve comprehensible ESL wording, formal diction, unknown enemy
count/distances, and the boundary between intending Pip's movement and doing it.
For Valphine, preserve analytical inner voice, the final magical-disinterest
exchange, Sending Stone communication, uncertainty about the spell, and the
distinction between remembering a purpose and losing willingness to pursue it.

The inherited pike/bike problem was a spoken misunderstanding rendered as inner
thought in the original draft. None of the editing arms repaired it. Flag such
missing interactions for a separate coverage review; don't reconstruct them as
part of a dialogue cleanup.

Never repair unclear speaker attribution by guessing. A player at the table is
not necessarily a character physically present. Preserve remote communication
only where the source establishes it. Keep GM descriptions and NPC speech
distinct, and do not turn table instructions into fictional speech.

## What has and has not been validated

The archived comparison used one response per approach per scene, all recorded
as gpt-6-astra with medium reasoning. B best supported a dedicated dialogue
pass; C sometimes improved the whole passage. The prompt author also reviewed
the results. This was not a blinded or repeated reliability evaluation.

The current skill uses B's permissions with the review-derived cadence
safeguards above. It operates through exact proposals in the current
conversation, not an identical replay of the historical full-scene runner.
Do not claim that this amended skill has inherited the experiment's results.

Phandalin used selected character-perspective sections and local generic-rule
adjustments; Obelisk used full declared voice notes and register policy. Record
what the current run reads, rather than claiming those different input stacks
were identical to current production narration.

The accepted narration-v1 prompt belongs to generation, before this skill. CG's
shared single-scene and bundled narration now use that writing brief; the skill
itself does not install or select it. Check the generator and its prompt log
when working with older versions. The 17 passing archive helper tests establish
preservation/reproduction properties, not voice quality.

## Pinned evidence

- [CG #387](https://github.com/kostadis/CampaignGenerator/issues/387) — rationale and proposed cadence amendments.
- [Campaigns PR #232](https://github.com/kostadis/campaigns/pull/232) — consolidated archive.
- [Complete review](https://github.com/kostadis/campaigns/blob/0355cdd28179650cf11ecb4435e4841fbe61d54c/experiments/sd-narrate/dialogue-edit-tests/review.md).
- [Tested B instruction](https://github.com/kostadis/campaigns/blob/0355cdd28179650cf11ecb4435e4841fbe61d54c/experiments/sd-narrate/prompts/approach_b.md) and [common editor brief](https://github.com/kostadis/campaigns/blob/0355cdd28179650cf11ecb4435e4841fbe61d54c/experiments/sd-narrate/prompts/editor_common.md).
- [Frozen fixtures](https://github.com/kostadis/campaigns/tree/0355cdd28179650cf11ecb4435e4841fbe61d54c/experiments/sd-narrate/fixtures) and [consolidation verification](https://github.com/kostadis/campaigns/blob/0355cdd28179650cf11ecb4435e4841fbe61d54c/experiments/sd-narrate/VERIFICATION.md).

These references preserve provenance. The guidance above is sufficient to run
the skill without network access; read full frozen scenes for regression work,
not just selected passages or this table.
