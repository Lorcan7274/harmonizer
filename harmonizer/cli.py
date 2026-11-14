"""Command line. `harmonizer run EDF_DIR OUT_DIR` does everything; the other commands are its steps."""
import argparse, json, os, sys
from . import pipeline
from .export import write_exports
from .report import write_report


def _mapping(draft_dir):
    with open(os.path.join(draft_dir, "mapping.json")) as fh:
        return json.load(fh)


def _run(a):
    os.makedirs(a.out_dir, exist_ok=True)
    prefix = os.path.join(a.out_dir, "audit")
    s = pipeline.audit_cohort(a.edf_dir, prefix, a.jobs)
    if not s["files"]:
        sys.exit(f"no .edf files in {a.edf_dir}")
    print(f"audited {s['files']} recordings in {s['wall']:.0f}s")
    n, _, _ = pipeline.answer_key(prefix)
    d = pipeline.draft(a.edf_dir, prefix, a.out_dir, a.reader, log=lambda lid: None)
    print(f"{d['layouts']} header layouts, {d['rules']} rules drafted by the {d['reader']} reader")
    rows, mapping = pipeline.read_audit(prefix), _mapping(a.out_dir)
    write_exports(rows, mapping, os.path.join(a.out_dir, "exports"))
    r = write_report(rows, mapping, a.edf_dir, os.path.join(a.out_dir, "report.html"), a.name)
    print(f"channels: {r['counts']}; {r['queue']} need a reader; "
          f"{r['staging']['ready']} of {r['recordings']} recordings ready for automatic staging")
    print(f"open {os.path.join(a.out_dir, 'report.html')}")


def _audit(a):
    s = pipeline.audit_cohort(a.edf_dir, a.prefix, a.jobs)
    print(f"{s['files']} files, wall {s['wall']:.0f}s, cpu {s['cpu']:.0f}s")


def _draft(a):
    print(pipeline.draft(a.edf_dir, a.prefix, a.out_dir, a.reader))


def _export(a):
    write_exports(pipeline.read_audit(a.prefix), _mapping(a.draft_dir), a.out_dir or os.path.join(a.draft_dir, "exports"))


def _report(a):
    out = a.out or os.path.join(a.draft_dir, "report.html")
    write_report(pipeline.read_audit(a.prefix), _mapping(a.draft_dir), a.edf_dir, out, a.name)
    print(out)


def _rule(a):
    n, kept, dropped = pipeline.answer_key(a.prefix, a.rulings)
    print(f"{n}; {kept} reader rulings in the key")
    if dropped:
        print(f"warning: {len(dropped)} rulings name channels that are not in the audit: {dropped[:10]}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="harmonizer", description="Check what each channel of a sleep recording really is, "
                                 "draft Luna CANONICAL rules, and export channel tables for MNE, BIDS and automatic stagers.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def cmd(name, fn, help, *args):
        p = sub.add_parser(name, help=help)
        for flags, kw in args:
            p.add_argument(*flags, **kw)
        p.set_defaults(fn=fn)

    edf = (["edf_dir"], dict(help="directory of .edf files"))
    prefix = (["prefix"], dict(help="audit prefix, as given to `audit` (OUT_DIR/audit after `run`)"))
    reader = (["--reader"], dict(choices=pipeline.READERS, default="baseline", help="who reads the labels; the model readers need ANTHROPIC_API_KEY"))
    jobs = (["--jobs"], dict(type=int, default=4, help="parallel workers"))
    name = (["--name"], dict(help="cohort name shown on the review page"))
    cmd("run", _run, "audit, draft rules, export channel tables and write the review page", edf, (["out_dir"], {}), reader, jobs, name)
    cmd("audit", _audit, "run the signal checks", edf, prefix, jobs)
    cmd("draft", _draft, "draft CANONICAL rules from an audit", edf, prefix, (["out_dir"], {}), reader)
    cmd("export", _export, "write BIDS channels.tsv, MNE channel types and stager picks", prefix, (["draft_dir"], {}), (["out_dir"], dict(nargs="?")))
    cmd("report", _report, "write the review page", edf, prefix, (["draft_dir"], {}), name, (["--out"], {}))
    cmd("rule", _rule, "merge rulings copied from the review page into the answer key", prefix, (["rulings"], dict(help="CSV with id, idx, ruling")))
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
