import csv, json, os, sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harmonizer import pipeline
from harmonizer.cli import main
from harmonizer.emit import _list_path
from harmonizer.export import channels_tsv, mne_names, mne_spec, resolve, staging_pick
from harmonizer.scoring import needed, verdict
from test_core import chan, write_edf


def audit_row(idx, label, label_type, signal_type, agree, sr=256, unit="uV"):
    return dict(id="r1", idx=str(idx), label=label, unit=unit, sr=str(sr), label_type=label_type, signal_type=signal_type,
                agree=agree, reason="evidence")


AUDIT = {"r1": [audit_row(0, "F4-C4", "eeg", "neuro", "agree"), audit_row(1, "C4", "eeg", "neuro", "agree"),
                audit_row(2, "A1", "eeg", "neuro", "agree"), audit_row(3, "CHIN", "emg", "emg", "agree"),
                audit_row(4, "CHIN", "emg", "neuro", "conflict"), audit_row(5, "EOG E1-M2", "eog", "flat", "flat"),
                audit_row(6, "EOG E2-M2", "eog", "neuro", "agree"), audit_row(7, "Temp", "temp", "slow_other", "unchecked", 1, "DegC")]}
MAPPING = dict(reader="baseline", layouts={"L01": ["r1"]}, mappings={"L01": [
    dict(label="C4", target="C4_M1", ref="A1", reason="unreferenced electrode"), dict(label="A1", target=None, ref=None, reason=""),
    dict(label="CHIN", target=None, ref=None, reason=""), dict(label="CHIN.1", target="EMG", ref=None, reason="chin"),
    dict(label="EOG_E1_M2", target="LOC", ref=None, reason=""), dict(label="EOG_E2_M2", target="ROC", ref=None, reason="")]})


def test_mne_names_follow_mne_for_repeated_labels():
    assert mne_names(["CHIN", "C4", "CHIN"]) == ["CHIN-0", "C4", "CHIN-1"]


def test_exports_for_mne_bids_and_stagers():
    rows = resolve(AUDIT, MAPPING)["r1"]
    assert [r["status"] for r in rows] == ["ok", "ok", "ok", "ok", "check", "flat", "ok", "unchecked"]
    spec = mne_spec(rows)
    assert spec["types"] == {"F4-C4": "eeg", "C4": "eeg", "A1": "eeg", "CHIN-0": "emg", "CHIN-1": "emg",
                             "EOG E1-M2": "eog", "EOG E2-M2": "eog", "Temp": "temperature"}
    assert spec["bads"] == ["EOG E1-M2"] and spec["reference"] == {"C4": "A1"} and spec["rename"]["EOG E2-M2"] == "ROC"
    tsv = list(csv.DictReader(channels_tsv(rows).splitlines(), delimiter="\t"))
    assert [(r["type"], r["units"], r["status"]) for r in tsv][-4:] == [
        ("EMG", "µV", "n/a"), ("EOG", "µV", "bad"), ("EOG", "µV", "good"), ("TEMP", "DegC", "n/a")]
    assert "header says emg, trace looks like neuro" in tsv[4]["status_description"]
    pick = staging_pick(rows)
    assert (pick["eeg"], pick["eeg_ref"]) == ("C4", "A1") and pick["eog"] == "EOG E2-M2"
    assert (pick["emg"], pick["emg_status"]) == ("CHIN-0", "ok")


def test_reader_ruling_outranks_the_trace_check():
    k = dict(label="F8-T4", label_type="eeg", trace_type="emg", status="unsettled", reader_ruling="")
    assert verdict(k, "EMG") == "unsettled" and needed([k]) == []
    k["reader_ruling"] = "emg"
    assert verdict(k, "EMG") == "right" and verdict(k, "C4_M1") == "wrong" and needed([k]) == ["emg"]
    belt = dict(label="THOR", label_type="effort", trace_type="resp", status="settled", reader_ruling="resp")
    assert verdict(belt, "thorax") == "right" and verdict(dict(belt, reader_ruling=""), "thorax") == "right"


