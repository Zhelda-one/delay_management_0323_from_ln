# timing_engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, List, Mapping, Any

import pandas as pd

from constants import (
    DELAY_KEYS_ORDER,
    CAL_15_30,
    CAL_40,
    CAL_MINIMUM,
    CAL_NONE
)

REAL_FIELD_KEYS = [
    "F30_real_T1a_max_up",
    "F31_real_T1a_min_up",
    "F32_real_T1a_max_cp_dl",
    "F33_real_T1a_min_cp_dl",
    "F34_real_T1a_max_cp_ul",
    "F35_real_T1a_min_cp_ul",
    "F36_real_Ta4_min_ul",
    "F37_real_Ta4_max_ul",
    "F38_real_T2a_max_up",
    "F39_real_T2a_min_up",
    "F40_real_T2a_max_cp_dl",
    "F41_real_T2a_min_cp_dl",
    "F42_real_T2a_max_cp_ul",
    "F43_real_T2a_min_cp_ul",
    "F44_real_Ta3_min_ul",
    "F45_real_Ta3_max_ul",
]

def default_calibration_field_tokens() -> Dict[str, Dict[str, str]]:
    """모드별 F30~F45 항목에 대한 기본 오프셋 토큰(0/E16/E17)."""
    return {
        CAL_NONE: {k: "0" for k in REAL_FIELD_KEYS},
        CAL_15_30: {
            **{k: "0" for k in REAL_FIELD_KEYS[:6]},
            **{k: "E17" for k in REAL_FIELD_KEYS[6:]},
        },
        CAL_40: {
            **{k: "0" for k in REAL_FIELD_KEYS[:6]},
            **{k: "E16" for k in REAL_FIELD_KEYS[6:]},
        },
        CAL_MINIMUM: {k: "E16" for k in REAL_FIELD_KEYS},
    }

def default_config() -> Dict[str, float]:
    """
    timing_v6_calibrated.xlsm (Master 시트) 기본값을 초기값으로 사용.
    필요하면 UI에서 수정.
    """
    return {
        # RU parameters (Master!E4,E5,E8,E9,E10,E11,E12)
        "t2a_min_up": 206.0,        # E4
        "t2a_max_up": 437.0,        # E5
        "tcp_adv_dl": 220.0,        # E8
        "ta3_min": 70.0,            # E9
        "ta3_max": 232.0,           # E10
        "t2a_min_cp_ul": 220.0,     # E11
        "t2a_max_cp_ul": 451.0,     # E12

        # DU parameters (Master!E14,E15)  ※ 엑셀은 음수로 들어가 있음
        "t12_max": -10.0,           # E14
        "t12_min": -5.0,            # E15
    }

def make_empty_delaydata() -> pd.DataFrame:
    """
    DelayData 시트(ODU 8행 + ORU 8행)를 웹 내부 테이블로 구성.
    """
    rows = []
    for node in ["ODU", "ORU"]:
        for cat, met in DELAY_KEYS_ORDER:
            rows.append({"Node": node, "Category": cat, "Metric": met, "Value(µs)": None})
    return pd.DataFrame(rows)

def apply_upload_to_delaydata(
    delay_df: pd.DataFrame,
    upload_values: Dict[Tuple[str, str], float],
    target: str,  # "ODU" | "ORU" | "Both"
) -> pd.DataFrame:
    """
    업로드 8개 값을 DelayData에 반영.
    """
    out = delay_df.copy()
    targets = ["ODU", "ORU"] if target == "Both" else [target]

    for node in targets:
        for (cat, met), val in upload_values.items():
            mask = (out["Node"] == node) & (out["Category"] == cat) & (out["Metric"] == met)
            if mask.sum() != 1:
                raise ValueError(f"DelayData mapping error for {node}: {cat}/{met}")
            out.loc[mask, "Value(µs)"] = float(val)
    return out

