# harmonizer

Channel audit and harmonisation for polysomnography recordings (EDF, EDF+).

Given a folder of recordings, harmonizer:

1. Classifies every channel from its signal (EEG/EOG, EMG, ECG, respiration, pulse wave, SpO2, heart rate, flat) and compares the result with the header label.
2. Maps channels to canonical names (NSRR conventions where they exist, e.g. `C4_M1`, `LOC`, `EMG`).
3. Writes channel tables for MNE, BIDS and automatic sleep stagers, Luna `CANONICAL` rules, and an HTML page for reviewing channels whose signal and label disagree.

Input files are never modified.

## How to use

```
pip install -e .
harmonizer run path/to/edfs out/ --name "My cohort"
```

Then open `out/report.html`. A whole night takes a few seconds per recording.

| In `out/` | What it is for |
| --- | --- |
| `report.html` | Review page: what was found, and each doubtful channel with previews of its trace |
| `exports/mne/ID.json` | Channel types for MNE, which otherwise reads every sleep channel as EEG |
| `exports/bids/ID_channels.tsv` | BIDS `channels.tsv` |
| `exports/staging_channels.csv` | Which EEG, EOG and chin EMG channel to give an automatic sleep stager |
| `rules.sigs`, `run.sh` | Luna `CANONICAL` rules, each with its reason |

**Use the output.** For example, automatic sleep staging with MNE and YASA:

```python
import csv, json, mne, yasa
raw = mne.io.read_raw_edf("SN001.edf", preload=True)
raw.set_channel_types(json.load(open("out/exports/mne/SN001.json"))["types"])
pick = next(r for r in csv.DictReader(open("out/exports/staging_channels.csv")) if r["id"] == "SN001")
hypnogram = yasa.SleepStaging(raw, eeg_name=pick["eeg"], eog_name=pick["eog"], emg_name=pick["emg"]).predict()
```

**Review doubtful channels.** A channel whose signal disagrees with its label is flagged, never corrected. On the review page, choose what each one really is, copy the rulings into a file called `rulings.csv`, and merge them:

```
harmonizer rule out/audit rulings.csv
```

**Optional: let Claude read unusual labels.** The default reader uses fixed rules and sends nothing anywhere. For labels it cannot read, run `pip install -e ".[model]"`, set `ANTHROPIC_API_KEY`, and add `--reader model-signals`. Only header text and summary counts are sent, never signals, file names or patient details. To see exactly what would be sent, without sending it:

```
harmonizer prompts path/to/edfs out/audit
```

## More info

Tested on three public sleep datasets, 456 recordings in all:

| Dataset | Recordings | Fully mapped | EEG confirmed | Chin EMG confirmed |
| --- | --- | --- | --- | --- |
| CAP Sleep Database | 108 | 107 | 96% | 90% |
| Sleep-EDF Expanded | 197 | 197 | 96% | 73% |
| HMC (Haaglanden) | 151 | 151 | 94% | 64% |

"Fully mapped" means every required channel type came out right when the drafted rules were run through Luna itself. "Confirmed" means the signal agrees with the label, leaving out flat channels and channels sampled too slowly to check.

- **Files.** Reads EDF and EDF+. BDF and vendor formats are not supported. A file that cannot be read is skipped and listed in `out/audit_errors.csv`.
- **Limits.** It cannot tell EEG from EOG by signal alone, chin EMG is its weakest check, and its rules have not yet been compared with NSRR's own.
- **Details.** [`docs/validation.md`](docs/validation.md) has the full results, how the checks work, the known weaknesses and how to reproduce everything. Example review pages are in `results/reports/`.
- **Tests.** `python3 -m pytest tests`. GitHub runs them on every push.
- **Licence.** MIT. If harmonizer contributes to published work, please cite it (see `CITATION.cff`).
