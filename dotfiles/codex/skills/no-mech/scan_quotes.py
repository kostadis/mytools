#!/usr/bin/env python3
"""Deterministic quote census for a voice-smoothed scene extraction.

Emits EVERY quote with its speaker label and a mechanical-pattern flag. It
does not filter, rank, or decide: the flags are a floor for the reading pass
(see SKILL.md Phase 1b), never a verdict. Measured on obelisk ch10 scene 06,
the pattern below matched 3 of 47 quotes in a scene where all 47 were
mechanical -- a 6% recall that would be catastrophic if trusted.

It reports TWO independent roleplay signals, because the speaker label is not
always one. Some extractors put the NPC in the label; others keep the label
'GM' for every NPC and name them in the italic stage direction instead
(`**GM** - *as Varek Solain, asking why they came*`). Where that is the
convention, the label signal is dead for the WHOLE campaign, not just one
scene, and the direction is the signal that works.

No LLM, no network. Regex over text already on disk.
"""
import argparse, collections, glob, json, os, re, sys

# Shapes that are mechanical BY FORM. Deliberately narrow: a false positive
# here costs a human a glance, a false negative costs nothing because the
# reading pass is what actually classifies. Never add vocabulary that could
# match in-world magic (see SKILL.md, the hard invariant).
MECH = re.compile(r"""(?xi)
  \b(?:
    DC\s*\d+ | d20 | natural\s+\d+
  | roll(?:s|ed|ing)?\b | re-?roll
  | (?:perception|survival|insight|arcana|investigation|persuasion|deception|
     stealth|athletics|history|religion|medicine|nature|performance|intimidation)\s+check
  | \bcheck\b | saving\s+throw | \binitiative\b | advantage | disadvantage
  | hit\s+points? | \bHP\b | \bAC\b | armou?r\s+class
  | level\s*\d+ | \bXP\b | experience\s+points
  | quest\s*log | side\s*quest | question\s+mark | \bpointer\b | \btoken\b
  | (?:on|in)\s+the\s+map | \bthe\s+map\b | highlight | draw\s+a\s+line
  | move\s+(?:you|your|the\s+player|the\s+players)
  | next\s+week | we'?ll\s+stop | let'?s\s+stop | call\s+it\s+(?:there|here)
  | your\s+turn | per\s+hour | \bround\s+\d+
  )\b
""")
CLOCK = re.compile(r"\b\d{1,2}[.:]\d{2}\b")          # "it's almost 7.40"
BARE  = re.compile(r'^>\s*"(yes|no|yeah|yep|okay|ok|right|sure|got it|mm-?hm)[.!?]*"\s*$', re.I)

LABEL = re.compile(r'^\*\*\[?([^*\]]+?)\]?\*\*(?:\s*—\s*\*(.+?)\*)?')
# An italic direction that names who is being voiced: "*as Varek Solain, ...*",
# "*as the hooded figure, opening the message*". This is the roleplay signal
# that survives when every NPC is labelled 'GM'.
IN_CHAR = re.compile(r'^as\s+(.+?)(?:\s*,|$)', re.I)
QUOTE = re.compile(r'^>\s*"')