def test_list_paths_stay_relative_inside_a_project(tmp_path):
    assert _list_path(tmp_path / "data" / "a.edf", tmp_path / "results" / "draft") == os.path.join("..", "..", "data", "a.edf")


def test_run_writes_rules_exports_and_review_page(tmp_path, capsys):
    rng = np.random.default_rng(4)
    t = np.arange(0, 60, 1 / 100)
    beats = 800 * np.exp(-0.5 * (((t % 0.9) - 0.45) / 0.01) ** 2)
    edf = tmp_path / "edf"
    edf.mkdir()
    for name in ("a", "b"):
        write_edf(edf / f"{name}.edf", nrec=60, chans=[
            chan("EEG C4-M1", rng.normal(0, 300, t.size), 100), chan("EOG E1-M2", np.convolve(rng.normal(0, 300, t.size), np.ones(20) / 20, "same"), 100),
            chan("EMG chin", beats, 100), chan("Mystery", rng.normal(0, 100, t.size), 100)])
    out = tmp_path / "out"
    main(["run", str(edf), str(out), "--name", "Test cohort", "--jobs", "1"])
    assert "2 recordings" in capsys.readouterr().out
    for f in ("rules.sigs", "report.html", "audit_answer_key.csv", "exports/channels.csv", "exports/staging_channels.csv",
              "exports/bids/a_channels.tsv", "exports/mne/b.json", "lists/L01.lst"):
        assert (out / f).exists(), f
    page = (out / "report.html").read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>") and "<title>Test cohort channel audit</title>" in page
    data = json.loads(page.split('id="audit-data">')[1].split("</script>")[0])
    flagged = {(g["label"], g["status"]) for g in data["groups"]}
    assert ("Mystery", "unread") in flagged and ("EMG chin", "check") in flagged
    item = next(g for g in data["groups"] if g["label"] == "Mystery")["items"][0]
    assert len(item["trace"]["strips"]) == 3 and max(map(abs, item["trace"]["strips"][0])) <= 100
    assert json.loads((out / "exports" / "mne" / "a.json").read_text())["types"]["EOG E1-M2"] == "eog"


def test_one_unreadable_file_does_not_stop_a_cohort(tmp_path, capsys):
    rng = np.random.default_rng(7)
    edf = tmp_path / "edf"
    edf.mkdir()
    write_edf(edf / "good.edf", [chan("EEG C4-M1", rng.normal(0, 300, 6000), 100)], nrec=60)
    (edf / "broken.edf").write_bytes(b"\x00" * 400)
    out = tmp_path / "out"
    main(["run", str(edf), str(out), "--jobs", "1"])
    assert "skipped broken: ValueError: not an EDF file" in capsys.readouterr().err
    assert (out / "audit_errors.csv").read_text().splitlines()[1].startswith("broken,")
    assert json.loads((out / "mapping.json").read_text())["layouts"] == {"L01": ["good"]}


def test_model_prompts_hold_header_text_and_counts_only(tmp_path):
    rng = np.random.default_rng(8)
    edf = tmp_path / "edf"
    edf.mkdir()
    for name in ("patient_jane_doe_1987", "patient_john_roe_1990"):
        write_edf(edf / f"{name}.edf", [chan("EEG C4-M1", rng.normal(0, 300, 6000), 100), chan("EMG chin", rng.normal(0, 300, 6000), 100)], nrec=60)
    prefix = str(tmp_path / "audit")
    pipeline.audit_cohort(str(edf), prefix, jobs=1)
    (lid, prompt), = pipeline.layout_prompts(str(edf), prefix, "model-signals")
    assert lid == "L01" and "2 recording(s)" in prompt and "EEG C4-M1" in prompt and "trace_types_seen" in prompt
    assert "patient" not in prompt and "jane" not in prompt and "1987" not in prompt and str(tmp_path) not in prompt
    assert "01.01.01" not in prompt and "X" * 3 not in prompt
    (_, headers_only), = pipeline.layout_prompts(str(edf), prefix, "model-headers")
    assert "trace_types_seen" not in headers_only
