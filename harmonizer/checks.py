"""Per-channel signal checks. Plain functions, no model. Thresholds come from physiology, not from CAP."""
import re
import numpy as np
from scipy import signal as sg

UNIT_TO_UV = {"uv": 1.0, "mv": 1e3, "v": 1e6}


def unit_scale(unit):
    """Factor from a declared unit to uV, or None if it is not a voltage unit. The micro sign counts as u."""
    u = unit.strip().lower()
    for micro in ("\u00e2\u00b5", "\u00b5", "\u03bc"):
        u = u.replace(micro, "u")
    return UNIT_TO_UV.get(u)


def _bp(x, sr, lo, hi, order=3):
    hi = min(hi, 0.45 * sr)
    if lo >= hi:
        return np.zeros_like(x)
    sos = sg.butter(order, [lo, hi], btype="band", fs=sr, output="sos")
    return sg.sosfiltfilt(sos, x)


def _band(f, p, lo, hi):
    m = (f >= lo) & (f < hi)
    return float(p[m].sum()) if m.any() else 0.0


def beats(x, sr):
    """Detect QRS-like peaks. Returns regularity stats and the sign of the dominant deflection."""
    y = _bp(x, sr, 8, 20)
    env = np.abs(y)
    thr = 0.35 * np.percentile(env, 99.5)
    if thr <= 0:
        return dict(rr_med=np.nan, rr_cv=np.nan, spike=0.0, pol=0.0, nbeats=0)
    pk, _ = sg.find_peaks(env, height=thr, distance=max(1, int(0.3 * sr)))
    if len(pk) < 10:
        return dict(rr_med=np.nan, rr_cv=np.nan, spike=0.0, pol=0.0, nbeats=len(pk))
    rr = np.diff(pk) / sr
    med = float(np.median(rr))
    cv = float(np.median(np.abs(rr - med)) / med)
    spike = float(np.median(env[pk]) / (np.median(env) + 1e-12))
    z = _bp(x, sr, 1, 40)
    w = max(1, int(0.04 * sr))
    ext = []
    for p in pk[:2000]:
        seg = z[max(0, p - w): p + w + 1]
        ext.append(seg[np.argmax(np.abs(seg))])
    pol = float(np.mean(np.sign(ext)))
    return dict(rr_med=med, rr_cv=cv, spike=spike, pol=pol, nbeats=len(pk))