def _resolve_offset_token(token: Any, E16: float, E17: float) -> float:
    tok = str(token).strip().upper()
    if tok in {"0", "ZERO"}:
        return 0.0
    if tok == "E16":
        return float(E16)
    if tok == "E17":
        return float(E17)
    raise ValueError(f"Invalid calibration token: {token}. Use one of 0/E16/E17")


def _calibration_offsets_by_field(
    cal_mode: str,
    E16: float,
    E17: float,
    custom_tokens_by_mode: Mapping[str, Mapping[str, Any]] | None = None,
) -> Dict[str, float]:
    """
    F30~F45 항목별 calibration offset을 반환.
    - 기본값은 기존 모드 동작과 동일
    - custom_tokens_by_mode를 전달하면 모드/필드별로 0/E16/E17 토큰을 세부 적용
    """
    tokens_by_mode = default_calibration_field_tokens()
    if custom_tokens_by_mode is not None:
        for mode, vals in custom_tokens_by_mode.items():
            if mode not in tokens_by_mode:
                continue
            for k, v in vals.items():
                if k in REAL_FIELD_KEYS:
                    tokens_by_mode[mode][k] = str(v)

    mode_tokens = tokens_by_mode.get(cal_mode)
    if mode_tokens is None:
        raise ValueError(f"Unknown cal_mode: {cal_mode}")

    out: Dict[str, float] = {}
    for field in REAL_FIELD_KEYS:
        token = mode_tokens.get(field, "0")
        out[field] = _resolve_offset_token(token, E16, E17)
    return out

@dataclass(frozen=True)
class MasterResult:
    master: Dict[str, float]
    dl: pd.DataFrame
    ul: pd.DataFrame

def _get_delay_block(delay_df: pd.DataFrame, node: str) -> List[float]:
    """
    node(ODU/ORU)의 8개 값을 DELAY_KEYS_ORDER 순서로 리스트화.
    """
    vals = []
    for cat, met in DELAY_KEYS_ORDER:
        s = delay_df.loc[
            (delay_df["Node"] == node) & (delay_df["Category"] == cat) & (delay_df["Metric"] == met),
            "Value(µs)",
        ]
        if len(s) != 1:
            raise ValueError(f"DelayData missing for {node}: {cat}/{met}")
        if pd.isna(s.iloc[0]):
            raise ValueError(f"DelayData value empty for {node}: {cat}/{met}")
        vals.append(float(s.iloc[0]))
    return vals

