# ml/menu_reco/common/config.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Dict, Optional
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    DATA_DIR: str = os.getenv("DATA_DIR", "./ml/menu_reco/data/raw")
    ARTIFACTS_DIR: str = os.getenv("ARTIFACT_DIR", "./ml/menu_reco/artifacts")

    @property
    def data_dir(self) -> str:
        return self.DATA_DIR

    @property
    def artifact_dir(self) -> str:
        return self.ARTIFACTS_DIR

    # ✅ service.py에서 쓰는 경로 해석 메서드 추가
    def resolve_data_dir(self, base_dir: Path) -> Path:
        p = Path(self.DATA_DIR)
        return p if p.is_absolute() else (base_dir / p).resolve()

    def resolve_artifacts_dir(self, base_dir: Path) -> Path:
        p = Path(self.ARTIFACTS_DIR)
        return p if p.is_absolute() else (base_dir / p).resolve()


@dataclass
class Phase1Config:
    LAMBDA_CAL: float = 0.60
    CAL_SOFT_CLIP: float = 0.80

    DELTA: float = 0.20
    LAMBDA_PURPOSE: float = 0.50

    FAT_RATIO_CAP: float = 0.80
    PROTEIN_MIN_G: float = 10.0
    USE_KEYWORD_BLACKLIST: bool = True
    KEYWORD_BLACKLIST: Tuple[str, ...] = (
        "기름", "오일", "마요", "마가린", "소스", "드레싱", "페스토"
    )

    W_CTX: float = 0.00
    W_GLOBAL: float = 0.10
    W_PREF: float = 1.00
    W_HEALTH: float = 1.00

    ALPHA_SLIDER: float = 0.50
    HEALTH_532: Tuple[float, float, float] = (0.5, 0.3, 0.2)


@dataclass
class Phase2Config:
    K: int = 5
    CAL_NORM_DENOM: float = 600.0
    HEALTH_532: Tuple[float, float, float] = (0.5, 0.3, 0.2)


@dataclass
class Phase3Config:
    alpha: float = 1.0
    w_map: Optional[Dict[str, float]] = None

    def __post_init__(self):
        if self.w_map is None:
            self.w_map = {
                "pref_cluster": 0.5,
                "healthy_532": 0.6,
                "explore_new": 0.3,
            }