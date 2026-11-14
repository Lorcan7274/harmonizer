import csv, os, subprocess, sys
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harmonizer.checks import audit, channel_features, classify, label_type, pairs, signal_type, unit_scale
from harmonizer.edf import FIELDS, read_header, read_signals, read_window, rewrite_labels
from harmonizer.emit import rule_text
from harmonizer.layout import luna_labels, sanitize
from harmonizer.mapping import baseline, leg_side, validate


def write_edf(path, chans, rec_dur=1, nrec=4):
    """chans: dicts with EDF signal fields plus 'data', an int array of nrec * nsamp digital values."""
    def f(v, w):
        return str(v).ljust(w)[:w].encode("latin1")
    ns = len(chans)
    hdr = (f(0, 8) + f("X", 80) + f("X", 80) + f("01.01.01", 8) + f("00.00.00", 8) + f(256 * (ns + 1), 8)
           + f("", 44) + f(nrec, 8) + f(rec_dur, 8) + f(ns, 4))
    for name, w in FIELDS:
        hdr += b"".join(f(c.get(name, ""), w) for c in chans)
    recs = [np.concatenate([c["data"][r * c["nsamp"]:(r + 1) * c["nsamp"]] for c in chans]) for r in range(nrec)]
    with open(path, "wb") as fh:
        fh.write(hdr + np.concatenate(recs).astype("<i2").tobytes())


def chan(label, data, nsamp, unit="uV", pmin=-100, pmax=100, dmin=-1000, dmax=1000):
    return dict(label=label, unit=unit, pmin=pmin, pmax=pmax, dmin=dmin, dmax=dmax, nsamp=nsamp, data=np.asarray(data))


def test_edf_round_trip_and_label_rewrite(tmp_path):
    a = np.arange(-200, 200)
    src, dst = tmp_path / "a.edf", tmp_path / "b.edf"
    write_edf(src, [chan("C4-A1", a, 100), chan("ECG", a[::-1], 100, unit="mV", pmin=5, pmax=-5)])
    h, xs = read_signals(src)
    assert [c["label"] for c in h["ch"]] == ["C4-A1", "ECG"]
    assert h["ch"][0]["sr"] == 100
    assert np.allclose(xs[0], a * 0.1)
    assert np.allclose(xs[1], -a[::-1] * 0.005)
    rewrite_labels(src, dst, [1, 0])
    assert [c["label"] for c in read_header(dst)["ch"]] == ["ECG", "C4-A1"]
    assert np.array_equal(read_signals(dst)[1][0], xs[0])
    assert np.array_equal(read_window(src, 1, 2)[1][0], xs[0][100:300])


def test_audit_and_pairs_share_one_read(tmp_path):
    rng = np.random.default_rng(0)
    x = rng.integers(-500, 500, 400)
    write_edf(tmp_path / "a.edf", [chan("LOC-ROC", x, 100), chan("ROC-LOC", -x, 100), chan("SpO2", np.full(4, 97), 1)])
    h, xs = read_signals(tmp_path / "a.edf")
    rows = audit(h, xs)
    assert rows[2]["signal_type"] == "flat"
    assert [r["cal_inverted"] for r in rows] == [False, False, False]
    (la, lb, r), = pairs(h, xs)
    assert (la, lb) == ("LOC-ROC", "ROC-LOC") and r < -0.99


def test_luna_labels():
    assert sanitize("LOC / A2") == "LOC___A2"
    h = {"ch": [{"label": l} for l in ("C4-A1", "CHIN", "chin", "EMG-")]}
    assert luna_labels(h) == ["C4_A1", "CHIN", "chin.1", "EMG"]


