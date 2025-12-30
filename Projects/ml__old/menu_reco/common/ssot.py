from __future__ import annotations
from typing import Iterable, Optional, Set
import numpy as np
import pandas as pd

def to_numeric_safe(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def normalize_macro(c: float, p: float, f: float) -> np.ndarray:
    vec = np.array([c, p, f], dtype=float)
    s = float(np.nansum(vec))
    if s <= 1e-12:
        return np.array([1/3, 1/3, 1/3], dtype=float)
    return vec / s

def macro_ratio_from_grams_to_kcal(c_g: float, p_g: float, f_g: float) -> np.ndarray:
    c = (0.0 if pd.isna(c_g) else float(c_g)) * 4.0
    p = (0.0 if pd.isna(p_g) else float(p_g)) * 4.0
    f = (0.0 if pd.isna(f_g) else float(f_g)) * 9.0
    return normalize_macro(c, p, f)

def l1_distance_batch(mat: np.ndarray, vec: np.ndarray) -> np.ndarray:
    return np.abs(mat - vec).sum(axis=1)

def compute_calorie_penalty(food_cal: float, target_cal: float, lambda_cal: float, soft_clip: float) -> float:
    if target_cal <= 0 or pd.isna(target_cal):
        return 0.0
    diff = abs(float(food_cal) - float(target_cal))
    ratio = diff / float(target_cal)
    ratio = min(ratio, soft_clip)
    return -lambda_cal * ratio

def compute_purpose_delta_penalty(food_cal: float, target_cal: float, purpose: int, delta: float, lambda_purpose: float) -> float:
    if target_cal <= 0 or pd.isna(target_cal):
        return 0.0
    cal = float(food_cal)
    t = float(target_cal)

    if int(purpose) == 0:  # Diet
        if cal > t * (1.0 + delta):
            overflow = (cal - t * (1.0 + delta)) / t
            return -lambda_purpose * overflow
    elif int(purpose) == 2:  # Bulk
        if cal < t * (1.0 - delta):
            under = (t * (1.0 - delta) - cal) / t
            return -lambda_purpose * under
    return 0.0

def keyword_blacklist_hit(food_name: str, blacklist: Iterable[str]) -> bool:
    if not isinstance(food_name, str):
        return False
    for kw in blacklist:
        if kw in food_name:
            return True
    return False

def apply_guardrails(
    cand: pd.DataFrame,
    fat_ratio_cap: float,
    protein_min_g: float,
    use_keyword_blacklist: bool,
    keyword_blacklist: Iterable[str],
) -> pd.DataFrame:
    df = cand.copy()

    if "macro_ratio_f" in df.columns:
        df = df[df["macro_ratio_f"].fillna(0) <= fat_ratio_cap].copy()

    if protein_min_g is not None and protein_min_g > 0:
        if "food_prot_g" in df.columns:
            df = df[df["food_prot_g"].fillna(0) >= protein_min_g].copy()

    if use_keyword_blacklist and "Food" in df.columns:
        mask = df["Food"].apply(lambda x: not keyword_blacklist_hit(str(x), keyword_blacklist))
        df = df[mask].copy()

    return df

def diversity_unique_food(df_sorted: pd.DataFrame, k: int, used: Optional[Set[str]] = None) -> pd.DataFrame:
    used = set() if used is None else set(used)
    rows = []
    for _, r in df_sorted.iterrows():
        f = str(r.get("Food"))
        if f in used:
            continue
        used.add(f)
        rows.append(r)
        if len(rows) >= k:
            break
    if not rows:
        return df_sorted.head(0)
    return pd.DataFrame(rows).reset_index(drop=True)