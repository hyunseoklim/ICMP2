"""
fake_data2 — AI 통합 검증 스토리(보고서 5.2.4) 결정론적 생성기.

부하테스트용 fake_data.py(확률적 spike)와 *별개*. 본 모듈은 "어느 공장의
어느 오전"(08:45~09:30) 시나리오를 1 논리분=1 tick으로 재생하기 위한
**결정론적** 데이터를 생성한다. 송신은 하지 않는다 — main.py가 sender.py로
보낸다(fake_data.py와 동일한 책임 분리).

설계 원칙 (docs/plans/ai-story-verification.md §1.2):
    1. 1 tick = STORY_STEP 논리분(밀도 5). STORY_START(08:00)~STORY_END(10:05).
    2. measured_at = 실제 now (가상시각 ❌ — is_stale·중복방지 정합 보존).
       "논리분 m"은 값 계산용 인덱스일 뿐 타임스탬프가 아니다.
    3. CO2 = 완만 상승(+9.47/분) → 09:12 warn(1000) 사전경고 → 09:20 정점 ~1076
       → 완만 회복 하강(~-10/분) → 10:05 ~620(정상). 기울기를 CP 게이트(50ppm)
       미발화로 제한 + 미세 노이즈로 ARIMA 적합 안정화 → 전 구간 정규 예측.
    4. 키프레임만 정의하고 사이는 선형 보간.

대상 (라이브 DB 확정 2026-06-10):
    - 가스 : GAS-001 (배치 10,5)
    - 전력 : PWR-001 / slave61 충전스테이션 A (rated 1000W, active, 배치 10,20)
    - 작업자: worker_id 1~5 (fake_data.py와 동일 — 라이브 on_duty 6명 중 5명.
              6번째 확장은 실제 worker_id 확인 후 _WORKER_TRACK에 추가)
"""
import logging
import random
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# co2 센서 노이즈 — 완벽한 직선 램프는 ARIMA 적합을 NaN/Inf로 붕괴시킨다.
# 실제 센서처럼 미세 노이즈를 더해 적합을 안정화(50ppm CP 게이트엔 비발화).
# 시드 고정 → 재현 가능(스토리 결정론 유지).
_CO2_NOISE = random.Random(20260610)
CO2_NOISE_SIGMA = 3.0   # ppm


# ── 대상 식별자 (라이브 DB 확정) ──────────────────────────────
GAS_DEVICE_UID   = "GAS-001"
POWER_DEVICE_UID = "PWR-001"
POWER_CHANNEL    = "slave61"   # 충전스테이션 A, rated 1000W
FLOOR_ID         = 1


