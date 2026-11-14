# harmonizer

Channel auditor for sleep recordings: checks what each channel is against what the EDF header claims, and (later) drafts Luna CANONICAL rules for layouts existing rules miss.

## Status

Built so far: EDF reader, layout grouping, per-channel signal checks, label-swap injector, a harness that runs Luna's real `CANONICAL` through `lunapi`, and a first full pass over the CAP Sleep Database. Not built yet: the model stage, the rule-file writer, the EEG polarity check (needs staging), scoring stages 1 to 3.

## Layout

| Path | Purpose |
| --- | --- |
| `harmonizer/edf.py` | Header and signal reader, label rewrite |
| `harmonizer/layout.py` | Group recordings by header layout |
| `harmonizer/checks.py` | Signal features, type from trace, unit check, duplicate pairs |
| `harmonizer/inject.py` | Label-swap faults and the fixed dev/held-out split |
| `harmonizer/canon.py` | Run real CANONICAL on one EDF |
| `scripts/fetch_cap.py` | Fetch CAP excerpts by HTTP range request |
| `scripts/audit_cohort.py` | Run the checks on a directory of EDFs |
| `scripts/retype.py` | Re-type from cached features after a rule change |
| `scripts/summarise.py` | Agreement table, flags per recording, swap recall |
| `scripts/answer_key.py` | Draft answer key with settled/unsettled status |

## Reproduce

```
pip install lunapi numpy scipy
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
