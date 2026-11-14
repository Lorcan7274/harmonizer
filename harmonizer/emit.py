"""Write the three outputs: CANONICAL rule file, one sample list per layout, and a Luna pre-script."""
import os
from .targets import TARGETS, VOLTAGE


def rule_text(layout_id, n_rec, m, voltage_units_ok, note):
    lines = [f"% {layout_id} ({n_rec} recordings): {m['label']}" + (f" / {m['ref']}" if m["ref"] else "") +
             f" -> {m['target']}. {m['reason']}. {note}",
             m["target"], " group:", f"  {layout_id}", " req:", f"  sig = {m['label']}"]
    if m["ref"]:
        lines.append(f"  ref = {m['ref']}")
    if TARGETS[m["target"]] in VOLTAGE and voltage_units_ok:
        lines += ["  unit = uV", "  unit = mV", "  unit = V", " set:", "  unit = uV"]
    return "\n".join(lines) + "\n"


def write_outputs(out_dir, layouts, mappings, notes, units_ok, prescript_lines):
    """layouts: id -> (key, paths). mappings: id -> mapping. notes: (id, label) -> evidence note."""
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "rules.sigs"), "w") as fh:
        fh.write("% Drafted CANONICAL rules. One group per header layout; run each layout's sample list with its group.\n\n")
        for lid, (_, paths) in layouts.items():
            for m in mappings[lid]:
                if m["target"]:
                    ok = units_ok.get((lid, m["label"].upper()), False)
                    fh.write(rule_text(lid, len(paths), m, ok, notes.get((lid, m["label"].upper()), "")) + "\n")
    os.makedirs(os.path.join(out_dir, "lists"), exist_ok=True)
    for lid, (_, paths) in layouts.items():
        with open(os.path.join(out_dir, "lists", f"{lid}.lst"), "w") as fh:
            for p in paths:
                fh.write(f"{os.path.basename(p)[:-4]}\t{os.path.abspath(p)}\n")
    with open(os.path.join(out_dir, "prescript.txt"), "w") as fh:
        fh.write("% Luna pre-script. Every line is a suggestion left commented out: nothing is auto-corrected.\n")
        fh.write("\n".join(prescript_lines) + "\n")
    with open(os.path.join(out_dir, "run.sh"), "w") as fh:
        fh.write("#!/bin/sh\n# one CANONICAL run per layout, because the group is chosen per run\n")
        for lid in layouts:
            fh.write(f"luna lists/{lid}.lst -o {lid}.db -s 'CANONICAL file=rules.sigs group={lid} drop-originals'\n")