def compute(delay_df: pd.DataFrame, cfg: Dict[str, float], cal_mode: str) -> MasterResult:
    """
    Master 시트 수식(주요 셀) + DL/UL 시트 참조를 그대로 계산.
    - DelayData(16개) + config + calibration 모드 -> DL/UL 파라미터 테이블 생성
    """
    # --- RU / DU base ---
    E4 = cfg["t2a_min_up"]
    E5 = cfg["t2a_max_up"]
    E8 = cfg["tcp_adv_dl"]
    E9 = cfg["ta3_min"]
    E10 = cfg["ta3_max"]
    E11 = cfg["t2a_min_cp_ul"]
    E12 = cfg["t2a_max_cp_ul"]
    E14 = cfg["t12_max"]   # 음수
    E15 = cfg["t12_min"]   # 음수

    # derived like Excel Master
    E6 = E4 + E8             # t2a_min_cp_dl
    E7 = E5 + E8             # t2a_max_cp_dl

    F4 = -E4
    F5 = -E5
    F8 = -E8
    F11 = -E11
    F12 = -E12

    E16 = -E14               # t34_max
    E17 = -E15               # t34_min

    # DU Delay profile (Master!E20,E21,E22,E23,E25,E26,E27,E28)
    E20 = F4 + E14                       # T1a_min_up
    E21 = E15 + F5                       # T1a_max_up
    E22 = E20 + F8                       # T1a_min_cp_dl
    E23 = E21 + F8                       # T1a_max_cp_dl
    E25 = E14 + F11                      # T1a_min_cp_ul
    E26 = E15 + F12                      # T1a_max_cp_ul
    E27 = E9 + E17                       # Ta4_min_up
    E28 = E10 + E16                      # Ta4_max_up

    # --- Calibrated inputs (Master!E30:E45) from DelayData ---
    odu_vals = _get_delay_block(delay_df, "ODU")  # 8
    oru_vals = _get_delay_block(delay_df, "ORU")  # 8

    # # Calibration offset selection (엑셀 버튼 동작을 로직화)
    # # 기본(엑셀 기본 수식): ODU는 +E16, ORU는 +E17
    # odu_off = E16
    # oru_off = E17

    # if cal_mode == CAL_NONE:
    #     # Module8: 보정 없음 (ODU/ORU 모두 +0)
    #     odu_off = 0.0
    #     oru_off = 0.0
    # elif cal_mode == CAL_15_30:
    #     odu_off = 0.0
    #     oru_off = E17
    #     pass
    # elif cal_mode == CAL_40:
    #     # Module6: ORU도 +E16
    #     odu_off= 0.0
    #     oru_off = E16
    # elif cal_mode == CAL_MINIMUM:
    #     # Module7: 전부 +E16
    #     odu_off = E16
    #     oru_off = E16
    # else:
    #     raise ValueError(f"Unknown cal_mode: {cal_mode}")

    # Calibration offset selection (항목 단위)
    field_offsets = _calibration_offsets_by_field(cal_mode, E16, E17, cfg.get("calibration_offsets_by_mode  "))

    # Master!F30:F37 (ODU real) / F38:F45 (ORU real)
    # F30_37 = [v + odu_off for v in odu_vals]
    # F38_45 = [v + oru_off for v in oru_vals]
    F30_37 = [
        odu_vals[0] + field_offsets["F30_real_T1a_max_up"],
        odu_vals[1] + field_offsets["F31_real_T1a_min_up"],
        odu_vals[2] + field_offsets["F32_real_T1a_max_cp_dl"],
        odu_vals[3] + field_offsets["F33_real_T1a_min_cp_dl"],
        odu_vals[4] + field_offsets["F34_real_T1a_max_cp_ul"],
        odu_vals[5] + field_offsets["F35_real_T1a_min_cp_ul"],
        odu_vals[6] + field_offsets["F36_real_Ta4_min_ul"],
        odu_vals[7] + field_offsets["F37_real_Ta4_max_ul"],
    ]
    F38_45 = [
        oru_vals[0] + field_offsets["F38_real_T2a_max_up"],
        oru_vals[1] + field_offsets["F39_real_T2a_min_up"],
        oru_vals[2] + field_offsets["F40_real_T2a_max_cp_dl"],
        oru_vals[3] + field_offsets["F41_real_T2a_min_cp_dl"],
        oru_vals[4] + field_offsets["F42_real_T2a_max_cp_ul"],
        oru_vals[5] + field_offsets["F43_real_T2a_min_cp_ul"],
        oru_vals[6] + field_offsets["F44_real_Ta3_min_ul"],
        oru_vals[7] + field_offsets["F45_real_Ta3_max_ul"],
    ]
    # Master dict (필요한 것만 담기 — 나중에 더 확장 가능)
    master = {
        "E4_t2a_min_up": E4,
        "E5_t2a_max_up": E5,
        "E6_t2a_min_cp_dl": E6,
        "E7_t2a_max_cp_dl": E7,
        "E8_tcp_adv_dl": E8,
        "E9_ta3_min": E9,
        "E10_ta3_max": E10,
        "E11_t2a_min_cp_ul": E11,
        "E12_t2a_max_cp_ul": E12,
        "E14_t12_max": E14,
        "E15_t12_min": E15,
        "E16_t34_max": E16,
        "E17_t34_min": E17,
        "E20_T1a_min_up": E20,
        "E21_T1a_max_up": E21,
        "E22_T1a_min_cp_dl": E22,
        "E23_T1a_max_cp_dl": E23,
        "E25_T1a_min_cp_ul": E25,
        "E26_T1a_max_cp_ul": E26,
        "E27_Ta4_min_ul": E27,
        "E28_Ta4_max_ul": E28,
        # real blocks
        "F30_real_T1a_max_up": F30_37[0],
        "F31_real_T1a_min_up": F30_37[1],
        "F32_real_T1a_max_cp_dl": F30_37[2],
        "F33_real_T1a_min_cp_dl": F30_37[3],
        "F34_real_T1a_max_cp_ul": F30_37[4],
        "F35_real_T1a_min_cp_ul": F30_37[5],
        "F36_real_Ta4_min_ul": F30_37[6],
        "F37_real_Ta4_max_ul": F30_37[7],
        "F38_real_T2a_max_up": F38_45[0],
        "F39_real_T2a_min_up": F38_45[1],
        "F40_real_T2a_max_cp_dl": F38_45[2],
        "F41_real_T2a_min_cp_dl": F38_45[3],
        "F42_real_T2a_max_cp_ul": F38_45[4],
        "F43_real_T2a_min_cp_ul": F38_45[5],
        "F44_real_Ta3_min_ul": F38_45[6],
        "F45_real_Ta3_max_ul": F38_45[7],
    }

    # --- DL sheet (timing_v6_calibrated.xlsm DL 시트 수식 그대로) ---
    dl_rows = [
        ("T1a_max_cp_dl", E23),
        ("T1a_min_cp_dl", E22),
        ("T2a_max_cp_dl", -E7),
        ("T2a_min_cp_dl", -E6),
        ("T1a_max_up", E21),
        ("T1a_min_up", E20),
        ("T2a_max_up", -E5),
        ("T2a_min_up", -E4),
        ("real_T1a_max_up", master["F30_real_T1a_max_up"]),
        ("real_T1a_min_up", master["F31_real_T1a_min_up"]),
        ("real_T1a_max_cp_dl", master["F32_real_T1a_max_cp_dl"]),
        ("real_T1a_min_cp_dl", master["F33_real_T1a_min_cp_dl"]),
        ("real_T2a_max_cp_dl", master["F40_real_T2a_max_cp_dl"]),
        ("real_T2a_min_cp_dl", master["F41_real_T2a_min_cp_dl"]),
        ("real_T2a_max_up", master["F38_real_T2a_max_up"]),
        ("real_T2a_min_up", master["F39_real_T2a_min_up"]),
    ]
    dl_df = pd.DataFrame(dl_rows, columns=["Parameter", "Value"])

    # --- UL sheet ---
    ul_rows = [
        ("T1a_max_cp_ul", E26),
        ("T1a_min_cp_ul", E25),
        ("Ta3_max_ul", E10),
        ("Ta3_min_ul", E9),
        ("T2a_max_cp_ul", -E12),
        ("T2a_min_cp_ul", -E11),
        ("Ta4_max_ul", E28),
        ("Ta4_min_ul", E27),
        ("real_T1a_max_cp_ul", master["F34_real_T1a_max_cp_ul"]),
        ("real_T1a_min_cp_ul", master["F35_real_T1a_min_cp_ul"]),
        ("real_Ta3_max_ul", master["F45_real_Ta3_max_ul"]),
        ("real_Ta3_min_ul", master["F44_real_Ta3_min_ul"]),
        ("real_T2a_max_cp_ul", master["F42_real_T2a_max_cp_ul"]),
        ("real_T2a_min_cp_ul", master["F43_real_T2a_min_cp_ul"]),
        ("real_Ta4_max_ul", master["F37_real_Ta4_max_ul"]),
        ("real_Ta4_min_ul", master["F36_real_Ta4_min_ul"]),
    ]
    ul_df = pd.DataFrame(ul_rows, columns=["Parameter", "Value"])

    return MasterResult(master=master, dl=dl_df, ul=ul_df)