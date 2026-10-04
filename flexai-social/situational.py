"""Situational NPC responses: Clef picks the stance, a chat model voices it.

FlexAI's tables roll a social result from Role x Size x Context x Rank and never
see the situation. This module reads the situation instead:

1. ``suggest`` sends the GM's one-line situation to a decision model behind the
   Jev/SystemOne API -- by default vLLM Semantic Router's Decision-2.0-Nox-4B on
   the Spark; Cloudflare's Clef speaks the same API -- and gets back a
   probability for each of eight response stances. ``roll`` samples one by
   those weights, so an NPC can surprise the GM without going off-character.
2. ``voice_line`` asks an OpenAI-compatible chat model for one or two lines of
   dialogue in the chosen stance.

Nothing here decides anything for the GM: it returns a suggestion to read.

Endpoints (env vars, defaults are the DGX Spark LAN addresses):
    CLEF_URL     http://192.168.1.121:8005     CLEF_MODEL  Decision-2.0-Nox-4B
    CHAT_URL     http://192.168.1.147:8001/v1  CHAT_MODEL  qwen3.8-flash-next
    CAMPAIGN_DIR (unset)  -- a campaign root; enables voice/dossier lookup
"""

from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

STANCES: Dict[str, str] = {
    "helps": "Agrees to do what was asked: helps, joins or assists",
    "answers": "Gives the information asked for, willingly or grudgingly, without bargaining",
    "bargains": "Agrees only for a price, makes a counter-offer, or sets conditions",
    "questions_motives": "Challenges the party, demands justification, is suspicious, or tests them",
    "deceives": "Lies, misleads, or gives false or deliberately unrelated information",
    "ignores": "Ignores the party or brushes them off",
    "leaves": "Ends the conversation and walks away",
    "hostile": "Turns openly hostile: threatens violence or attacks",
}

STANCE_LABELS: Dict[str, str] = {
    "helps": "Helps",
    "answers": "Answers",
    "bargains": "Bargains",
    "questions_motives": "Questions motives",
    "deceives": "Deceives",
    "ignores": "Ignores",
    "leaves": "Leaves",
    "hostile": "Turns hostile",
}

NOTES_LIMIT = 2500  # characters of voice/dossier text passed to either model

Poster = Callable[[str, dict, float], dict]


class BackendError(RuntimeError):
    """A model endpoint could not be reached or answered badly."""


def _post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise BackendError(f"{url}: {e}") from e


def endpoints() -> Dict[str, str]:
    return {
        "clef_url": os.environ.get("CLEF_URL", "http://192.168.1.121:8005").rstrip("/"),
        "clef_model": os.environ.get("CLEF_MODEL", "Decision-2.0-Nox-4B"),
        "chat_url": os.environ.get("CHAT_URL", "http://192.168.1.147:8001/v1").rstrip("/"),
        "chat_model": os.environ.get("CHAT_MODEL", "qwen3.8-flash-next"),
    }


# ---------------------------------------------------------------------------
# NPC notes from a campaign directory
# ---------------------------------------------------------------------------


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def find_notes(npc: str, campaign_dir: Optional[str]) -> Tuple[str, Optional[str]]:
    """Return (text, path) for the NPC's voice file or dossier, or ("", None).

    Looks for an exact slug match first, then the first name alone, in
    voice/ (<name>_voice.md or <name>.md), docs/npcs/ and docs/distill/npcs/ — in that order, because the
    voice file is the campaign's authority on how a character speaks.
    """
    if not campaign_dir or not npc.strip():
        return "", None
    root = Path(campaign_dir).expanduser()
    full = _slug(npc)
    first = _slug(npc.split()[0]) if npc.split() else full
    for sub in ("voice", "docs/npcs", "docs/distill/npcs"):
        for stem in dict.fromkeys((full, first)):
            names = (f"{stem}_voice.md", f"{stem}.md") if sub == "voice" else (f"{stem}.md",)
            for p in (root / sub / n for n in names):
                if not p.is_file():
                    continue
                return p.read_text(encoding="utf-8", errors="replace")[:NOTES_LIMIT], str(p)
    return "", None


# ---------------------------------------------------------------------------
# Stance suggestion (decision model)
# ---------------------------------------------------------------------------


def _state(npc: str, notes: str, situation: str) -> str:
    parts = [f"A D&D game. The party is talking to {npc or 'an NPC'}."]
    if notes.strip():
        parts.append(f"What {npc or 'the NPC'} is like:\n{notes.strip()[:NOTES_LIMIT]}")
    parts.append(f"The situation right now:\n{situation.strip()}")
    return "\n\n".join(parts)


def suggest(npc: str, notes: str, situation: str, post: Poster = _post) -> dict:
    """Score every stance with the decision model. Returns {"stances": [(key, p), ...] high-first, "ms": float}."""
    if not situation.strip():
        raise ValueError("describe the situation first")
    ep = endpoints()
    body = {
        "model": ep["clef_model"],
        "state": _state(npc, notes, situation),
        "questions": {"stance": {
            "type": "choice",
            "instructions": f"How does {npc or 'the NPC'} respond to the party at this moment?",
            "criteria": STANCES,
        }},
    }
    t = time.monotonic()
    resp = post(f"{ep['clef_url']}/v1/systemone", body, 60.0)
    try:
        probs = resp["answers"]["stance"]["probabilities"]
    except (KeyError, TypeError) as e:
        raise BackendError(f"unexpected decision-model reply: {str(resp)[:200]}") from e
    ranked = sorted(((k, float(probs.get(k, 0.0))) for k in STANCES), key=lambda kv: -kv[1])
    return {"stances": ranked, "ms": (time.monotonic() - t) * 1000}


def roll(stances: List[Tuple[str, float]], rng: Optional[random.Random] = None) -> str:
    """Sample one stance by its probability."""
    rng = rng or random.Random()
    keys = [k for k, _ in stances]
    weights = [max(p, 0.0) for _, p in stances]
    if sum(weights) <= 0:
        return keys[0]
    return rng.choices(keys, weights=weights, k=1)[0]


# ---------------------------------------------------------------------------
# Voiced line (chat model)
# ---------------------------------------------------------------------------


def voice_line(npc: str, notes: str, situation: str, stance: str, post: Poster = _post) -> dict:
    """One or two lines of dialogue in the given stance. Returns {"line": str, "ms": float}."""
    if stance not in STANCES:
        raise ValueError(f"unknown stance {stance!r}")
    ep = endpoints()
    who = npc or "the NPC"
    prompt = (
        _state(npc, notes, situation)
        + f"\n\n{who} responds this way: {STANCES[stance]}.\n"
        f"Write what {who} says right now: one or two lines of spoken dialogue, in their voice, "
        "with at most one short stage direction in italics. No narration, no options, no commentary."
    )
    body = {
        "model": ep["chat_model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 200,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    t = time.monotonic()
    resp = post(f"{ep['chat_url']}/chat/completions", body, 60.0)
    try:
        line = (resp["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise BackendError(f"unexpected chat reply: {str(resp)[:200]}") from e
    return {"line": line, "ms": (time.monotonic() - t) * 1000}
