from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd


@dataclass
class ViolationRow:
    contingency_label: str
    violation_type: Literal["thermal", "voltage"]
    element_type: Literal["branch", "xfmr", "bus"]
    from_bus: int
    from_name: str
    from_kv: float
    to_bus: Optional[int]
    to_name: Optional[str]
    to_kv: Optional[float]
    ckt: Optional[str]
    rating: Optional[float]
    flow: Optional[float]
    loading_pct: Optional[float]
    v_init: Optional[float]
    v_cont: Optional[float]
    dev_pct: Optional[float]


def to_dataframe(rows: list[ViolationRow]) -> pd.DataFrame:
    return pd.DataFrame([vars(r) for r in rows])