def _periodicity(x, sr, lo, hi, lag_lo, lag_hi, target_sr):
    """Peak of the normalised autocorrelation of the band-passed trace within a lag range."""
    q = max(1, int(sr // target_sr))
    y = _bp(x, sr, lo, hi)[::q]
    y = y - y.mean()
    n = len(y)
    if n < 16 or y.std() == 0:
        return 0.0
    spec = np.fft.rfft(y, 2 * n)
    ac = np.fft.irfft(spec * np.conj(spec))[:n]
    ac /= ac[0]
    a, b = int(lag_lo * sr / q), int(lag_hi * sr / q)
    return float(ac[a:b + 1].max()) if b > a else 0.0


def window_features(x, sr):
    f = dict(sr=sr)
    f["std"] = float(np.std(x))
    f["median"] = float(np.median(x))
    f["p01"], f["p99"] = (float(v) for v in np.percentile(x, [1, 99]))
    _, counts = np.unique(x, return_counts=True)
    f["top5"] = float(np.sort(counts)[-5:].sum() / len(x))
    f["nonneg"] = float(np.mean(x >= 0))
    f["iqr"] = float(np.subtract(*np.percentile(x, [75, 25])))
    if f["std"] == 0:
        return f
    if sr >= 4:
        nper = int(min(len(x), sr * 60))
        fr, p = sg.welch(sg.detrend(x), fs=sr, nperseg=nper)
        tot = _band(fr, p, 0.05, sr / 2)
        f["resp_frac"] = _band(fr, p, 0.1, 0.6) / (tot + 1e-30)
        m = (fr >= 0.1) & (fr < 0.6)
        f["resp_peak"] = float(p[m].max() / (np.median(p[m]) + 1e-30)) if m.any() else 0.0
        f["card_frac"] = _band(fr, p, 0.6, 3.0) / (tot + 1e-30)
        f["resp_ac"] = _periodicity(x, sr, 0.1, 0.6, 2, 8, 4)
    if sr >= 50:
        fr, p = sg.welch(sg.detrend(x), fs=sr, nperseg=int(4 * sr))
        top = min(sr / 2, 100)
        tot = _band(fr, p, 0.5, top)
        f["slow_frac"] = _band(fr, p, 0.5, 4) / (tot + 1e-30)
        f["alpha_sigma_frac"] = _band(fr, p, 8, 16) / (tot + 1e-30)
        f["hf_frac"] = _band(fr, p, 25, top) / (tot + 1e-30)
        f["mains50"] = _band(fr, p, 49, 51) / (tot + 1e-30)
        f["mains60"] = _band(fr, p, 59, 61) / (tot + 1e-30)
        # slow drift and mains hum are not physiology, so muscle is also judged on what is left
        fast = (fr >= 4) & (fr < top) & ~(((fr > 48) & (fr < 52)) | ((fr > 58) & (fr < 62)))
        f["hf_share4"] = float(p[fast & (fr >= 25)].sum() / (p[fast].sum() + 1e-30))
        f.update(beats(x, sr))
        f["card_ac"] = _periodicity(x, sr, 0.5, 5, 0.4, 1.5, 25)
        f["rms_05_30"] = float(np.std(_bp(x, sr, 0.5, 30)))
    return f


def combine_windows(fs):
    """Median of each feature over a channel's windows."""
    out = {}
    for k in sorted(set().union(*fs)):
        vals = [f[k] for f in fs if k in f and not np.isnan(f[k])]
        out[k] = float(np.median(vals)) if vals else np.nan
    out["flat_windows"] = float(np.mean([f["std"] == 0 for f in fs]))
    return out


def channel_features(x, sr, win_sec=300):
    n = int(win_sec * sr)
    wins = [x[i:i + n] for i in range(0, len(x) - n + 1, n)] or [x]
    return combine_windows([window_features(w.astype(float), sr) for w in wins])


RESP_PEAK_MIN = 4.5
# below this sampling rate the trace cannot show what the label claims, so the channel is left unchecked
MIN_SR = {"eeg": 50, "eog": 50, "emg": 50, "emg_leg": 50, "snore": 50, "pleth": 50, "ecg": 100, "effort": 4, "flow": 4}


def signal_type(f, skip_ecg=False):
    """Coarse type from the trace alone. Returns (type, reason)."""
    if f["std"] == 0 or f["flat_windows"] >= 0.75:
        return "flat", "no variation"
    sr = f["sr"]
    if f["top5"] > 0.97 and sr <= 64 and not (35 <= f["median"] <= 130 and sr <= 16):
        return "discrete", f"{f['top5']:.0%} of samples in 5 levels"
    if sr <= 16 and f.get("resp_frac", 0) < 0.5:
        if 80 <= f["median"] <= 100.5 and f["p99"] <= 101:
            if f["iqr"] > 3:
                return "hr_or_spo2", f"median {f['median']:.0f}, IQR {f['iqr']:.0f}"
            return "spo2", f"median {f['median']:.0f}, capped at 100"
        if 35 <= f["median"] <= 130:
            return "hr", f"median {f['median']:.0f}"
        return "slow_other", f"median {f['median']:.3g}"
    if sr >= 50:
        regular = 0.33 <= f.get("rr_med", 0) <= 1.5 and f.get("rr_cv", 1) < 0.12
        # needs >=100 Hz to resolve a QRS, and must not be muscle-dominated with beats riding on top
        if regular and f["spike"] > 12 and sr >= 100 and f["hf_frac"] < 0.15 and not skip_ecg:
            return "ecg", f"beats every {f['rr_med']:.2f}s, spike ratio {f['spike']:.0f}"
        if f.get("card_frac", 0) > 0.6 and f["hf_frac"] < 0.05 and f["card_ac"] > 0.5:
            return "pleth", f"{f['card_frac']:.0%} of power at pulse rate"
    # breathing is periodic, so it must show a spectral peak; slow drift in an eye or scalp lead does not
    if f.get("resp_frac", 0) > 0.6 and f.get("resp_peak", 0) >= RESP_PEAK_MIN:
        return "resp", f"{f['resp_frac']:.0%} of power at 0.1-0.6 Hz"
    if sr >= 50:
        if f["hf_frac"] > 0.35:
            return "emg", f"{f['hf_frac']:.0%} of power above 25 Hz"
        if f.get("hf_share4", 0) > 0.5:
            return "emg", f"{f['hf_share4']:.0%} of the power above 4 Hz lies above 25 Hz"
        return "neuro", f"{f['slow_frac']:.0%} of power at 0.5-4 Hz"
    return "unknown", ""


LABEL_RULES = [
    ("spo2", r"sao2|spo2"), ("stat", r"stat"), ("hr", r"^hr$|^pr$|pulse|heart rate"),
    ("pleth", r"pleth"), ("pos", r"posi"), ("light", r"light"), ("temp", r"temp"),
    ("snore", r"mic|sound|snore"), ("ecg", r"ecg|ekg"),
    ("effort", r"tora|thor|ad+ome|abdo"), ("flow", r"flus|flow|can+ula|termis|nasal"),
    ("emg_leg", r"tib|^[sd]x\d|^dx|^sx|leg"), ("emg", r"emg|chin|milo|deltoid"),
    ("eog", r"roc|loc|eog|(^|[^a-z0-9])e[12]([^0-9]|$)"),
    ("eeg", r"eeg|(^|[^a-z])(fp|af|f|fc|c|cp|p|po|o|t|a|m)\d"),
]
COMPATIBLE = {"eeg": {"neuro"}, "eog": {"neuro"}, "emg": {"emg"}, "emg_leg": {"emg"},
              "ecg": {"ecg"}, "effort": {"resp"}, "flow": {"resp"}, "spo2": {"spo2", "hr_or_spo2"}, "hr": {"hr", "hr_or_spo2"},
              "pleth": {"pleth"}, "pos": {"discrete"}, "stat": {"discrete"}, "light": {"discrete"},
              "snore": {"emg"}}


def label_type(label):
    s = label.lower()
    for t, pat in LABEL_RULES:
        if re.search(pat, s):
            return t
    return "unknown"


# plausible amplitude in uV once the declared unit is applied: (low, high) on the named feature
AMP_RANGE = {"neuro": ("rms_05_30", 2, 300), "ecg": ("p99", 100, 5000), "emg": ("std", 0.3, 500)}


def unit_check(sig_type, f, unit):
    k = unit_scale(unit)
    if sig_type not in AMP_RANGE:
        return "n/a", None
    if k is None:
        return "no_unit", None
    feat, lo, hi = AMP_RANGE[sig_type]
    v = abs(f[feat]) * k
    if v < lo / 30 or v > hi * 30:
        return "conflict", v
    return "ok", v


def classify(chs, feats):
    """chs: dicts with label, unit, sr, cal_inverted. feats: matching feature dicts."""
    typed = [signal_type(f) for f in feats]
    # the ECG lead is the channel where beats stand out most; weaker beat trains elsewhere are artefact
    best = max([f["spike"] for f, t in zip(feats, typed) if t[0] == "ecg"], default=0)
    rows = []
    for i, (c, f) in enumerate(zip(chs, feats)):
        st, why = typed[i]
        artefact = st == "ecg" and f["spike"] < 0.5 * best
        if artefact:
            st, why = signal_type(f, skip_ecg=True)
            why += "; carries heartbeat artefact"
        lt = label_type(c["label"])
        if st == "flat":
            agree = "flat"
        elif lt == "unknown":
            agree = "label_unread"
        elif st in COMPATIBLE.get(lt, ()):
            agree = "agree"
        else:
            agree = "unchecked" if lt not in COMPATIBLE or c["sr"] < MIN_SR.get(lt, 0) else "conflict"
        us, uv = unit_check(st, f, c["unit"])
        rows.append(dict(idx=i, label=c["label"], unit=c["unit"], sr=c["sr"], label_type=lt, signal_type=st,
                         reason=why, agree=agree, unit_status=us, amp_uv=uv, cal_inverted=c["cal_inverted"],
                         ecg_pol=f.get("pol") if st == "ecg" else None, ecg_artefact=artefact, feat=f))
    return rows


def audit(h, xs):
    """Type every channel of a recording loaded with edf.read_signals."""
    for c in h["ch"]:
        c["cal_inverted"] = (c["pmax"] < c["pmin"]) != (c["dmax"] < c["dmin"])
    feats = [channel_features(x, c["sr"]) for c, x in zip(h["ch"], xs)]
    return classify(h["ch"], feats)


class PairStats:
    """Running correlation between same-rate channels, fed one block of the recording at a time."""

    def __init__(self, chs):
        self.chs, self.groups, self.acc = chs, {}, {}
        for i, c in enumerate(chs):
            if c["sr"] >= 50:
                self.groups.setdefault(c["sr"], []).append(i)

    def add(self, xs):
        for sr, idx in self.groups.items():
            if len(idx) < 2:
                continue
            m = np.vstack([xs[i] for i in idx]).astype(float)
            if sr not in self.acc:
                # a fixed shift keeps the sums small; correlation does not depend on it
                self.acc[sr] = dict(shift=m.mean(axis=1, keepdims=True), n=0, s=np.zeros(len(idx)), ss=np.zeros((len(idx),) * 2))
            a = self.acc[sr]
            m = m - a["shift"]
            a["n"] += m.shape[1]
            a["s"] += m.sum(axis=1)
            a["ss"] += m @ m.T

    def pairs(self, thr=0.95):
        out = []
        for sr, idx in self.groups.items():
            a = self.acc.get(sr)
            if not a:
                continue
            cov = a["ss"] - np.outer(a["s"], a["s"]) / a["n"]
            var = np.diag(cov)
            for i in range(len(idx)):
                for j in range(i + 1, len(idx)):
                    if var[i] > 0 and var[j] > 0 and abs(cov[i, j]) >= thr * np.sqrt(var[i] * var[j]):
                        out.append((idx[i], idx[j], round(float(cov[i, j] / np.sqrt(var[i] * var[j])), 6)))
        return [(self.chs[i]["label"], self.chs[j]["label"], r) for i, j, r in sorted(out)]


def pairs(h, xs, thr=0.95):
    """Same-rate channel pairs whose traces are near-identical or near-inverted."""
    acc = PairStats(h["ch"])
    acc.add(xs)
    return acc.pairs(thr)


def audit_file(path, win_sec=300, max_windows=8):
    """Audit one EDF a window at a time, so memory stays flat however long the recording is.

    A recording longer than max_windows windows is sampled at that many windows spread over the night,
    the sampling the checks were validated on; max_windows=0 reads every window. Returns (header, rows, pairs).
    """
    from .edf import read_blocks, read_header
    h = read_header(path)
    if not h["ch"]:
        raise ValueError("no signal channels (an annotation-only EDF+ file?)")
    for c in h["ch"]:
        c["cal_inverted"] = (c["pmax"] < c["pmin"]) != (c["dmax"] < c["dmin"])
    wins, acc = [], PairStats(h["ch"])
    for xs in read_blocks(path, h, win_sec, max_windows):
        acc.add(xs)
        wins.append((len(xs[0]) if xs else 0, [window_features(x.astype(float), c["sr"]) for c, x in zip(h["ch"], xs)]))
    if not wins:
        raise ValueError("no data records")
    # a short last window is dropped, as channel_features does, unless it is all there is
    whole = [f for n, f in wins if n == wins[0][0]]
    feats = [combine_windows([f[i] for f in whole]) for i in range(len(h["ch"]))]
    return h, classify(h["ch"], feats), acc.pairs()
