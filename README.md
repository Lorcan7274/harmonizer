# harmonizer

Channel auditor for sleep recordings: checks what each channel is against what the EDF header claims, and (later) drafts Luna CANONICAL rules for layouts existing rules miss.

## Status

Built: EDF reader, layout grouping, per-channel signal checks, label-swap injector, evidence-based confidence, a rule drafter that writes the three output files, a scorer that runs the drafted rules through Luna's real `CANONICAL` via `lunapi`, and two Claude label readers (headers only, and headers plus signal evidence), both run on CAP. Not built: the EEG polarity check (needs staging) and stage 1 against the NSRR rule file.

## Draft and score

```
python3 scripts/draft.py data/cap/excerpts results/cap results/draft_baseline baseline
python3 scripts/score.py results/draft_baseline results/cap_answer_key.csv all
export ANTHROPIC_API_KEY=...   # then the two model readers
python3 scripts/draft.py data/cap/excerpts results/cap results/draft_headers model-headers
python3 scripts/draft.py data/cap/excerpts results/cap results/draft_signals model-signals
```

Each draft directory holds `rules.sigs` (one group per layout, reason and evidence as a comment on every rule), `lists/Lnn.lst` (paths relative to the draft directory), `prescript.txt` (suggestions, all commented out), `run.sh` (runs from any directory), `confidence.csv` and `mapping.json`. Model responses are cached in `model_cache/`, so redrafting with unchanged prompts needs no API key.

Results on CAP (recordings where every required signal comes out right through real CANONICAL, out of 63 dev and 45 held-out):

| Reader | Dev (63) | Held-out (45) | Confident and wrong |
| --- | --- | --- | --- |
| Baseline label reader, no model | 62 | 45 | 0 |
| Model, headers only | 62 | 45 | 0 |
| Model with signal evidence | 63 | 45 | 0 |

Test A holds: adding signal evidence does no worse than headers alone on either half. These scores are weak evidence because the answer key comes from the same checks, so "confident and wrong" cannot be large until a reader settles the unsettled rows. The held-out half was seen once before the completeness and reason-first fixes, so it is not fully untouched.

What the signal evidence changed: it mapped `TAG` to left leg EMG (French, tibial antérieur gauche), `THE` and `Flow` to airflow, and the Italian `DX1-DX2`/`SX1-SX2` leg leads in `narco1`; it moved chin EMG from `CHIN` to `CHIN.1` in `n12` because the first chin trace looked like brain activity. It also dropped four ECG leads (`sdb2`, `nfle32`, `narco2`, `narco3`) whose traces failed the heartbeat check. At least `nfle32` and `sdb2` look like noisy but real ECG just under the threshold, so the model trusts the checks more than it should.

## Layout

| Path | Purpose |
| --- | --- |
| `harmonizer/edf.py` | Header and signal reader, label rewrite |
| `harmonizer/layout.py` | Group recordings by header layout |
| `harmonizer/checks.py` | Signal features, type from trace, unit check, duplicate pairs |
| `harmonizer/inject.py` | Label-swap faults and the fixed dev/held-out split |
| `harmonizer/canon.py` | Run real CANONICAL on one EDF |
| `harmonizer/mapping.py` | Baseline label reader and mapping validation |
| `harmonizer/model.py` | Claude label reader, cached |
| `harmonizer/evidence.py` | Confidence from label/trace agreement |
| `harmonizer/emit.py` | Rule file, sample lists, pre-script |
| `harmonizer/targets.py` | Canonical targets and which types a recording must get right |
| `scripts/draft.py` | Draft rules for a cohort |
| `scripts/score.py` | Score a draft through CANONICAL against the answer key |
| `scripts/fetch_cap.py` | Fetch CAP excerpts by HTTP range request |
| `scripts/audit_cohort.py` | Run the checks on a directory of EDFs |
| `scripts/retype.py` | Re-type from cached features after a rule change |
| `scripts/summarise.py` | Agreement table, flags per recording, swap recall |
| `scripts/answer_key.py` | Draft answer key with settled/unsettled status; keeps reader rulings on re-run |
| `tests/test_core.py` | Unit tests on synthetic EDFs, no data needed: `python3 -m pytest tests` |

## Reproduce

```
pip install lunapi numpy scipy anthropic pytest
python3 scripts/fetch_cap.py data/cap/excerpts 8 300   # 3 GB, about 1 minute
python3 scripts/audit_cohort.py data/cap/excerpts results/cap   # about 3.5 minutes on 4 cores
python3 scripts/summarise.py results/cap held
python3 scripts/answer_key.py results/cap
```

Each CAP excerpt is eight 5-minute windows spread over the night, stored as a valid EDF with the original header.

## CAP findings (first pass)

- 108 recordings, 2,074 channels, 113 distinct labels. 50 layouts by label set (35 seen once); 77 when unit and sampling rate are included.
- `rbd10.edf` and `rbd11.edf` are byte-identical (same SHA-256 in PhysioNet's checksum file), so there are 107 unique recordings.
- Label and trace agree on 1,820 channels, 87 are flat, 167 are unsettled.
- Likely real header errors: where `F8-T4` and `F7-T3` appear without the rest of the temporal chain (mostly RBD files), they carry 0 to 1% of power at 0.5 to 4 Hz against 65 to 89% for the same labels elsewhere. They look like muscle channels under an EEG label. Needs a reader's ruling.
- Wrong-unit headers on correctly typed EEG, ECG or EMG channels: none, at a 30-fold tolerance. Three recordings (`n13`, `n14`, `n15`) leave the unit blank.
- 30 recordings have at least one channel whose physical minimum exceeds its maximum, which inverts the trace on read. ECG is the most common.
- Three recordings hold both `ROC-LOC` and `LOC-ROC` (correlation below -0.95), three hold near-duplicate `CHIN1`/`CHIN2`.
- Label-swap recall on the held-out half (45 recordings, scored once): 88.4% of cross-type swaps at 1.51 type flags per clean recording. Dev half: 86.5% at 1.46.

## Known weaknesses of the checks

- EEG and EOG are one class (`neuro`), so EEG/EOG swaps are missed. This is most of the missed swaps.
- Quiet leg EMG reads as `neuro`; drifting EOG reads as `resp`; some pulse-wave channels read as ECG.
- The ECG polarity sign is not trustworthy yet: 72 of 98 CAP ECG leads come out negative, which is more likely the heuristic or the lead placement than 72 inverted leads.
- The answer key and the tool share the same checks. Until a reader settles the unsettled rows, the key cannot score the checks themselves.
- Thresholds were set from physiology and Luna's three tutorial recordings. Structural fixes were made after looking at the CAP dev half; the held-out half was scored once afterwards.

## Blocked

- Stage 1 needs the NSRR rule file (`nsrr/common/resources/canonical/harm.txt`, 81 rules per the Luna docs). Its GitLab host returned 503 on 2026-11-14. `rules/smoke.sigs` only proves the harness runs.
