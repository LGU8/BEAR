# ml/menu_reco/common/constants.py
from __future__ import annotations

# DB 기준: mood=pos/neu/neg, energy=low/med/hig
STABLE_CONTEXTS = {
    ("neu", "low"), ("neu", "med"),
    ("pos", "low"), ("pos", "med"),
}

UNSTABLE_CONTEXTS = {
    ("neg", "low"), ("neg", "med"), ("neg", "hig"),
    ("neu", "hig"), ("pos", "hig"),
}

RECOVERY_CONTEXTS = {
    ("neu", "low"), ("neu", "med"), ("pos", "low"),
}