"""
시나리오 기반 학습/검증용 데이터 생성기

사용법:
  python manage.py generate_scenario_data           # 기본 (가스+전력 전체)
  python manage.py generate_scenario_data --gas     # 가스만
  python manage.py generate_scenario_data --power   # 전력만
  python manage.py generate_scenario_data --clear   # 기존 시나리오 데이터 삭제 후 재생성
"""

import random
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from monitoring.models import Device, DeviceChannel, GasReading, PowerReading

GAS_FIELDS = ["co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc"]

SCENARIO_TAG = "scenario_generated"

# ── 유틸 ────────────────────────────────────────────────────────────────────

def rnd(lo, hi, decimals=2):
    return round(random.uniform(lo, hi), decimals)

def lerp(start, end, steps):
    """start → end 를 steps 개로 선형 보간"""
    return [round(start + (end - start) * i / max(steps - 1, 1), 3) for i in range(steps)]

def make_ts(base_dt, minutes):
    return base_dt + timedelta(minutes=minutes)


# ── 가스 시나리오 정의 ────────────────────────────────────────────────────────

def scenario_A_normal(base_dt, count=60):
    """정상 운영 — Isolation Forest 학습용 기준선"""
    rows = []
    for i in range(count):
        rows.append({
            "measured_at": make_ts(base_dt, i),
            "co":  rnd(5, 18),
            "h2s": rnd(0, 3),
            "co2": rnd(400, 700),
            "o2":  rnd(20.5, 21.0),
            "no2": rnd(0.5, 2.0),
            "so2": rnd(0.2, 1.5),
            "o3":  rnd(0.01, 0.04),
            "nh3": rnd(2, 10),
            "voc": rnd(0.1, 0.3),
            "quality_flag": "ok",
            "scenario": "normal_operation",
            "phase": "normal",
            "expected_status": "normal",
            "is_anomaly": False,
        })
    return rows


def scenario_B_ventilation(base_dt):
    """환기 불량 — ARIMA + Change Point 검증용"""
    rows = []
    # 정상 30분
    for i in range(30):
        rows.append({
            "measured_at": make_ts(base_dt, i),
            "co": rnd(5, 15), "h2s": rnd(0, 2),
            "co2": rnd(430, 600), "o2": rnd(20.6, 20.8),
            "no2": rnd(0.5, 1.5), "so2": rnd(0.1, 0.8),
            "o3": rnd(0.01, 0.03), "nh3": rnd(2, 8), "voc": rnd(0.15, 0.22),
            "quality_flag": "ok",
            "scenario": "ventilation_failure", "phase": "normal",
            "expected_status": "normal", "is_anomaly": False,
        })
    # 전조 15분 (CO2 서서히 상승)
    co2_vals = lerp(650, 970, 15)
    o2_vals  = lerp(20.5, 20.1, 15)
    voc_vals = lerp(0.25, 0.38, 15)
    for i, (c, o, v) in enumerate(zip(co2_vals, o2_vals, voc_vals)):
        rows.append({
            "measured_at": make_ts(base_dt, 30 + i),
            "co": rnd(8, 20), "h2s": rnd(0, 2),
            "co2": c + rnd(-10, 10), "o2": o + rnd(-0.05, 0.05),
            "no2": rnd(0.5, 1.5), "so2": rnd(0.1, 0.8),
            "o3": rnd(0.01, 0.03), "nh3": rnd(2, 8), "voc": v + rnd(-0.02, 0.02),
            "quality_flag": "ok",
            "scenario": "ventilation_failure", "phase": "early_warning",
            "expected_status": "predictive_warning", "is_anomaly": True,
        })
    # 주의 20분
    co2_vals = lerp(1000, 1500, 20)
    o2_vals  = lerp(20.0, 19.5, 20)
    voc_vals = lerp(0.38, 0.48, 20)
    for i, (c, o, v) in enumerate(zip(co2_vals, o2_vals, voc_vals)):
        rows.append({
            "measured_at": make_ts(base_dt, 45 + i),
            "co": rnd(10, 25), "h2s": rnd(0, 2),
            "co2": c + rnd(-20, 20), "o2": o + rnd(-0.05, 0.05),
            "no2": rnd(0.5, 2.0), "so2": rnd(0.1, 1.0),
            "o3": rnd(0.01, 0.04), "nh3": rnd(2, 10), "voc": v,
            "quality_flag": "ok",
            "scenario": "ventilation_failure", "phase": "warning",
            "expected_status": "warning", "is_anomaly": True,
        })
    # 복귀 10분
    co2_vals = lerp(1500, 700, 10)
    o2_vals  = lerp(19.5, 20.6, 10)
    for i, (c, o) in enumerate(zip(co2_vals, o2_vals)):
        rows.append({
            "measured_at": make_ts(base_dt, 65 + i),
            "co": rnd(5, 15), "h2s": rnd(0, 2),
            "co2": c, "o2": o,
            "no2": rnd(0.5, 1.5), "so2": rnd(0.1, 0.8),
            "o3": rnd(0.01, 0.03), "nh3": rnd(2, 8), "voc": rnd(0.15, 0.25),
            "quality_flag": "ok",
            "scenario": "ventilation_failure", "phase": "recovery",
            "expected_status": "normal", "is_anomaly": False,
        })
    return rows


