# Validation and details

The full record behind the summary in the [README](../README.md): how the checks were tested, how the tool works, what it found in CAP, and where it is weak.

## Results on three cohorts

| Cohort | Recordings | Header layouts | Role |
| --- | --- | --- | --- |
| CAP Sleep Database | 108 | 50 | Development. Checks and readers were built on its dev half |
| Sleep-EDF Expanded | 197 | 2 | First unseen cohort. Its dev half was used to fix what it exposed |
| HMC (Haaglanden) | 151 | 1 | Sealed until the first round of fixes was frozen, then scored once |

Every cohort is split into a fixed dev and held-out half (`harmonizer/inject.py`). HMC and Sleep-EDF use clean, standard labels, so label and trace agreement there measures the checks themselves; on CAP the answer key and the checks are not independent.

**Trace check against the header** (channels whose trace agrees with the label, flat and unchecked channels left out):

| Cohort | EEG | EOG | Chin EMG | ECG |
| --- | --- | --- | --- | --- |
| CAP | 1,023 of 1,066 | 117 of 121 | 103 of 114 | 98 of 109 |
| Sleep-EDF | 378 of 394 | 194 of 197 | 32 of 44 | none recorded |
| HMC | 566 of 604 | 267 of 302 | 96 of 151 | 139 of 150 |

**What changed after the unseen cohorts.** Run unchanged on Sleep-EDF, the original checks raised 1.99 false flags per recording. Two fixes were made on dev halves only and frozen before HMC was opened: breathing must show a spectral peak (slow drift in an eye or scalp lead no longer reads as breathing), and a label the trace cannot confirm at its sampling rate is reported as unchecked instead of as a conflict. HMC's first score then showed chin EMG confirmed in only 42 of 151 recordings, so a third fix was developed on the dev halves of all three cohorts (muscle is also judged on power above 4 Hz with mains hum removed) and scored once on the held-out halves.

| Measure | Before | After |
| --- | --- | --- |
| HMC (sealed), EEG confirmed, first two fixes | 456 of 604 | 570 of 604 |
| HMC (sealed), EOG confirmed, first two fixes | 137 of 302 | 273 of 302 |
| HMC (sealed), flags per recording, first two fixes | 2.87 | 1.21 |
| HMC held-out, chin EMG confirmed, third fix | 22 of 75 | 48 of 75 |
| HMC held-out, EEG or EOG wrongly called muscle, third fix | 12 of 450 | 19 of 450 |
| Flags per recording, held-out, all fixes: CAP / Sleep-EDF / HMC | 1.51 / 1.99 / 2.88 | 1.27 / 0.16 / 0.99 |
| Label-swap recall, CAP held-out | 88.4% | 88.6% |

Label-swap recall on the held-out halves is 88.6% on CAP, 60.5% on HMC and 12.5% on Sleep-EDF. The two lower numbers are the known limits below: EEG and EOG are one class, and Sleep-EDF has almost nothing else to swap.

**Mapping, scored through real CANONICAL** (recordings where every required signal comes out right):

| Reader | CAP dev (63) | CAP held-out (45) | Sleep-EDF (197) | HMC (151) | Confident and wrong |
| --- | --- | --- | --- | --- | --- |
| Baseline label reader, no model | 62 | 45 | 197 | 151 | 0 |
| Claude, headers only | 62 | 45 | 197 | 151 | 0 |
| Claude with signal evidence | 63 | 45 | 197 | 151 | 0 |

Before it was taught AASM-style headers (`EEG F4-M1`, `EOG E1-M2`), the baseline reader mapped none of HMC's six EEG and EOG channels. Both Claude readers map every recording of the two unseen cohorts with no change to their prompt. On CAP the signal-evidence reader was redrafted with the corrected trace evidence (17 of 50 layouts needed a new answer; 485 rules) and gets all 63 dev recordings. Its earlier draft, made when a drifting eye channel still read as breathing, had left that channel unmapped and scores 62 of 63 under the corrected key: better trace evidence gave a better mapping.

**End to end.** On all 456 recordings MNE accepted every exported channel name and type, and every BIDS table uses valid types and statuses. YASA's stager ran on one recording from each cohort using the exported picks with no per-cohort channel configuration.

