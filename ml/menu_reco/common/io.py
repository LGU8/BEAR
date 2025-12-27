from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import json
import pandas as pd

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def load_csv_triplet(data_dir: str) -> Dict[str, pd.DataFrame]:
    base = Path(data_dir)
    foods = pd.read_csv(base / "음식_최종.csv")
    users = pd.read_csv(base / "사용자_최종.csv")
    logs  = pd.read_csv(base / "최종_메뉴_모델.csv")
    return {"foods": foods, "users": users, "logs": logs}

def load_csv_inputs(cfg) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    AppConfig 기반 CSV 로더 (DB 붙기 전 최종 테스트용)
    - 내부적으로 load_csv_triplet() 재사용
    """
    triplet = load_csv_triplet(cfg.DATA_DIR)
    return triplet["foods"], triplet["users"], triplet["logs"]

def save_parquet(df: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    df.to_parquet(path, index=False)

def load_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)

def load_phase1_artifacts_from_dir(artifacts_dir: str) -> Dict[str, Any]:
    base = Path(artifacts_dir) / "phase1"
    return {
        "food_stats": load_parquet(base / "food_stats.parquet"),
        "user_pref": load_parquet(base / "user_pref.parquet"),
        "ctx_food_all": load_parquet(base / "ctx_food_all.parquet"),
        "unobserved_pool": load_parquet(base / "unobserved_pool.parquet"),
        "bad_foods_set": set(load_json(base / "bad_foods.json")),
        "config": load_json(base / "config.json"),
    }

def load_phase2_artifacts_from_dir(artifacts_dir: str) -> Dict[str, Any]:
    base = Path(artifacts_dir) / "phase2"
    return {
        "clustered": load_parquet(base / "clustered.parquet"),
        "cluster_meta": load_parquet(base / "cluster_meta.parquet"),
        "config": load_json(base / "config.json"),
    }

def load_phase1_artifacts(cfg) -> Dict[str, Any]:
    base = Path(cfg.ARTIFACTS_DIR) / "phase1"
    return {
        "food_stats": load_parquet(base / "food_stats.parquet"),
        "user_pref": load_parquet(base / "user_pref.parquet"),
        "ctx_food_all": load_parquet(base / "ctx_food_all.parquet"),
        "unobserved_pool": load_parquet(base / "unobserved_pool.parquet"),
        "bad_foods_set": set(load_json(base / "bad_foods.json")),
        "config": load_json(base / "config.json"),
    }

def load_phase2_artifacts(cfg) -> Dict[str, Any]:
    base = Path(cfg.ARTIFACTS_DIR) / "phase2"
    return {
        "clustered": load_parquet(base / "clustered.parquet"),
        "cluster_meta": load_parquet(base / "cluster_meta.parquet"),
        "config": load_json(base / "config.json"),
    }

def save_json(obj: Any, path: Path) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(dataclass_obj: Any, path: Path) -> None:
    from dataclasses import is_dataclass
    if not is_dataclass(dataclass_obj):
        raise TypeError("save_config expects a dataclass instance")
    save_json(asdict(dataclass_obj), path)