def scenario_C_oxygen(base_dt):
    """산소 농도 저하 — Z-score 역방향 검증"""
    rows = []
    o2_full  = lerp(20.8, 15.8, 40)
    co2_full = lerp(450, 1120, 40)
    phases = (
        [(20.8, 20.5, "normal",             "normal",              False)] * 10 +
        [(19.8, 18.5, "early_warning",      "predictive_warning",  True)]  * 10 +
        [(17.9, 16.5, "warning",            "warning",             True)]  * 10 +
        [(15.9, 14.0, "danger",             "danger",              True)]  * 10
    )
    for i, (o2, co2) in enumerate(zip(o2_full, co2_full)):
        _, _, phase, status, anomaly = phases[i]
        rows.append({
            "measured_at": make_ts(base_dt, i),
            "co": rnd(5, 15), "h2s": rnd(0, 2),
            "co2": co2 + rnd(-20, 20), "o2": o2 + rnd(-0.05, 0.05),
            "no2": rnd(0.5, 1.5), "so2": rnd(0.1, 0.8),
            "o3": rnd(0.01, 0.03), "nh3": rnd(2, 8), "voc": rnd(0.1, 0.25),
            "quality_flag": "ok",
            "scenario": "oxygen_depletion", "phase": phase,
            "expected_status": status, "is_anomaly": anomaly,
        })
    return rows


def scenario_D_h2s(base_dt):
    """H2S 급성 누출 — Z-score + Threshold 검증"""
    h2s_seq = [1.0, 1.2, 1.1, 1.3, 1.0, 7.0, 11.0, 14.0, 16.5, 18.0, 15.0, 9.0, 2.0, 1.5, 1.2]
    statuses = [
        "normal","normal","normal","normal","normal",
        "anomaly","warning","warning","danger","danger","danger",
        "warning","normal","normal","normal",
    ]
    phases = [
        "normal","normal","normal","normal","normal",
        "anomaly_spike","warning","warning","danger","danger","danger",
        "recovery","recovery","recovery","recovery",
    ]
    is_anomalies = [False]*5 + [True]*6 + [False]*4
    for i, (h, s, p, a) in enumerate(zip(h2s_seq, statuses, phases, is_anomalies)):
        rows_item = {
            "measured_at": make_ts(base_dt, i),
            "co": rnd(5, 15), "h2s": h + rnd(-0.1, 0.1),
            "co2": rnd(400, 600), "o2": rnd(20.5, 21.0),
            "no2": rnd(0.5, 1.5), "so2": rnd(0.1, 0.8),
            "o3": rnd(0.01, 0.03), "nh3": rnd(2, 8), "voc": rnd(0.1, 0.25),
            "quality_flag": "ok",
            "scenario": "h2s_acute_leak", "phase": p,
            "expected_status": s, "is_anomaly": a,
        }
        yield rows_item


