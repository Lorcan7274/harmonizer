"""Run Luna's real CANONICAL command on one EDF and return what it made."""
import lunapi as lp

_proj = None


def run_canonical(edf, rule_files, group=None, check=True):
    global _proj
    if _proj is None:
        _proj = lp.proj()
        _proj.silence(True)
    p = _proj.inst(edf)
    p.attach_edf(edf)
    cmd = "CANONICAL file=" + ",".join(rule_files)
    if group:
        cmd += f" group={group}"
    if check:
        cmd += " check"
    p.eval(cmd)
    out = {"made": {}, "unused": []}
    cs = p.table("CANONICAL", "CS")
    for _, r in cs.iterrows():
        if int(r["DEFINED"]) == 1:
            out["made"][r["CS"]] = (r.get("SIG"), r.get("REF"))
    try:
        ch = p.table("CANONICAL", "CH")
        out["unused"] = [r["CH"] for _, r in ch.iterrows() if int(r["USED"]) == 0]
    except Exception:
        pass
    return out