@pytest.mark.parametrize("label,kind", [
    ("SAO2", "spo2"), ("TIB Dx", "emg_leg"), ("DX1-DX2", "emg_leg"), ("ROC-LOC", "eog"), ("C4-A1", "eeg"),
    ("TORACE", "effort"), ("Flusso", "flow"), ("milo", "emg"), ("EKG", "ecg"), ("CO2", "unknown"),
    ("E1-M2", "eog"), ("EOG E2-M2", "eog"), ("EEG F4-M1", "eeg"), ("Temp rectal", "temp"), ("TERMISTORE", "flow"), ("Leg1", "emg_leg"),
])
def test_label_type(label, kind):
    assert label_type(label) == kind


@pytest.mark.parametrize("unit,scale", [
    ("uV", 1.0), (" UV ", 1.0), ("µV", 1.0), ("μV", 1.0), ("ÂµV", 1.0),
    ("mV", 1e3), ("V", 1e6), ("", None), ("%", None), ("BPM", None),
])
def test_unit_scale(unit, scale):
    assert unit_scale(unit) == scale


@pytest.mark.parametrize("label,side", [
    ("tib_dx", "RAT"), ("tib_sin", "LAT"), ("sx1_sx2", "LAT"), ("dx1", "RAT"), ("leg_r", "RAT"),
    ("leg_l", "LAT"), ("rleg", "RAT"), ("leg", None), ("leg_left_right", None),
])
def test_leg_side(label, side):
    assert leg_side(label) == side


def by_label(mapping):
    return {m["label"]: (m["target"], m["ref"]) for m in mapping}


def test_baseline_numbered_pairs_and_references():
    got = by_label(baseline(["DX1", "DX2", "SX1", "SX2", "EMG1", "EMG2", "ECG", "C3", "A2", "ROC_LOC"]))
    assert got["DX1"] == ("RAT", "DX2") and got["SX1"] == ("LAT", "SX2")
    assert got["DX2"] == (None, None) and got["SX2"] == (None, None) and got["EMG2"] == (None, None)
    assert got["EMG1"] == ("EMG", "EMG2") and got["ECG"] == ("ECG", None)
    assert got["C3"] == ("C3_M2", "A2") and got["ROC_LOC"] == ("EOG", None)


def test_baseline_never_guesses_a_side():
    got = by_label(baseline(["Leg_R", "Leg_L", "LEG", "EOG"]))
    assert got == {"Leg_R": ("RAT", None), "Leg_L": ("LAT", None), "LEG": (None, None), "EOG": (None, None)}


def test_baseline_reads_aasm_headers():
    hmc = by_label(baseline(["EEG_F4_M1", "EEG_C4_M1", "EEG_O2_M1", "EEG_C3_M2", "EMG_chin", "EOG_E1_M2", "EOG_E2_M2", "ECG"]))
    assert [v[0] for v in hmc.values()] == ["F4_M1", "C4_M1", "O2_M1", "C3_M2", "EMG", "LOC", "ROC", "ECG"]
    sedf = by_label(baseline(["EEG_Fpz_Cz", "EEG_Pz_Oz", "EOG_horizontal", "Resp_oro_nasal", "EMG_submental", "Temp_rectal"]))
    assert [v[0] for v in sedf.values()] == [None, None, "EOG", "airflow", "EMG", None]
    assert by_label(baseline(["EEG_C3", "EEG_A2"]))["EEG_C3"] == ("C3_M2", "EEG_A2")


def test_validate_drops_unsafe_entries():
    clean, probs = validate([
        dict(label="C4_A1", target="C4_M1", ref=""),
        dict(label="C3_A2", target="C4_M1", ref=""),
        dict(label="EMG1", target="EMG", ref="EMG9"),
        dict(label="X", target="ECG", ref=""),
        dict(label="ECG", target="EKG", ref=""),
    ], ["C4_A1", "C3_A2", "EMG1", "ECG", "SAO2"])
    assert by_label(clean) == {"C4_A1": ("C4_M1", None), "C3_A2": (None, None), "EMG1": (None, None), "ECG": (None, None)}
    assert len(probs) == 5