def scenario_E_co(base_dt):
    """CO 연소 이상 — Isolation Forest 복합 패턴"""
    co_vals  = lerp(8,  210, 30)
    o2_vals  = lerp(20.8, 18.7, 30)
    co2_vals = lerp(450, 1300, 30)
    phases_map = [
        ("normal",        "normal",              False)] * 8 + [
        ("early_warning", "predictive_warning",  True)]  * 8 + [
        ("warning",       "warning",             True)]  * 8 + [
        ("danger",        "danger",              True)]  * 6
    for i, (co, o2, co2) in enumerate(zip(co_vals, o2_vals, co2_vals)):
        p, s, a = phases_map[i]
        yield {
            "measured_at": make_ts(base_dt, i),
            "co": co + rnd(-2, 2), "h2s": rnd(0, 2),
            "co2": co2 + rnd(-20, 20), "o2": o2 + rnd(-0.05, 0.05),
            "no2": rnd(0.5, 1.5), "so2": rnd(0.1, 0.8),
            "o3": rnd(0.01, 0.03), "nh3": rnd(2, 8), "voc": rnd(0.1, 0.3),
            "quality_flag": "ok",
            "scenario": "co_combustion", "phase": p,
            "expected_status": s, "is_anomaly": a,
        }


def scenario_F_voc(base_dt):
    """VOC 작업환경 변화 — Change Point 검증"""
    voc_vals = lerp(0.18, 1.15, 35)
    for i, v in enumerate(voc_vals):
        if v < 0.35:
            phase, status, anomaly = "normal", "normal", False
        elif v < 0.5:
            phase, status, anomaly = "early_warning", "predictive_warning", True
        elif v < 1.0:
            phase, status, anomaly = "warning", "warning", True
        else:
            phase, status, anomaly = "danger", "danger", True
        yield {
            "measured_at": make_ts(base_dt, i),
            "co": rnd(5, 15), "h2s": rnd(0, 2),
            "co2": rnd(450, 900), "o2": rnd(20.3, 20.8),
            "no2": rnd(0.5, 1.5), "so2": rnd(0.1, 0.8),
            "o3": rnd(0.01, 0.04), "nh3": rnd(2, 8), "voc": v + rnd(-0.02, 0.02),
            "quality_flag": "ok",
            "scenario": "voc_work_change", "phase": phase,
            "expected_status": status, "is_anomaly": anomaly,
        }


def scenario_G_complex(base_dt):
    """복합 이상 패턴 — Isolation Forest 전용"""
    for i in range(20):
        yield {
            "measured_at": make_ts(base_dt, i),
            "co":  rnd(60, 90),  "h2s": rnd(6, 10),
            "co2": rnd(850, 1000), "o2": rnd(18.0, 18.8),
            "no2": rnd(2.0, 3.5), "so2": rnd(1.0, 2.0),
            "o3": rnd(0.04, 0.08), "nh3": rnd(15, 25), "voc": rnd(0.4, 0.55),
            "quality_flag": "ok",
            "scenario": "complex_anomaly", "phase": "multi_sensor_anomaly",
            "expected_status": "anomaly", "is_anomaly": True,
        }


def scenario_H_sensor_error(base_dt):
    """센서 오류 / 통신 불량 — AI 학습 제외 대상"""
    for i in range(10):
        err_type = random.choice(["comm_err", "missing", "partial"])
        if err_type == "comm_err":
            row = {f: -1.0 for f in GAS_FIELDS}
            qf = "comm_err"
        elif err_type == "missing":
            row = {f: None for f in GAS_FIELDS}
            qf = "missing"
        else:
            row = {f: rnd(5, 20) for f in GAS_FIELDS}
            row["co2"] = None
            qf = "partial"
        row.update({
            "measured_at": make_ts(base_dt, i),
            "quality_flag": qf,
            "scenario": "sensor_error", "phase": err_type,
            "expected_status": "ignored", "is_anomaly": False,
        })
        yield row


# ── 전력 시나리오 정의 ────────────────────────────────────────────────────────

def scenario_I_power_normal(base_dt, count=60):
    """정상 사용 — 전력 AI 학습용"""
    rows = []
    for i in range(count):
        hour = (base_dt + timedelta(minutes=i)).hour
        if 9 <= hour < 12 or 13 <= hour < 18:
            cur = rnd(8, 14)
        elif 12 <= hour < 13:
            cur = rnd(4, 7)
        else:
            cur = rnd(1, 3)
        vol = rnd(218, 222)
        rows.append({
            "measured_at": make_ts(base_dt, i),
            "current_a": int(cur), "voltage_v": int(vol),
            "power_w": int(cur * vol),
            "quality_flag": "ok",
            "scenario": "normal_power", "phase": "normal",
            "expected_status": "normal", "is_anomaly": False,
        })
    return rows