# ── 논리 시각 (분 인덱스) ─────────────────────────────────────
def M(hhmm: str) -> int:
    """'09:00' → 540(분). 값 계산용 인덱스이며 실제 시각이 아니다."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


STORY_START = M("08:00")
STORY_END   = M("10:05")   # 회복 하강 구간 확보 (co2 1076→620 완만 회복)

# 샘플 밀도 — 논리분당 점수. ARIMA가 CP magnitude_gate(50ppm)에 안 걸리려면
# 샘플당 기울기가 완만해야 한다(분당 5점 → CP anchor=None → 정규 경로 예측).
# 밀도 3 이하면 구간이 잘려 path=unknown. 검증 결과 5가 안정적.
STORY_DENSITY = 5
STORY_STEP    = 1.0 / STORY_DENSITY


# ── CO2: 완만 상승 → 정점(09:20) → 완만 회복 하강 (전 구간 ARIMA 정규경로) ──
# 상승·하강 모두 CP magnitude_gate(50ppm) 미발화 기울기(≈±10/분)로 제한.
#   상승: 08:15부터 +9.47/분 → 09:12 warn(1000) 도달(주의 사전경고) → 09:20 정점 ~1076.
#   회복: 09:20부터 ~-10/분 완만 하강 → STORY_END(10:05) ~620(정상). 주의→정상 단계적.
# 1800 등 급변 정점(+100/분)은 CP를 터뜨려 anchor가 박히고 구간이 잘려 unknown → 불가.
CO2_NORMAL     = 450.0
CO2_RAMP_START = M("08:15")    # 완만 상승 시작 (환기 실패 누적)
CO2_WARN_CROSS = M("09:12")    # warn(1000) 도달 — 주의 사전경고
CO2_PEAK_MIN   = M("09:20")    # 정점 (환기 복구 시점)
CO2_BASE       = 460.0
CO2_SLOPE      = (1000.0 - CO2_BASE) / (CO2_WARN_CROSS - CO2_RAMP_START)  # ≈ +9.47/분
CO2_PEAK       = CO2_BASE + CO2_SLOPE * (CO2_PEAK_MIN - CO2_RAMP_START)   # ≈ 1076
CO2_RECOVER    = 620.0         # 회복 종료값 (정상 구간)


# ── 가스 키프레임 (분 → 값). CO2 제외. 사이는 선형 보간 ───────
# no2/so2/o3/nh3는 전 구간 정상(_GAS_CONST).
# 조합 가스도 환기 실패의 결과 — 09:05 동시 비정상, 전력 복귀(09:20)까지 유지 후 정상.
_GAS_KF = {
    "o2":  [(STORY_START, 20.8), (M("09:04"), 20.8), (M("09:05"), 18.4),
            (M("09:20"), 18.4), (M("09:30"), 20.8)],
    "voc": [(STORY_START, 0.20), (M("09:04"), 0.20), (M("09:05"), 0.48),
            (M("09:20"), 0.48), (M("09:30"), 0.20)],
    "co":  [(STORY_START, 5.0),  (M("09:04"), 5.0),  (M("09:05"), 70.0),
            (M("09:20"), 70.0), (M("09:30"), 5.0)],
    "h2s": [(STORY_START, 2.0),  (M("09:04"), 2.0),  (M("09:05"), 8.0),
            (M("09:20"), 8.0),  (M("09:30"), 2.0)],
}
_GAS_CONST = {"no2": 1.0, "so2": 0.5, "o3": 0.02, "nh3": 5.0}


# ── 전력 키프레임 (분 → V, I, P) — 1000W 채널 ─────────────────
# 인과: 환기팬 이상이 *사건의 원인*. 08:09 이상 시작 → 08:11 위험(과부하) →
# 09:19까지 지속 → 09:20 조치로 정상 복귀. CO2 상승(08:15~)은 이 환기 실패의 결과.
# 08:09 load 48%(Threshold 침묵) → IF만 포착 / 08:11 load 85%(Threshold+IF)
_PWR_KF = [
    (STORY_START, 220.0, 1.66, 366.0),   # 08:00 정상 (load 37%)
    (M("08:08"),  220.0, 1.66, 366.0),   # 08:08 정상 유지
    (M("08:09"),  220.0, 3.00, 480.0),   # 08:09 환기팬 이상 — IF 고유 (load 48%)
    (M("08:10"),  220.0, 3.00, 480.0),   # 08:10 48% 유지 (IF 단독 구간)
    (M("08:11"),  220.0, 4.00, 850.0),   # 08:11 위험·과부하 (load 85%, Threshold+IF)
    (M("09:19"),  220.0, 4.00, 850.0),   # 과부하 지속 (환기 불능)
    (M("09:20"),  220.0, 1.66, 366.0),   # 09:20 조치 완료 — 정상 복귀
    (STORY_END,   220.0, 1.66, 366.0),
]


# ── 작업자 트랙 (worker_id → [(분, x, y)]) ────────────────────
# 작업영역(10~20,5~15) 군집 → 08:11 W3 환기팬(10,20) 점검 이동 → 09:12 전원 출구 대피.
# 출구 도달은 09:30 완료(즉시 대피) — STORY_END(10:05) 연장과 무관, 이후 외부 좌표 클램프 유지.
_WORKER_NAME = {1: "김철수", 2: "이영희", 3: "박민준", 4: "최수진", 5: "정도현"}
_EXIT = (45.0, 28.0)
_WORKER_TRACK = {
    1: [(STORY_START, 12.0,  8.0), (M("09:12"), 12.0,  8.0), (M("09:30"), *_EXIT)],
    2: [(STORY_START, 18.0, 12.0), (M("09:12"), 18.0, 12.0), (M("09:30"), *_EXIT)],
    3: [(STORY_START, 15.0, 10.0), (M("08:11"), 10.0, 20.0),   # 환기팬 이상 → 점검
        (M("09:12"), 10.0, 20.0), (M("09:20"), *_EXIT)],
    4: [(STORY_START, 20.0,  6.0), (M("09:12"), 20.0,  6.0), (M("09:30"), *_EXIT)],
    5: [(STORY_START, 14.0, 14.0), (M("09:12"), 14.0, 14.0), (M("09:30"), *_EXIT)],
}


# ── 보간 헬퍼 ────────────────────────────────────────────────
def _interp(kf: list, m: int) -> float:
    """(분, 값) 오름차순 리스트에서 m 위치 선형 보간. 양끝은 클램프."""
    if m <= kf[0][0]:
        return kf[0][1]
    if m >= kf[-1][0]:
        return kf[-1][1]
    for (m0, v0), (m1, v1) in zip(kf, kf[1:]):
        if m0 <= m <= m1:
            if m1 == m0:
                return v1
            return v0 + (v1 - v0) * (m - m0) / (m1 - m0)
    return kf[-1][1]


def _interp_pwr(m: int, idx: int) -> float:
    return _interp([(row[0], row[idx]) for row in _PWR_KF], m)


def _co2_at(m: int) -> float:
    """CO2 곡선: 정상 → 완만 상승(08:15~) → warn(1000)@09:12(주의 사전경고) →
    정점 ~1076@09:20(환기 복구) → 완만 회복 하강 ~620@STORY_END(주의→정상 단계적).

    상승·하강 모두 CP magnitude_gate(50ppm) 미발화 기울기(≈±10/분)로 제한해
    전 구간 ARIMA 정규 예측을 유지한다(실측값엔 generate_gas_tick에서 미세
    노이즈를 더해 직선 적합 붕괴를 방지)."""
    if m < CO2_RAMP_START:
        return CO2_NORMAL
    if m <= CO2_PEAK_MIN:
        return CO2_BASE + CO2_SLOPE * (m - CO2_RAMP_START)   # 09:12 → 1000, 09:20 → ~1076
    return _interp([(CO2_PEAK_MIN, CO2_PEAK), (STORY_END, CO2_RECOVER)], m)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── tick 생성기 (송신 X — dict 반환만) ────────────────────────
def generate_gas_tick(m: int) -> dict:
    """논리분 m의 가스 9종 payload. queue_gas_reading 규약과 일치."""
    data = {
        "type":        "gas",
        "device_uid":  GAS_DEVICE_UID,
        "measured_at": _now_iso(),
        "co2": round(_co2_at(m) + _CO2_NOISE.gauss(0, CO2_NOISE_SIGMA), 1),
        "o2":  round(_interp(_GAS_KF["o2"],  m), 2),
        "voc": round(_interp(_GAS_KF["voc"], m), 3),
        "co":  round(_interp(_GAS_KF["co"],  m), 1),
        "h2s": round(_interp(_GAS_KF["h2s"], m), 1),
    }
    data.update(_GAS_CONST)   # no2/so2/o3/nh3 (상시 정상)
    return data


def generate_power_tick(m: int) -> dict:
    """논리분 m의 전력 payload. post_power_reading 규약과 일치."""
    return {
        "type":         "power",
        "device_uid":   POWER_DEVICE_UID,
        "channel_code": POWER_CHANNEL,
        "measured_at":  _now_iso(),
        "voltage_v": round(_interp_pwr(m, 1), 1),
        "current_a": round(_interp_pwr(m, 2), 2),
        "power_w":   round(_interp_pwr(m, 3), 1),
    }


def generate_worker_ticks(m: int) -> list[dict]:
    """논리분 m의 작업자 위치들. post_location_reading 규약과 일치."""
    out = []
    for wid, track in _WORKER_TRACK.items():
        xs = [(t, x) for (t, x, _y) in track]
        ys = [(t, _y) for (t, _x, _y) in track]
        out.append({
            "type":        "location",
            "worker_id":   wid,
            "worker_name": _WORKER_NAME.get(wid, f"W{wid}"),
            "x":           round(_interp(xs, m), 2),
            "y":           round(_interp(ys, m), 2),
            "floor_id":    FLOOR_ID,
        })
    return out
