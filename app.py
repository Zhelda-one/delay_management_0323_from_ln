# app.py
from __future__ import annotations

import io
import datetime as dt

import pandas as pd
import streamlit as st
from openpyxl import Workbook

from constants import CAL_15_30, CAL_40, CAL_MINIMUM, CAL_NONE, CAL_MODES
from io_excel import read_delay_upload_xlsx
from timing_engine import (
    default_config,
    make_empty_delaydata,
    apply_upload_to_delaydata,
    compute,
    default_calibration_field_tokens,
    REAL_FIELD_KEYS,
)

st.set_page_config(page_title="Timing Web Tool", layout="wide")


# -------------------------
# Helpers
# -------------------------
def _xlsx_bytes_from_df(sheet_name: str, df: pd.DataFrame) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    ws.append(list(df.columns))
    for _, row in df.iterrows():
        ws.append([row[c] for c in df.columns])

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _ensure_state():
    if "delay_df" not in st.session_state:
        st.session_state.delay_df = make_empty_delaydata()

    if "cfg" not in st.session_state:
        st.session_state.cfg = default_config()

    if "cal_mode" not in st.session_state:
        st.session_state.cal_mode = CAL_NONE
    
    if "calibration_offsets_by_mode" not in st.session_state:
        st.session_state.calibration_offsets_by_mode = default_calibration_field_tokens()

def _num_input(key: str, label: str, default: float, help_text: str | None = None, *, disabled: bool = False) -> float:
    """
    Streamlit number_input 안정화:
    - key가 없으면 default로 초기화
    - 항상 key 기반으로 값을 유지
    """
    if key not in st.session_state:
        st.session_state[key] = float(default)
    return st.number_input(
        label,
        key=key,
        value=float(st.session_state[key]),
        help=help_text,
        format="%.2f",
        step=0.01
    )

def _to_float_micro(value) -> float:
    s = str(value).strip()
    s = s.replace(',', '').replace('Hz', '').replace('hz', '').strip()
    return float(s) / 1000.0


def _read_profile_cfg_upload(file_obj) -> dict[str, float]:
    name = (file_obj.name or '').lower()
    if name.endswith('.csv'):
        df = pd.read_csv(file_obj)
    else:
        df = pd.read_excel(file_obj)

    if df.empty:
        raise ValueError('Uploaded profile data file is empty.')

    row = df.iloc[0]
    normalized = {str(col).strip().lower(): row[col] for col in df.columns}

    def pick(*keys):
        for k in keys:
            if k in normalized and pd.notna(normalized[k]):
                return normalized[k]
        raise ValueError(f"Missing required column. Expected one of: {', '.join(keys)}")

    return {
        't2a_min_up': _to_float_micro(pick('t2a min up', 't2a_min_up')),
        't2a_max_up': _to_float_micro(pick('t2a max up', 't2a_max_up')),
        'tcp_adv_dl': _to_float_micro(pick('tcp adv dl', 'tcp_adv_dl')),
        'ta3_min': _to_float_micro(pick('ta3 min', 'ta3_min')),
        'ta3_max': _to_float_micro(pick('ta3 max', 'ta3_max')),
        't2a_min_cp_ul': _to_float_micro(pick('t2a min cp ul', 't2a_min_cp_ul')),
        't2a_max_cp_ul': _to_float_micro(pick('t2a max cp ul', 't2a_max_cp_ul')),
    }
def _calibration_tokens_df(tokens_by_mode: dict) -> pd.DataFrame:
    rows = []
    for field in REAL_FIELD_KEYS:
        row = {"Field": field}
        for mode in CAL_MODES:
            row[mode] = tokens_by_mode.get(mode, {}).get(field, "0")
        rows.append(row)
    return pd.DataFrame(rows)


def _normalize_token(v) -> str:
    t = str(v).strip().upper()
    if t in {"ZERO", "0.0", "0"}:
        return "0"
    if t in {"E16", "E17"}:
        return t
    raise ValueError(f"Invalid token '{v}'. Allowed: 0, E16, E17")


def _tokens_by_mode_from_df(df: pd.DataFrame) -> dict:
    out = {mode: {} for mode in CAL_MODES}
    for _, row in df.iterrows():
        field = str(row.get("Field", "")).strip()
        if field not in REAL_FIELD_KEYS:
            continue
        for mode in CAL_MODES:
            out[mode][field] = _normalize_token(row.get(mode, "0"))
    return out