def scenario_J_overload(base_dt):
    """전력 과부하 — Z-score + Isolation Forest"""
    cur_vals = lerp(9, 25, 25)
    vol_vals = lerp(220, 216, 25)
    phases_map = (
        [("normal",        "normal",             False)] * 8 +
        [("early_warning", "predictive_warning", True)]  * 7 +
        [("overload",      "danger",             True)]  * 7 +
        [("recovery",      "normal",             False)] * 3
    )
    for i, (cur, vol) in enumerate(zip(cur_vals, vol_vals)):
        phase, status, anomaly = phases_map[i]
        yield {
            "measured_at": make_ts(base_dt, i),
            "current_a": int(cur + rnd(-0.5, 0.5)),
            "voltage_v": int(vol + rnd(-1, 1)),
            "power_w":   int(cur * vol),
            "quality_flag": "ok",
            "scenario": "power_overload", "phase": phase,
            "expected_status": status, "is_anomaly": anomaly,
        }


def scenario_K_night_abnormal(base_dt):
    """야간 비정상 지속 사용"""
    for i in range(20):
        yield {
            "measured_at": make_ts(base_dt, i),
            "current_a": int(rnd(12, 16)),
            "voltage_v": int(rnd(219, 221)),
            "power_w":   int(rnd(2600, 3520)),
            "quality_flag": "ok",
            "scenario": "night_abnormal", "phase": "continuous_use",
            "expected_status": "anomaly", "is_anomaly": True,
        }


def scenario_L_motor_lock(base_dt):
    """모터 고착 — 전압 안정 + 전류 급증"""
    cur_vals = [10, 11, 18, 26, 30, 28, 25]
    vol_vals = [220, 220, 219, 219, 218, 218, 219]
    statuses = ["normal","normal","anomaly","danger","danger","danger","warning"]
    anomalies = [False, False, True, True, True, True, True]
    for i, (cur, vol, s, a) in enumerate(zip(cur_vals, vol_vals, statuses, anomalies)):
        yield {
            "measured_at": make_ts(base_dt, i),
            "current_a": cur, "voltage_v": vol, "power_w": cur * vol,
            "quality_flag": "ok",
            "scenario": "motor_lock", "phase": s,
            "expected_status": s, "is_anomaly": a,
        }


def scenario_M_comm_error(base_dt):
    """통신 불량"""
    for i in range(8):
        yield {
            "measured_at": make_ts(base_dt, i),
            "current_a": -1, "voltage_v": -1, "power_w": -1,
            "quality_flag": "comm_err",
            "scenario": "power_comm_error", "phase": "communication_failure",
            "expected_status": "ignored", "is_anomaly": False,
        }