**The reader itself.** On a plain EDF and on a real EDF+ file with an annotation channel, the reader gives the same channel names and sample values as MNE. Its Luna-style labels equal Luna's own on those files and on 52 labels built to exercise punctuation; before this was measured, labels with a period (`Abd.`, `Tib.`) were cleaned differently from Luna and their rules would not have matched. One full-night recording from each cohort (48 to 496 MB) gives the same channel verdicts as its excerpt.

## How it works

1. `audit`: read every EDF, compute per-channel features in 5-minute windows, type the trace (brain or eye, muscle, heartbeat, breathing, pulse wave, saturation, heart rate, fixed levels, flat) and compare with the type the label reads as.
2. `draft`: group recordings by header layout and map each layout's labels to canonical targets, by rules or by Claude, with or without the trace evidence. Every rule carries its reason and how many recordings back it.
3. `export`, `report`: write the tables and the review page. `rule`: merge a reader's rulings.
4. `scripts/score.py`: run the drafted rules through Luna's real `CANONICAL` and judge the result against the answer key.

| Path | Purpose |
| --- | --- |
| `harmonizer/cli.py` | The `harmonizer` command |
| `harmonizer/pipeline.py` | Cohort-level audit, answer key and draft |
| `harmonizer/edf.py` | Header and signal reader, windowed reads, label rewrite |
| `harmonizer/layout.py` | Group recordings by header layout |
| `harmonizer/checks.py` | Signal features, type from trace, unit check, duplicate pairs |
| `harmonizer/mapping.py` | Baseline label reader and mapping validation |
| `harmonizer/model.py` | Claude label reader, cached |
| `harmonizer/evidence.py` | Confidence from label/trace agreement |
| `harmonizer/emit.py` | Rule file, sample lists, pre-script |
| `harmonizer/export.py` | MNE, BIDS and stager tables |
| `harmonizer/report.py`, `report.html` | The review page |
| `harmonizer/scoring.py` | Verdicts against the answer key, rulings first |
| `harmonizer/inject.py` | Label-swap faults and the fixed dev/held-out split |
| `harmonizer/canon.py` | Run real CANONICAL on one EDF |
| `harmonizer/targets.py` | Canonical targets and which types a recording must get right |
| `scripts/` | `fetch_physionet.py`, `audit_cohort.py`, `retype.py`, `summarise.py`, `answer_key.py`, `draft.py`, `score.py` |
| `tests/` | Unit tests on synthetic EDFs, no data needed: `python3 -m pytest tests`. GitHub runs them on every push |
| `results/` | Audits, drafts, scores, `reports/COHORT.html` and `exports/COHORT/` for the three cohorts |

## Reproduce

```
pip install -e ".[model,score,dev]"
python3 scripts/fetch_physionet.py cap data/cap/excerpts          # 3 GB; also: hmc (1.4 GB), sleep-edf (0.3 GB)
python3 scripts/audit_cohort.py data/cap/excerpts results/cap     # about 2.5 minutes on 4 cores
python3 scripts/summarise.py results/cap held
python3 scripts/answer_key.py results/cap
python3 scripts/draft.py data/cap/excerpts results/cap results/draft_baseline baseline
python3 scripts/score.py results/draft_baseline results/cap_answer_key.csv held
export ANTHROPIC_API_KEY=...   # then model-headers into results/draft_headers, model-signals into results/draft_signals
```

Each excerpt is eight 5-minute windows spread over the recording, stored as a valid EDF with the original header. Model responses are cached in each draft's `model_cache/`, so redrafting with unchanged prompts needs no API key. For the other cohorts the audit prefix is `results/hmc` or `results/sleep-edf` and the draft directory `results/hmc_draft_baseline` or `results/sleep-edf_draft_baseline`; `score.py` takes the EDF directory as its fourth argument.

## CAP findings

