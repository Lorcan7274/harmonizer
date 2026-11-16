"""Ask Claude to read one layout's labels and propose canonical targets. Responses are cached on disk."""
import hashlib, json, os
from .targets import TARGETS

MODEL = "claude-opus-5-5"
SYSTEM = """You map channel labels from sleep recordings (EDF files) to canonical channel names for Luna's CANONICAL command.

You receive one header layout: every channel's label as Luna sees it, the original label, units, sampling rates, transducer and filter fields. Labels come from many labs and languages (for example Italian: torace, addome, flusso, milo, dx, sin).

For each channel choose the canonical target it should become, or "none". Rules:
- Use only the listed targets. Each target at most once per layout; if two channels fit, pick the better and give the other "none".
- Channels with no listed counterpart (for example bipolar EEG chains such as F4-C4) get "none". Not every channel needs a target.
- If a channel is an unreferenced electrode and its reference is recorded separately in this layout, put the reference channel's Luna label in "ref". Otherwise "ref" is "".
- Left/right and electrode position come only from the label. Never guess them.
- When signal evidence is given, it shows what the trace looked like in each recording. If it contradicts the label, say so in the reason and prefer "none" over a mapping the trace does not support.
- "reason" is one short sentence a sleep technologist could check, and the target must follow from it.
- Return exactly one entry for every channel listed, in the order given."""

SCHEMA = {
    "type": "object",
    "properties": {"channels": {"type": "array", "items": {
        "type": "object",
        # reason comes before target so the choice is made after the reasoning is written
        "properties": {"label": {"type": "string"}, "reason": {"type": "string"},
                       "target": {"type": "string", "enum": list(TARGETS) + ["none"]}, "ref": {"type": "string"}},
        "required": ["label", "reason", "target", "ref"], "additionalProperties": False}}},
    "required": ["channels"], "additionalProperties": False,
}


def layout_prompt(layout_id, n_rec, channels, evidence=None):
    """channels: dicts with label, original, units, rates, trans, prefilt."""
    lines = [f"Layout {layout_id}, {n_rec} recording(s).", "",
             "Canonical targets (name: kind): " + ", ".join(f"{t}: {k}" for t, k in TARGETS.items()), "", "Channels:"]
    for c in channels:
        s = (f"- label={c['label']} | original={c['original']!r} | units={c['units']} | rates_hz={c['rates']}"
             f" | transducer={c['trans']!r} | prefilter={c['prefilt']!r}")
        if evidence is not None:
            s += f" | trace_types_seen={dict(evidence.get(c['label'].upper(), {}))}"
        lines.append(s)
    if evidence is not None:
        lines += ["", "trace_types_seen counts recordings by what the signal looked like: neuro (EEG or EOG, not separable), "
                  "ecg, emg, resp, pleth, spo2, hr, hr_or_spo2, discrete, flat, unknown."]
    return "\n".join(lines)


def ask(prompt, cache_dir, labels, attempts=3):
    """Returns one entry per label. Incomplete answers are retried and never cached."""
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, hashlib.sha256((MODEL + SYSTEM + json.dumps(SCHEMA) + prompt).encode()).hexdigest()[:24] + ".json")
    if os.path.exists(path):
        return json.load(open(path))["channels"]
    import anthropic
    client = anthropic.Anthropic()
    want = sorted(labels)
    for attempt in range(attempts):
        resp = client.beta.messages.create(
            model=MODEL, max_tokens=16000, system=SYSTEM,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.stop_reason != "end_turn":
            raise RuntimeError(f"model stopped with {resp.stop_reason}")
        chans = json.loads(next(b.text for b in resp.content if b.type == "text"))["channels"]
        got = sorted(c["label"] for c in chans)
        if got == want:
            json.dump(dict(prompt=prompt, model=resp.model, channels=chans), open(path, "w"), indent=1)
            return chans
        print(f"  incomplete answer (attempt {attempt + 1}): missing {sorted(set(want) - set(got))}, extra {sorted(set(got) - set(want))}")
    raise RuntimeError("model did not return exactly one entry per channel")
