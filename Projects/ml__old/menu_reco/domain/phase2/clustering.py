from __future__ import annotations
from typing import Tuple, Dict, Any
import numpy as np
import pandas as pd

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from ml.menu_reco.common.config import Phase2Config
from ml.menu_reco.common.ssot import normalize_macro

def _l1(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a-b).sum())

def label_cluster_message_key(center_c: float, center_p: float, center_f: float, dist_to_healthy: float) -> str:
    if center_f >= 0.60:
        return "high_fat_comfort"
    if dist_to_healthy < 0.15:
        return "healthy_532_like"
    if (center_p >= 0.35) and (center_c >= 0.30):
        return "high_protein"
    if (center_c >= 0.50) and (center_f <= 0.25):
        return "high_carb_lowfat"
    return "balanced_mixed"

def label_cluster_text(message_key: str, cal_norm: float) -> str:
    if cal_norm < 0.55:
        cal_tag = "Lean"
    elif cal_norm <= 0.90:
        cal_tag = "Mid"
    else:
        cal_tag = "Rich"

    base = {
        "high_fat_comfort": "Fat Comfort",
        "healthy_532_like": "Balance 5:3:2",
        "high_protein": "High Protein",
        "high_carb_lowfat": "Carb Focus",
        "balanced_mixed": "Mixed",
    }[message_key]
    return f"{cal_tag} {base}"

def perform_phase2_clustering(ctx_food_all: pd.DataFrame, cfg: Phase2Config) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = ctx_food_all.copy()
    df["cal_norm"] = df["Calories"].fillna(0) / float(cfg.CAL_NORM_DENOM)

    feat_cols = ["macro_ratio_c","macro_ratio_p","macro_ratio_f","cal_norm"]
    if "emotion_score" not in df.columns:
        df["emotion_score"] = 0.0
    feat_cols.append("emotion_score")

    results = []
    meta_rows = []
    healthy_vec = np.array(cfg.HEALTH_532, dtype=float)

    for (mood, energy), g in df.groupby(["Mood","Energy"]):
        if len(g) < cfg.K:
            continue

        X_raw = g[feat_cols].to_numpy()
        scaler = StandardScaler()
        X = scaler.fit_transform(X_raw)

        km = KMeans(n_clusters=cfg.K, random_state=42, n_init=10)
        labels = km.fit_predict(X)

        g2 = g.copy()
        g2["cluster_id"] = labels
        results.append(g2)

        centers = scaler.inverse_transform(km.cluster_centers_)
        for cid in range(cfg.K):
            c = centers[cid]
            center_vec = np.array([c[0], c[1], c[2]], dtype=float)
            dist = _l1(center_vec, healthy_vec)

            cal_norm = float(c[3])
            emo = float(c[4])
            key = label_cluster_message_key(center_vec[0], center_vec[1], center_vec[2], dist)
            label = label_cluster_text(key, cal_norm)

            meta_rows.append({
                "Mood": mood, "Energy": energy,
                "cluster_id": cid,
                "center_macro_c": center_vec[0],
                "center_macro_p": center_vec[1],
                "center_macro_f": center_vec[2],
                "center_cal_norm": cal_norm,
                "center_emo_score": emo,
                "dist_to_healthy": dist,
                "message_key": key,
                "cluster_label": label,
                "n_rows": int((labels==cid).sum()),
            })

    clustered = pd.concat(results, ignore_index=True) if results else df.head(0).copy()
    meta = pd.DataFrame(meta_rows)
    return clustered, meta

def attach_cluster_info(rec_df: pd.DataFrame, clustered: pd.DataFrame, cluster_meta: pd.DataFrame) -> pd.DataFrame:
    out = rec_df.copy()

    # Food 기준으로 cluster_id 붙이기(동일 Food라도 context별 cluster 달라질 수 있어 Mood/Energy로 join)
    # Phase1 output에는 Mood_req/Energy_req가 있으므로 그것을 사용
    if clustered is None or clustered.empty:
        out["cluster_id"] = np.nan
        out["cluster_label"] = "N/A"
        out["message_key"] = "N/A"
        out["Mood_used"] = out.get("Mood_req")
        out["Energy_used"] = out.get("Energy_req")
        return out

    out["Mood_used"] = out.get("Mood_req")
    out["Energy_used"] = out.get("Energy_req")

    key_cols_left = ["Mood_used","Energy_used","Food"]
    key_cols_right = ["Mood","Energy","Food"]

    tmp = clustered[key_cols_right + ["cluster_id"]].drop_duplicates()
    tmp = tmp.rename(columns={"Mood":"Mood_used","Energy":"Energy_used"})

    out = out.merge(tmp, on=key_cols_left, how="left")

    # label 붙이기
    if cluster_meta is None or cluster_meta.empty:
        out["cluster_label"] = "N/A"
        out["message_key"] = "N/A"
        return out

    meta = cluster_meta.rename(columns={"Mood":"Mood_used","Energy":"Energy_used"})
    out = out.merge(
        meta[["Mood_used","Energy_used","cluster_id","cluster_label","message_key","dist_to_healthy"]],
        on=["Mood_used","Energy_used","cluster_id"],
        how="left"
    )
    return out