def scan(path, party_names=None):
    text = open(path, encoding="utf-8").read()
    if "## Voiced moments" not in text:
        return {"file": path, "error": "no '## Voiced moments' section"}
    head, body = text.split("## Voiced moments", 1)
    offset = head.count("\n") + 1

    quotes, labels, speaker, ctx = [], collections.Counter(), None, None
    roles = collections.Counter()
    for i, line in enumerate(body.split("\n"), start=offset):
        m = LABEL.match(line)
        if m:
            speaker, ctx = m.group(1).strip(), (m.group(2) or "").strip()
            continue
        if QUOTE.match(line):
            flags = []
            if MECH.search(line):  flags.append("mechanical")
            if CLOCK.search(line): flags.append("wall-clock")
            if BARE.match(line):   flags.append("bare-ack")
            labels[speaker or "(none)"] += 1
            role = None
            mrole = IN_CHAR.match(ctx or "")
            if mrole:
                role = mrole.group(1).strip()
                roles[role] += 1
                flags.append("in-character")
            quotes.append({"line": i, "speaker": speaker, "context": ctx,
                           "role": role, "text": line, "flags": flags})

    # Triage signal ONLY, and it is one-directional.
    #
    # A label naming someone OUTSIDE the party (an NPC) is strong evidence of
    # roleplay. A PARTY label is NOT: the player speaks under their character's
    # name, so "Zenvon Forepot" sits on both "I'll do a Perception" and a line
    # of real dialogue. Counting PC labels as roleplay marks every scene as
    # roleplay and the triage becomes worthless -- obelisk ch10 06 and 08 both
    # scored "likely roleplay" that way while being almost entirely mechanical.
    #
    # The ABSENCE of an NPC label is not evidence of the reverse either: ch10
    # scene 03 is a full two-hander in which every one of Daran Edermath's 55
    # lines is labelled 'GM', because the extractor never broke the NPC out.
    #
    # SECOND SIGNAL. When the label is always 'GM', the italic direction still
    # names who is being voiced. toee is the worked case: every NPC line is
    # `**GM** - *as Varek Solain, ...*`, so all six scenes of a session that is
    # half roleplay triaged as "may be all-mechanical" on the label alone.
    party = {p.strip().lower() for p in (party_names or [])}
    named = sorted(k for k in labels
                   if k and k not in ("GM", "(none)") and not k.startswith("[")
                   and k.strip().lower() not in party)
    voiced_npcs = sorted(r for r in roles if r.strip().lower() not in party)
    voiced_pcs  = sorted(r for r in roles if r.strip().lower() in party)

    if named:
        triage = f"likely roleplay — NPC speakers present: {', '.join(named)}"
    elif voiced_npcs:
        triage = ("likely roleplay — NPCs voiced in stage directions, not labels: "
                  f"{', '.join(voiced_npcs)}. The label signal is dead here; "
                  "classify on the direction.")
    else:
        triage = "REVIEW CLOSELY — no NPC speaker labels; may be all-mechanical"

    # A party character voiced under a non-PC label means the GM is also a
    # player. Cutting on the 'GM' label alone would then delete a PC's entire
    # performance. Real case: toee, where Kostadis is GM and plays Calmer, so
    # every Calmer line carries a **GM** label after players.yaml gained
    # `gm: true`.
    warnings = []
    for pc in voiced_pcs:
        n = roles[pc]
        warnings.append(f"{pc} is a PARTY character voiced under a non-PC label "
                        f"({n} quote{'s' if n != 1 else ''}) — the GM is also a "
                        "player. NEVER cut on the 'GM' label alone.")
    return {
        "file": path,
        "total_quotes": len(quotes),
        "by_speaker": dict(labels.most_common()),
        "named_non_gm_speakers": named,
        "voiced_in_directions": dict(roles.most_common()),
        "voiced_npcs": voiced_npcs,
        "voiced_party_characters": voiced_pcs,
        "in_character_quotes": sum(1 for q in quotes if "in-character" in q["flags"]),
        "flagged_mechanical": sum(1 for q in quotes
                                  if any(f != "in-character" for f in q["flags"])),
        "triage": triage,
        "warnings": warnings,
        "quotes": quotes,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="a smoothed scene .md, or a directory of them")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--quotes", action="store_true",
                    help="print every quote, not just the per-scene summary")
    ap.add_argument("--party-config", metavar="FILE", default=None,
                    help="config/party.yaml. Party character names are excluded "
                         "from the NPC-speaker signal -- without this, every "
                         "scene triages as roleplay. Strongly recommended.")
    a = ap.parse_args()

    files = (sorted(f for f in glob.glob(os.path.join(a.target, "*.md"))
                    if not f.endswith(".prev"))
             if os.path.isdir(a.target) else [a.target])
    party = []
    if a.party_config:
        import yaml
        cfg = yaml.safe_load(open(a.party_config, encoding="utf-8")) or {}
        party = [c.get("name", "") for c in (cfg.get("characters") or [])]
        print(f"party (excluded from the NPC signal): {', '.join(party)}", file=sys.stderr)
    elif not a.json:
        print("WARNING: no --party-config; PC labels will be miscounted as NPCs.",
              file=sys.stderr)
    out = [scan(f, party) for f in files]

    if a.json:
        json.dump(out, sys.stdout, indent=2, ensure_ascii=False); print(); return

    for r in out:
        base = os.path.basename(r["file"])
        if "error" in r:
            print(f"{base:44} -- {r['error']}"); continue
        print(f"\n=== {base}")
        print(f"    {r['total_quotes']} quotes, {r['flagged_mechanical']} pattern-flagged, "
              f"{r['in_character_quotes']} in-character by stage direction")
        print(f"    speakers: {r['by_speaker']}")
        if r["voiced_in_directions"]:
            print(f"    voiced:   {r['voiced_in_directions']}")
        print(f"    triage:   {r['triage']}")
        for w in r["warnings"]:
            print(f"    WARNING:  {w}")
        if a.quotes:
            for q in r["quotes"]:
                mark = ("[" + ",".join(q["flags"]) + "]") if q["flags"] else ""
                print(f"      {q['line']:>4} {(q['speaker'] or '?')[:26]:28}"
                      f" {q['text'][:96]} {mark}")
    print("\nThe flags are a FLOOR. Read every scene before ruling -- see SKILL.md Phase 1b.")


if __name__ == "__main__":
    main()