- 108 recordings, 2,074 channels, 113 distinct labels. 50 layouts by label set (35 seen once); 77 when unit and sampling rate are included.
- `rbd10.edf` and `rbd11.edf` are byte-identical (same SHA-256 in PhysioNet's checksum file), so there are 107 unique recordings.
- Label and trace agree on 1,846 channels, 87 are flat, 141 are unsettled.
- Likely real header errors: where `F8-T4` and `F7-T3` appear without the rest of the temporal chain (mostly RBD files), they carry 0 to 1% of power at 0.5 to 4 Hz against 65 to 89% for the same labels elsewhere. They look like muscle channels under an EEG label. They are the first group on the CAP review page and need a reader's ruling.
- Wrong-unit headers on correctly typed EEG, ECG or EMG channels: none, at a 30-fold tolerance. Three recordings (`n13`, `n14`, `n15`) leave the unit blank.
- 30 recordings have at least one channel whose physical minimum exceeds its maximum, which inverts the trace on read. ECG is the most common.
- Three recordings hold both `ROC-LOC` and `LOC-ROC` (correlation below -0.95), three hold near-duplicate `CHIN1`/`CHIN2`.
- What the signal evidence changed for Claude (earlier draft): it mapped `TAG` to left leg EMG (French, tibial antérieur gauche), `THE` and `Flow` to airflow, and the Italian `DX1-DX2`/`SX1-SX2` leg leads in `narco1`; it moved chin EMG from `CHIN` to `CHIN.1` in `n12` because the first chin trace looked like brain activity. It also dropped four ECG leads whose traces failed the heartbeat check; at least two look like noisy but real ECG just under the threshold, so the model trusts the checks more than it should.

## Known weaknesses

- EEG and EOG are one class (`neuro`), so EEG/EOG swaps are missed. This is most of the missed swaps on every cohort.
- Chin EMG is confirmed in 64% of HMC recordings and 73% of Sleep-EDF's 100 Hz ones. Quiet chin muscle stored broadband, or sampled too slowly to keep its fast content, still reads as brain activity.
- The breathing test is a ratio of the strongest to the typical spectral value between 0.1 and 0.6 Hz. It also rises with a steep spectral slope, so it is a peak test only in practice, as measured on these three cohorts.
- Quiet leg EMG reads as `neuro`; some pulse-wave channels read as ECG; 7 to 10% of ECG leads fail the heartbeat test.
- At 1 Hz nothing separates airflow from temperature or a marker, so those channels are unchecked, not confirmed.
- The ECG polarity sign is not trustworthy yet: most CAP ECG leads come out negative, which is more likely the heuristic or the lead placement than inverted leads.
- BDF and vendor formats are not read. Gaps in a discontinuous EDF+ recording are ignored: its records are treated as consecutive.
- Whole-night behaviour was measured on one full recording per cohort, not on whole cohorts.
- Not built: an EEG polarity check (needs staging and recordings of known polarity to verify against).

## Not done yet

- Checking drafted rules against the NSRR rule file (`nsrr/common/resources/canonical/harm.txt`) is still not done: its GitLab host returned 503 on every attempt on 2026-11-14. `rules/smoke.sigs` only proves the harness runs.

## Whole nights and file formats

The audit reads eight 5-minute windows spread over each recording, the sampling it was validated on, so memory stays flat however long the recording is: a 9.6-hour, 496 MB recording takes about 7 seconds and 170 MB. `--windows 0` reads every window instead (about 96 seconds for that recording, same verdicts). EDF and EDF+ files are read, with any letter case in the extension; EDF+ annotation channels are left out, as Luna and MNE leave them out. A file that cannot be read (BDF, an annotation-only scoring file, a damaged header) is skipped and listed with the reason in `audit_errors.csv`, and the run carries on.

## What the Claude readers send

The default reader uses no model, and nothing leaves your machine. With `--reader model-headers` or `model-signals`, one request is sent per header layout, not per recording. It holds the layout number and how many recordings share it; each channel's label, unit, sampling rate, and the transducer and prefilter text from the EDF header; and, for `model-signals` only, how many recordings showed each trace type. No signal samples, file names, recording or patient identifiers, dates or paths are sent, and a test holds the code to that.

The transducer and prefilter fields are free text written by the recording system. To see every request word for word without sending anything:

```
harmonizer prompts path/to/edfs out/audit
```