def _build_real_range_debug(master: dict[str, float]) -> pd.DataFrame:
    """real 값(F30~F45)이 기준 min/max 범위 안에 있는지 확인용 테이블 생성."""
    checks = [
        ("T1a UP", "E20_T1a_min_up", "E21_T1a_max_up", ["F30_real_T1a_max_up", "F31_real_T1a_min_up"]),
        ("T1a CP DL", "E22_T1a_min_cp_dl", "E23_T1a_max_cp_dl", ["F32_real_T1a_max_cp_dl", "F33_real_T1a_min_cp_dl"]),
        ("T1a CP UL", "E25_T1a_min_cp_ul", "E26_T1a_max_cp_ul", ["F34_real_T1a_max_cp_ul", "F35_real_T1a_min_cp_ul"]),
        ("Ta4 UL", "E27_Ta4_min_ul", "E28_Ta4_max_ul", ["F36_real_Ta4_min_ul", "F37_real_Ta4_max_ul"]),
    ]

    # E-키 기반이 아닌 항목은 계산식으로 구성
    computed_ranges = {
        "F38_real_T2a_max_up": ("T2a UP", -master["E5_t2a_max_up"], -master["E4_t2a_min_up"]),
        "F39_real_T2a_min_up": ("T2a UP", -master["E5_t2a_max_up"], -master["E4_t2a_min_up"]),
        "F40_real_T2a_max_cp_dl": ("T2a CP DL", -master["E7_t2a_max_cp_dl"], -master["E6_t2a_min_cp_dl"]),
        "F41_real_T2a_min_cp_dl": ("T2a CP DL", -master["E7_t2a_max_cp_dl"], -master["E6_t2a_min_cp_dl"]),
        "F42_real_T2a_max_cp_ul": ("T2a CP UL", -master["E12_t2a_max_cp_ul"], -master["E11_t2a_min_cp_ul"]),
        "F43_real_T2a_min_cp_ul": ("T2a CP UL", -master["E12_t2a_max_cp_ul"], -master["E11_t2a_min_cp_ul"]),
        "F44_real_Ta3_min_ul": ("Ta3 UL", master["E9_ta3_min"], master["E10_ta3_max"]),
        "F45_real_Ta3_max_ul": ("Ta3 UL", master["E9_ta3_min"], master["E10_ta3_max"]),
    }

    rows = []
    for label, min_key, max_key, real_keys in checks:
        lo = master.get(min_key)
        hi = master.get(max_key)
        if lo is None or hi is None:
            continue
        low, high = (lo, hi) if lo <= hi else (hi, lo)
        for real_key in real_keys:
            real_val = master.get(real_key)
            status = "PASS" if real_val is not None and low <= real_val <= high else "OUT"
            rows.append({
                "Group": label,
                "Expected Min": low,
                "Real Key": real_key,
                "Real Value": real_val,
                "Expected Max": high,
                "In Range": status,
            })

    for real_key, (group, lo, hi) in computed_ranges.items():
        real_val = master.get(real_key)
        low, high = (lo, hi) if lo <= hi else (hi, lo)
        status = "PASS" if real_val is not None and low <= real_val <= high else "OUT"
        rows.append({
            "Group": group,
            "Expected Min": low,
            "Real Key": real_key,
            "Real Value": real_val,
            "Expected Max": high,
            "In Range": status,
        })

    return pd.DataFrame(rows)


_ensure_state()

st.title("Timing tool - RL1 PD US EngSupport & Poc")


