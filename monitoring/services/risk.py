"""
가스 위험도 계산 로직
"""
from monitoring.models import ThresholdPolicy


def get_thresholds() -> dict:
    """DB에서 임계치 정책 조회. 없으면 기본값 사용"""
    policies = ThresholdPolicy.objects.filter(is_active=True)
    if policies.exists():
        return {p.metric_code: p for p in policies}

    # 기본값 (fallback)
    return {
        "co":  {"warning_min": 25,   "danger_min": 200  },
        "h2s": {"warning_min": 10,   "danger_min": 15   },
        "co2": {"warning_min": 1000, "danger_min": 5000 },
        "no2": {"warning_min": 3,    "danger_min": 5    },
        "so2": {"warning_min": 2,    "danger_min": 5    },
        "o3":  {"warning_min": 0.06, "danger_min": 0.12 },
        "nh3": {"warning_min": 25,   "danger_min": 35   },
        "voc": {"warning_min": 0.5,  "danger_min": 1.0  },
    }


def calc_danger_level(reading) -> str:
    """
    GasReading 인스턴스를 받아 위험도 반환
    반환값: '위험' / '주의' / '정상'
    """
    # O2는 낮을수록 위험 (반대 방향)
    if reading.o2 is not None:
        if reading.o2 < 16:   return "위험"
        elif reading.o2 < 18: return "주의"

    thresholds = get_thresholds()

    for gas, t in thresholds.items():
        value = getattr(reading, gas, None)
        if value is None:
            continue

        danger_min  = t.danger_min  if hasattr(t, 'danger_min')  else t["danger_min"]
        warning_min = t.warning_min if hasattr(t, 'warning_min') else t["warning_min"]

        if value >= danger_min:  return "위험"
        elif value >= warning_min: return "주의"

    return "정상"


def check_threshold_exceeded(reading) -> list:
    """
    임계치 초과 가스 목록 반환
    alerts 앱에서 AlarmEvent 생성 시 사용

    반환 예시:
    [
        {"gas": "co", "value": 250, "level": "위험"},
        {"gas": "h2s", "value": 12, "level": "주의"},
    ]
    """
    exceeded = []
    thresholds = get_thresholds()

    # O2 체크
    if reading.o2 is not None:
        if reading.o2 < 16:
            exceeded.append({"gas": "o2", "value": reading.o2, "level": "위험"})
        elif reading.o2 < 18:
            exceeded.append({"gas": "o2", "value": reading.o2, "level": "주의"})

    for gas, t in thresholds.items():
        value = getattr(reading, gas, None)
        if value is None:
            continue

        danger_min  = t.danger_min  if hasattr(t, 'danger_min')  else t["danger_min"]
        warning_min = t.warning_min if hasattr(t, 'warning_min') else t["warning_min"]

        if value >= danger_min:
            exceeded.append({"gas": gas, "value": value, "level": "위험"})
        elif value >= warning_min:
            exceeded.append({"gas": gas, "value": value, "level": "주의"})

    return exceeded