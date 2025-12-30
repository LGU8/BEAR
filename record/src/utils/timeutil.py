from __future__ import annotations

from datetime import datetime
import time
from dataclasses import dataclass


def now_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def now_yyyymmddhhmmss() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


@dataclass
class Timer:
    t0: float

    @staticmethod
    def start() -> "Timer":
        return Timer(time.perf_counter())

    def sec(self) -> float:
        return float(time.perf_counter() - self.t0)