def test_rule_comment_stays_on_one_line():
    m = dict(label="ECG1", ref="ECG2", target="ECG", reason="Two\nlines.")
    lines = rule_text("L01", 3, m, True, "Evidence: 3 high").splitlines()
    assert lines[0] == "% L01 (3 recordings): ECG1 / ECG2 -> ECG. Two lines. Evidence: 3 high"
    assert lines[1] == "ECG" and "  ref = ECG2" in lines and lines[-1] == "  unit = uV"


def kind(x, sr):
    return signal_type(channel_features(np.asarray(x, float), sr))[0]


def test_signal_type_on_synthetic_traces():
    rng = np.random.default_rng(1)
    t = np.arange(0, 600, 1 / 256)
    beats = 1000 * np.exp(-0.5 * (((t % 0.9) - 0.45) / 0.01) ** 2)
    assert kind(beats + rng.normal(0, 5, t.size), 256) == "ecg"
    assert kind(rng.normal(0, 30, t.size), 256) == "emg"
    tr = np.arange(0, 600, 1 / 10)
    assert kind(500 * np.sin(2 * np.pi * 0.25 * tr) + rng.normal(0, 20, tr.size), 10) == "resp"
    assert kind(np.zeros(2560), 256) == "flat"


def band_noise(rng, n, sr, lo, hi):
    from scipy import signal as sg
    x = sg.sosfiltfilt(sg.butter(4, [lo, hi], btype="band", fs=sr, output="sos"), rng.normal(0, 1, n))
    return x / x.std()


def test_drift_is_not_breathing_and_muscle_survives_drift():
    rng = np.random.default_rng(2)
    n = 600 * 256
    f = channel_features(200 * band_noise(rng, n, 256, 0.1, 0.6) + 40 * band_noise(rng, n, 256, 1, 20), 256)
    assert f["resp_frac"] > 0.6 and f["resp_peak"] < 4.5 and signal_type(f)[0] == "neuro"
    f = channel_features(60 * band_noise(rng, n, 256, 0.7, 3) + rng.normal(0, 30, n), 256)
    assert f["hf_frac"] < 0.35 and f["hf_share4"] > 0.5 and signal_type(f)[0] == "emg"


def test_slow_channels_are_left_unchecked_not_flagged():
    rng = np.random.default_rng(3)
    chs = [dict(label=l, unit="uV", sr=1.0, cal_inverted=False) for l in ("EMG submental", "Resp oro-nasal", "Temp rectal", "Event marker")]
    feats = [channel_features(rng.normal(m, 1, 2400), 1.0) for m in (3, 60, 37, 900)]
    assert [r["agree"] for r in classify(chs, feats)] == ["unchecked", "unchecked", "unchecked", "label_unread"]


def test_answer_key_keeps_reader_rulings(tmp_path):
    prefix = str(tmp_path / "cap")
    cols = ["id", "idx", "label", "unit", "sr", "label_type", "signal_type", "agree", "reason"]
    with open(prefix + "_channels.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        w.writerow(dict(id="n1", idx=0, label="F8-T4", unit="uV", sr=512, label_type="eeg", signal_type="emg",
                        agree="conflict", reason="70% of power above 25 Hz"))
    script = os.path.join(ROOT, "scripts", "answer_key.py")
    rulings = str(tmp_path / "rulings.csv")
    with open(rulings, "w") as fh:
        fh.write("id,idx,label,ruling\nn1,0,F8-T4,emg\nn9,3,GONE,eeg\n")
    out = subprocess.run([sys.executable, script, prefix, rulings], check=True, capture_output=True, text=True).stdout
    assert "1 reader rulings in the key" in out and "dropped" in out
    subprocess.run([sys.executable, script, prefix], check=True, capture_output=True)
    (row,) = csv.DictReader(open(prefix + "_answer_key.csv"))
    assert row["status"] == "unsettled" and row["reader_ruling"] == "emg"
    with open(rulings, "w") as fh:
        fh.write("id,idx,ruling\nn1,0,brain\n")
    assert subprocess.run([sys.executable, script, prefix, rulings], capture_output=True).returncode != 0
