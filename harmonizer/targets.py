"""Canonical targets the drafter may emit. Names follow Luna's NSRR harmonisation output where one exists."""

TARGETS = {
    "C4_M1": "eeg", "C3_M2": "eeg", "F4_M1": "eeg", "F3_M2": "eeg", "O2_M1": "eeg", "O1_M2": "eeg",
    "LOC": "eog", "ROC": "eog",
    "EOG": "eog",  # bipolar ROC-LOC derivation; not an NSRR target
    "EMG": "emg", "ECG": "ecg", "LAT": "emg_leg", "RAT": "emg_leg",
    "thorax": "effort", "abdomen": "effort", "airflow": "flow", "nas_pres": "flow",
    "SpO2": "spo2", "HR": "hr", "pleth": "pleth", "pos": "pos", "snore": "snore",
}
VOLTAGE = {"eeg", "eog", "emg", "ecg", "emg_leg"}
# a recording counts as right only if each of these, when the answer key says it exists, is made correctly
REQUIRED_TYPES = ("eeg", "eog", "emg", "ecg")
