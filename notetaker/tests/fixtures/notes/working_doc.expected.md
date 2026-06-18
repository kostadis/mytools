# Working Doc — slides + transcript

This is a deterministic concatenation of the recovered slide content and the meeting transcript. It is the input to a single LLM render pass that produces the polished notes.

- Slides: 5 unique, in extraction order
- Utterances: 12
- Transcript span: 00:00:02 → 00:03:52

## Slides

### Slide 1 (`s001`): Project kick-off

- Goal: ship Phase 1 by end of next week
- Two engineers staffed full-time

_Visual:_ Simple title card with two-line agenda below the title.

### Slide 2 (`s002`): Architecture overview

- Single-process CLI
- Filesystem cache keyed by URL hash

### Slide 3 (`s003`): (no title)

_Raw text on slide:_

Block diagram showing capture -> extract -> understand -> synthesise pipeline with arrows. No text labels visible.

### Slide 4 (`s004`): Open questions

_Visual:_ Single-question slide with the question shown as a centred sentence.

### Slide 5 (`s005`): Next steps

- Alex writes the spec
- Bo prototypes the parser
- Cam reviews end of week

_Visual:_ Three-row table with columns Owner / Item / Deadline.

## Transcript

**Alex [00:00:02]**

Welcome everyone. Let's go through the kick-off slides.
We're aiming to ship Phase 1 by end of next week.

**Bo [00:00:30]**

Two of us full time should be enough if scope holds.

**Alex [00:01:00]**

On to the architecture. It's a single-process CLI.
Cache is keyed by URL hash, same convention as today.

**Cam [00:01:45]**

The block diagram on the next slide is the same one from the design doc.

**Alex [00:02:30]**

Open question: what retention do we want for generated notes?

**Bo [00:02:45]**

I'd say keep them indefinitely. Frames can be purged on the existing schedule.

**Cam [00:03:00]**

Agreed. We can make it configurable.

**Alex [00:03:30]**

Last slide. Alex writes the spec, Bo prototypes the parser, Cam reviews end of week.

**Bo [00:03:50]**

Sounds good.

**Cam [00:03:52]**

Works for me.