# ── Django Command ───────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "시나리오 기반 학습/검증용 GasReading·PowerReading 생성"

    def add_arguments(self, parser):
        parser.add_argument("--gas",   action="store_true", help="가스 시나리오만")
        parser.add_argument("--power", action="store_true", help="전력 시나리오만")
        parser.add_argument("--clear", action="store_true", help="기존 시나리오 데이터 삭제 후 재생성")

    def handle(self, *args, **options):
        do_gas   = options["gas"]   or not options["power"]
        do_power = options["power"] or not options["gas"]

        gas_device   = Device.objects.filter(device_type="gas").first()
        power_device = Device.objects.filter(device_type="power").first()

        if do_gas and not gas_device:
            self.stderr.write("가스 장비 없음 — 먼저 seed를 실행하세요.")
            return
        if do_power and not power_device:
            self.stderr.write("전력 장비 없음 — 먼저 seed를 실행하세요.")
            return

        if options["clear"]:
            if do_gas:
                deleted, _ = GasReading.objects.filter(
                    raw_payload__scenario_tag=SCENARIO_TAG
                ).delete()
                self.stdout.write(f"  기존 가스 시나리오 데이터 {deleted}건 삭제")
            if do_power:
                deleted, _ = PowerReading.objects.filter(
                    raw_payload__scenario_tag=SCENARIO_TAG
                ).delete()
                self.stdout.write(f"  기존 전력 시나리오 데이터 {deleted}건 삭제")

        now = timezone.now().replace(second=0, microsecond=0)
        base = now - timedelta(hours=6)

        # ── 가스 시나리오 ─────────────────────────────────
        if do_gas:
            self.stdout.write("▶ 가스 시나리오 생성 중...")
            gas_total = 0

            scenarios = [
                ("A 정상운영",    scenario_A_normal(base,                      count=200)),
                ("B 환기불량",    scenario_B_ventilation(base - timedelta(hours=5))),
                ("C 산소저하",    scenario_C_oxygen(base - timedelta(hours=4))),
                ("D H2S누출",     list(scenario_D_h2s(base - timedelta(hours=3)))),
                ("E CO연소이상",  list(scenario_E_co(base - timedelta(hours=3, minutes=30)))),
                ("F VOC변화",     list(scenario_F_voc(base - timedelta(hours=2)))),
                ("G 복합이상",    list(scenario_G_complex(base - timedelta(hours=1)))),
                ("H 센서오류",    list(scenario_H_sensor_error(base - timedelta(minutes=30)))),
            ]

            for label, rows in scenarios:
                bulk = []
                for r in rows:
                    payload = {f: r.get(f) for f in GAS_FIELDS}
                    payload.update({
                        "scenario":        r["scenario"],
                        "phase":           r["phase"],
                        "expected_status": r["expected_status"],
                        "is_anomaly":      r["is_anomaly"],
                        "scenario_tag":    SCENARIO_TAG,
                    })
                    bulk.append(GasReading(
                        device=gas_device,
                        measured_at=r["measured_at"],
                        co=r.get("co"), h2s=r.get("h2s"), co2=r.get("co2"),
                        o2=r.get("o2"), no2=r.get("no2"), so2=r.get("so2"),
                        o3=r.get("o3"), nh3=r.get("nh3"), voc=r.get("voc"),
                        quality_flag=r.get("quality_flag", "ok"),
                        raw_payload=payload,
                    ))
                GasReading.objects.bulk_create(bulk, ignore_conflicts=True)
                gas_total += len(bulk)
                self.stdout.write(f"  {label}: {len(bulk)}건")

            self.stdout.write(self.style.SUCCESS(f"  가스 합계: {gas_total}건"))

        # ── 전력 시나리오 ─────────────────────────────────
        if do_power:
            self.stdout.write("▶ 전력 시나리오 생성 중...")

            channel = DeviceChannel.objects.filter(device=power_device).first()
            if not channel:
                self.stderr.write("전력 채널 없음 — seed를 먼저 실행하세요.")
                return

            power_total = 0
            pwr_scenarios = [
                ("I 정상사용",       scenario_I_power_normal(base,                      count=60)),
                ("J 과부하",         list(scenario_J_overload(base - timedelta(hours=4)))),
                ("K 야간비정상",     list(scenario_K_night_abnormal(base - timedelta(hours=3)))),
                ("L 모터고착",       list(scenario_L_motor_lock(base - timedelta(hours=2)))),
                ("M 통신불량",       list(scenario_M_comm_error(base - timedelta(hours=1)))),
            ]

            for label, rows in pwr_scenarios:
                bulk = []
                for r in rows:
                    payload = {
                        "current_a": r["current_a"],
                        "voltage_v": r["voltage_v"],
                        "power_w":   r["power_w"],
                        "scenario":        r["scenario"],
                        "phase":           r["phase"],
                        "expected_status": r["expected_status"],
                        "is_anomaly":      r["is_anomaly"],
                        "scenario_tag":    SCENARIO_TAG,
                    }
                    bulk.append(PowerReading(
                        device=power_device,
                        channel=channel,
                        measured_at=r["measured_at"],
                        current_a=r["current_a"],
                        voltage_v=r["voltage_v"],
                        power_w=r["power_w"],
                        quality_flag=r.get("quality_flag", "ok"),
                        raw_payload=payload,
                    ))
                PowerReading.objects.bulk_create(bulk, ignore_conflicts=True)
                power_total += len(bulk)
                self.stdout.write(f"  {label}: {len(bulk)}건")

            self.stdout.write(self.style.SUCCESS(f"  전력 합계: {power_total}건"))

        self.stdout.write(self.style.SUCCESS("✅ 시나리오 데이터 생성 완료"))
        self.stdout.write("  검증: python manage.py generate_scenario_data --clear 로 재생성 가능")