# -------------------------
# Sidebar: Upload + Calibration buttons + Config
# -------------------------
with st.sidebar:
    st.header("1) Upload DelayData (.xlsx)")

    up = st.file_uploader(
        "Upload any .xlsx with columns: Category / Metric / Value",
        type=["xlsx"],
        accept_multiple_files=False,
    )
    target = st.radio("Apply to", options=["ODU", "ORU", "Both"], horizontal=True)

    if up is not None:
        st.caption(f"Uploaded file: {up.name}")

        try:
            upload = read_delay_upload_xlsx(up.getvalue())  # 파일명 고정 없음
            st.success(f"Parsed OK (sheet: {upload.sheet_used})")

            if st.button(f"Update {target}", type="primary"):
                st.session_state.delay_df = apply_upload_to_delaydata(
                    st.session_state.delay_df,
                    upload.values,
                    target=target,
                )
                st.success(f"DelayData updated: {target}")
                st.rerun()
        except Exception as e:
            st.error(str(e))

    st.divider()

    st.header("2) Calibration")
    st.caption(f"Current mode: {st.session_state.cal_mode}")

    c1, c2 = st.columns(2)
    c3, c4 = st.columns(2)

    if c1.button("Apply 15/30km"):
        st.session_state.cal_mode = CAL_15_30
        st.rerun()

    if c2.button("Apply 40km"):
        st.session_state.cal_mode = CAL_40
        st.rerun()

    if c3.button("Apply minimum"):
        st.session_state.cal_mode = CAL_MINIMUM
        st.rerun()

    if c4.button("Calibration Reset", type="secondary"):
        st.session_state.cal_mode = CAL_NONE
        st.rerun()

    with st.expander("Calibration offset map (per mode / field)", expanded=False):
        st.caption("Set each field token by mode. Allowed tokens: 0, E16, E17")
        token_df = _calibration_tokens_df(st.session_state.calibration_offsets_by_mode)
        edited_tokens_df = st.data_editor(
            token_df,
            use_container_width=True,
            num_rows="fixed",
            key="calibration_offsets_editor",
            hide_index=True,
            column_config={
                "Field": st.column_config.TextColumn("Field", disabled=True),
                CAL_NONE: st.column_config.SelectboxColumn(CAL_NONE, options=["0", "E16", "E17"]),
                CAL_15_30: st.column_config.SelectboxColumn(CAL_15_30, options=["0", "E16", "E17"]),
                CAL_40: st.column_config.SelectboxColumn(CAL_40, options=["0", "E16", "E17"]),
                CAL_MINIMUM: st.column_config.SelectboxColumn(CAL_MINIMUM, options=["0", "E16", "E17"]),
            },
        )

        c_apply, c_reset = st.columns(2)
        if c_apply.button("Apply calibration offset map"):
            try:
                st.session_state.calibration_offsets_by_mode = _tokens_by_mode_from_df(edited_tokens_df)
                st.success("Calibration offset map applied.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
        if c_reset.button("Reset offset map", type="secondary"):
            st.session_state.calibration_offsets_by_mode = default_calibration_field_tokens()
            st.success("Calibration offset map reset to defaults.")
            st.rerun()

    st.divider()

    st.header("3) RU/DU Config (Master)")
    st.caption("Import the downloaded delay row file (CSV/XLSX). Only t12_max/min are editable.")

    # cfg UI inputs (key 기반)
    cfg = dict(st.session_state.cfg)

    # # RU parameters
    # cfg["t2a_min_up"] = _num_input("cfg_t2a_min_up", "t2a_min_up (E4)", cfg["t2a_min_up"])
    # cfg["t2a_max_up"] = _num_input("cfg_t2a_max_up", "t2a_max_up (E5)", cfg["t2a_max_up"])
    # cfg["tcp_adv_dl"] = _num_input("cfg_tcp_adv_dl", "tcp_adv_dl (E8)", cfg["tcp_adv_dl"])
    # cfg["ta3_min"] = _num_input("cfg_ta3_min", "ta3_min (E9)", cfg["ta3_min"])
    # cfg["ta3_max"] = _num_input("cfg_ta3_max", "ta3_max (E10)", cfg["ta3_max"])
    # cfg["t2a_min_cp_ul"] = _num_input("cfg_t2a_min_cp_ul", "t2a_min_cp_ul (E11)", cfg["t2a_min_cp_ul"])
    # cfg["t2a_max_cp_ul"] = _num_input("cfg_t2a_max_cp_ul", "t2a_max_cp_ul (E12)", cfg["t2a_max_cp_ul"])

    # # DU parameters (Excel uses negative)
    # # UI에서는 양수로 입력받고 내부에서 음수로 강제 (엑셀 방식과 동일하게 맞춤)
    # st.number_input("t12_max (µs) (enter positive)", key="t12_max_ui", value=10.0)
    # st.number_input("t12_min (µs) (enter positive)", key="t12_min_ui", value=5.0)
    profile_cfg_file = st.file_uploader(
        "Import profile delay row (Bandwidth/SCS/T2a... columns)",
        type=["csv", "xlsx"],
        accept_multiple_files=False,
        key="profile_cfg_file",
    )

    if profile_cfg_file is not None:
        try:
            imported_cfg = _read_profile_cfg_upload(profile_cfg_file)
            preview_df = pd.DataFrame([{
                "t2a_min_up": imported_cfg["t2a_min_up"],
                "t2a_max_up": imported_cfg["t2a_max_up"],
                "tcp_adv_dl": imported_cfg["tcp_adv_dl"],
                "ta3_min": imported_cfg["ta3_min"],
                "ta3_max": imported_cfg["ta3_max"],
                "t2a_min_cp_ul": imported_cfg["t2a_min_cp_ul"],
                "t2a_max_cp_ul": imported_cfg["t2a_max_cp_ul"],
            }])
            st.caption("Imported values preview (µs):")
            st.dataframe(preview_df, use_container_width=True)

            if st.button("Apply imported RU config", type="primary"):
                cfg.update(imported_cfg)
                st.session_state.cfg = cfg
                st.session_state["cfg_t2a_min_up"] = cfg["t2a_min_up"]
                st.session_state["cfg_t2a_max_up"] = cfg["t2a_max_up"]
                st.session_state["cfg_tcp_adv_dl"] = cfg["tcp_adv_dl"]
                st.session_state["cfg_ta3_min"] = cfg["ta3_min"]
                st.session_state["cfg_ta3_max"] = cfg["ta3_max"]
                st.session_state["cfg_t2a_min_cp_ul"] = cfg["t2a_min_cp_ul"]
                st.session_state["cfg_t2a_max_cp_ul"] = cfg["t2a_max_cp_ul"]
                st.success("Imported RU config applied.")
                st.rerun()
        except Exception as e:
            st.error(str(e))

    cfg["t2a_min_up"] = _num_input("cfg_t2a_min_up", "t2a_min_up (E4)", cfg["t2a_min_up"], disabled=True)
    cfg["t2a_max_up"] = _num_input("cfg_t2a_max_up", "t2a_max_up (E5)", cfg["t2a_max_up"], disabled=True)
    cfg["tcp_adv_dl"] = _num_input("cfg_tcp_adv_dl", "tcp_adv_dl (E8)", cfg["tcp_adv_dl"], disabled=True)
    cfg["ta3_min"] = _num_input("cfg_ta3_min", "ta3_min (E9)", cfg["ta3_min"], disabled=True)
    cfg["ta3_max"] = _num_input("cfg_ta3_max", "ta3_max (E10)", cfg["ta3_max"], disabled=True)
    cfg["t2a_min_cp_ul"] = _num_input("cfg_t2a_min_cp_ul", "t2a_min_cp_ul (E11)", cfg["t2a_min_cp_ul"], disabled=True)
    cfg["t2a_max_cp_ul"] = _num_input("cfg_t2a_max_cp_ul", "t2a_max_cp_ul (E12)", cfg["t2a_max_cp_ul"], disabled=True)

    if "t12_max_ui" not in st.session_state:
        st.session_state["t12_max_ui"] = abs(float(cfg["t12_max"]))
    if "t12_min_ui" not in st.session_state:
        st.session_state["t12_min_ui"] = abs(float(cfg["t12_min"]))

    st.number_input("t12_max (µs) (enter positive)", key="t12_max_ui", format="%.2f", step=0.01)
    st.number_input("t12_min (µs) (enter positive)", key="t12_min_ui", format="%.2f", step=0.01)

    cfg["t12_max"] = -abs(float(st.session_state["t12_max_ui"]))
    cfg["t12_min"] = -abs(float(st.session_state["t12_min_ui"]))

    cfg["calibration_offsets_by_mode"] = st.session_state.calibration_offsets_by_mode

    st.session_state.cfg = cfg


# -------------------------
# Main: DelayData editor
# -------------------------
st.subheader("DelayData (internal table)")
st.caption("ODU 8 rows + ORU 8 rows. You can also edit values manually.")

edited = st.data_editor(
    st.session_state.delay_df,
    use_container_width=True,
    num_rows="fixed",
    key="delay_editor",
)

st.session_state.delay_df = edited


# -------------------------
# Compute + Show Results
# -------------------------
st.subheader("Compute Results")

colA, colB = st.columns([1, 1], gap="large")

try:
    result = compute(
        delay_df=st.session_state.delay_df,
        cfg=st.session_state.cfg,
        cal_mode=st.session_state.cal_mode,
    )

    with colA:
        st.markdown("### DL Parameters")
        st.dataframe(result.dl, use_container_width=True)

        dl_bytes = _xlsx_bytes_from_df("DL", result.dl)
        st.download_button(
            "Download DL.xlsx",
            data=dl_bytes,
            file_name=f"DL_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with colB:
        st.markdown("### UL Parameters")
        st.dataframe(result.ul, use_container_width=True)

        ul_bytes = _xlsx_bytes_from_df("UL", result.ul)
        st.download_button(
            "Download UL.xlsx",
            data=ul_bytes,
            file_name=f"UL_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with st.expander("Master (debug view)"):
        master_df = pd.DataFrame([{"Key": k, "Value": v} for k, v in result.master.items()])
        st.dataframe(master_df, use_container_width=True)
    
    with st.expander("Real vs Expected Range Check (debug)"):
        st.caption("Check whether each real timing value is between expected min/max.")
        range_debug_df = _build_real_range_debug(result.master)
        st.dataframe(range_debug_df, use_container_width=True)

except Exception as e:
    st.error(f"Compute failed: {e}")
    st.info("Tip: Verify that all 16 values (ODU/ORU) in the Delay Data field are filled in..")