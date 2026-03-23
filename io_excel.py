# io_excel.py
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Dict, Tuple, Optional, List

import pandas as pd

from constants import EXPECTED_COLUMNS, DELAY_KEYS_ORDER

def _norm(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    s = s.replace("μ", "µ")
    s = re.sub(r"\s+", " ", s)
    return s

def _norm_col(s: str) -> str:
    return _norm(s).lower()

def _as_float(x) -> float:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        raise ValueError("Value is empty.")
    try:
        return float(x)
    except Exception as e:
        raise ValueError(f"Value is not numeric: {x}") from e

@dataclass(frozen=True)
class DelayUpload:
    values: Dict[Tuple[str, str], float]  # (Category, Metric) -> value(µs)
    sheet_used: str

def _try_parse_df(df: pd.DataFrame) -> Dict[Tuple[str, str], float]:
    """df 안에서 Category/Metric/Value 컬럼을 찾아 8개 키를 파싱."""
    col_map = {_norm_col(c): c for c in df.columns}
    if not EXPECTED_COLUMNS.issubset(set(col_map.keys())):
        raise ValueError(f"Missing required columns. Got: {list(df.columns)}")

    cat_col = col_map["category"]
    met_col = col_map["metric"]
    val_col = col_map["value"]

    values: Dict[Tuple[str, str], float] = {}
    for _, row in df.iterrows():
        cat = _norm(row[cat_col])
        met = _norm(row[met_col])
        # 빈 행 스킵(현장 파일에서 종종 생김)
        if cat == "" and met == "":
            continue
        val = _as_float(row[val_col])
        values[(cat, met)] = val

    missing = [k for k in DELAY_KEYS_ORDER if k not in values]
    if missing:
        msg = "Missing rows in upload:\n" + "\n".join([f"- {c} / {m}" for c, m in missing])
        raise ValueError(msg)

    return values

def read_delay_upload_xlsx(
    file_bytes: bytes,
    preferred_sheet: str = "eCPRI Analysis",
) -> DelayUpload:
    """
    파일명과 무관하게 업로드된 xlsx에서 Delay(8개) 테이블을 파싱.
    - preferred_sheet가 있으면 먼저 시도
    - 없으면 workbook의 모든 시트를 순회하면서 조건을 만족하는 첫 시트를 사용
    """
    xls = pd.ExcelFile(io.BytesIO(file_bytes))

    # 1) preferred sheet 우선
    if preferred_sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=preferred_sheet)
        values = _try_parse_df(df)
        return DelayUpload(values=values, sheet_used=preferred_sheet)

    # 2) 없으면 모든 시트 순회
    last_err: Optional[Exception] = None
    for sh in xls.sheet_names:
        try:
            df = pd.read_excel(xls, sheet_name=sh)
            values = _try_parse_df(df)
            return DelayUpload(values=values, sheet_used=sh)
        except Exception as e:
            last_err = e
            continue

    # 3) 끝까지 못 찾으면 에러
    raise ValueError(
        f"Could not find a sheet with columns {EXPECTED_COLUMNS} "
        f"and required 8 keys. Sheets tried: {xls.sheet_names}. "
        f"Last error: {last_err}"
    )