# constants.py
from __future__ import annotations

# DelayData(ODU/ORU)에서 "8개 값"의 고정 순서 (엑셀 DelayData 시트 행 순서와 동일)
DELAY_KEYS_ORDER = [
    ("User plane DL", "Min Delay (µs)"),
    ("User plane DL", "Max Delay (µs)"),
    ("Control Plane DL", "Min Delay (µs)"),
    ("Control Plane DL", "Max Delay (µs)"),
    ("Control Plane UL", "Min Delay (µs)"),
    ("Control Plane UL", "Max Delay (µs)"),
    ("User plane UL", "Min Delay (µs)"),
    ("User plane UL", "Max Delay (µs)"),
]

# 업로드 파일(ecpri_analysis.xlsx)에서 기대하는 컬럼명(유연하게 normalize 해서 맞춰줄 예정)
EXPECTED_COLUMNS = {"category", "metric", "value"}

# Calibration 모드
CAL_MINIMUM = "minimum"
CAL_15_30 = "15/30km"
CAL_40 = "40km"
CAL_NONE = "none"


CAL_MODES = [CAL_15_30, CAL_40, CAL_MINIMUM, CAL_NONE]