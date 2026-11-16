"""Write the review page: what the audit found, the channels that need a reader with trace previews, and every layout's mapping."""
import json, os
from collections import Counter, defaultdict
import numpy as np
from .edf import edf_paths, n_records, read_header, read_window, rec_id
from .export import resolve, staging_pick

QUEUE = ("check", "unread")
_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report.html")
_SHELL = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
          '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n{page}</html>\n')


def _envelope(x, cols):
    edges = np.linspace(0, len(x), min(cols, len(x)) + 1).astype(int)[:-1]
    return np.minimum.reduceat(x, edges), np.maximum.reduceat(x, edges)


def previews(path, wanted, cols=160, fracs=(0.2, 0.5, 0.8)):
    """Three short samples of each wanted channel index, as min/max columns scaled to -100..100 with the span they cover."""
    h = read_header(path)
    total = n_records(path, h) * h["rec_dur"]
    wins = [read_window(path, max(0.0, min(f * total, total - 120)), 120)[1] for f in fracs]
    out = {}
    for i in wanted:
        c = h["ch"][i]
        sec = 10 if c["sr"] >= 16 else 120
        parts = [w[i][: max(2, int(sec * c["sr"]))] for w in wins]
        allx = np.concatenate(parts)
        mid = float(np.median(allx))
        half = float(max(np.percentile(allx, 99.5) - mid, mid - np.percentile(allx, 0.5))) or 1.0
        strips = []
        for x in parts:
            lo, hi = _envelope(x, cols)
            pairs = np.clip(np.stack([lo, hi], axis=1).reshape(-1) - mid, -half, half) / half * 100
            strips.append([int(v) for v in np.round(pairs)])
        out[i] = dict(strips=strips, sec=sec, span=f"{2 * half:.3g} {c['unit'].strip() or 'units'}")
    return out


def build(audit_rows, mapping, edf_dir, name, max_previews=600):
    """Everything the page shows, as one JSON-ready dict."""
    resolved = resolve(audit_rows, mapping)
    rows = [r for rs in resolved.values() for r in rs]
    picks = [staging_pick(rs) for rs in resolved.values()]
    groups, budget = defaultdict(list), max_previews
    paths = {rec_id(p): p for p in edf_paths(edf_dir)}
    for rid, rs in resolved.items():
        flagged = [r for r in rs if r["status"] in QUEUE]
        if not flagged:
            continue
        peers = {r["idx"]: next((p for p in rs if p["status"] == "ok" and p["label_type"] == r["label_type"]), None) for r in flagged}
        path = paths.get(rid)
        shown = flagged[:budget] if path else []
        budget -= len(shown)
        tr = previews(path, {r["idx"] for r in shown} | {p["idx"] for i, p in peers.items() if p}) if shown else {}
        for r in flagged:
            peer = peers[r["idx"]]
            groups[(r["label"].upper(), r["label_type"], r["signal_type"], r["status"])].append(dict(
                id=rid, idx=r["idx"], sr=f"{r['sr']:g}", unit=r["unit"].strip(), evidence=r["evidence"],
                trace=tr.get(r["idx"]), peer=dict(tr[peer["idx"]], label=peer["label"]) if peer and r["idx"] in tr else None))
    layouts = []
    for lid, ids in mapping["layouts"].items():
        if not ids or ids[0] not in resolved:
            continue
        tally = defaultdict(Counter)
        for rid in ids:
            for r in resolved.get(rid, []):
                tally[r["luna"].upper()][r["status"]] += 1
        layouts.append(dict(id=lid, recs=ids, rows=[dict(label=r["label"], kind=r["kind"], target=r["target"], ref=r["ref"],
                                                         reason=r["reason"], tally=dict(tally[r["luna"].upper()])) for r in resolved[ids[0]]]))
    ordered = sorted(groups.items(), key=lambda kv: (kv[0][3] != "check", -len(kv[1]), kv[0]))
    first = {k: next(r["label"] for r in rows if r["label"].upper() == k[0]) for k in groups}
    return dict(name=name, reader=mapping.get("reader", "baseline"), recordings=len(resolved), channels=len(rows),
                counts=dict(Counter(r["status"] for r in rows)), mapped=sum(bool(r["target"]) for r in rows),
                queue=sum(len(v) for v in groups.values()),
                staging=dict(ready=sum(all(p[k + "_status"] == "ok" for k in ("eeg", "eog", "emg")) for p in picks)),
                groups=[dict(label=first[k], says=k[1], looks=k[2], status=k[3], items=v) for k, v in ordered], layouts=layouts)


def render(data, standalone=True):
    """The page for `data`. standalone=False gives the bare fragment, for hosts that add their own document shell."""
    with open(_TEMPLATE, encoding="utf-8") as fh:
        page = fh.read()
    title = "".join(ch for ch in data["name"] if ch not in "<>&") + " channel audit"
    page = page.replace("__TITLE__", title).replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("</", "<\\/"))
    return _SHELL.format(page=page) if standalone else page


def write_report(audit_rows, mapping, edf_dir, out_path, name=None, standalone=True):
    data = build(audit_rows, mapping, edf_dir, name or os.path.basename(os.path.abspath(edf_dir)))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(render(data, standalone))
    return data
