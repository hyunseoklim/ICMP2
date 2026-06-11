"""monitoring 앱 임계치 판단 로직 테스트.

ingest 파이프라인의 핵심 판단 함수에 대한 회귀 안전망:
    1. check_threshold_exceeded — 가스별 주의/위험 경계값 + O2 역방향 처리
    2. get_thresholds — ThresholdPolicy(DB) 우선, 없으면 DEFAULT_THRESHOLDS 폴백

실행 (DB_HOST=db 이므로 컨테이너 내부에서):
    docker compose exec django python manage.py test monitoring
"""
from django.test import TestCase
from django.utils import timezone

from .models import GasReading, ThresholdPolicy
from .services import DEFAULT_THRESHOLDS, check_threshold_exceeded, get_thresholds


def _reading(**values):
    """DB 저장 없이 가스 필드만 채운 GasReading 인스턴스 (판단 함수 입력용)."""
    return GasReading(measured_at=timezone.now(), **values)


def _exceeded_map(result: list) -> dict:
    """[{gas, value, level}, ...] → {gas: level} 변환 (단언 편의용)."""
    return {e['gas']: e['level'] for e in result}


class CheckThresholdExceededTests(TestCase):
    """ThresholdPolicy 미등록 → DEFAULT_THRESHOLDS 폴백 기준.

    DEFAULT_THRESHOLDS (주의, 위험): co=(25, 200), h2s=(10, 15),
    co2=(1000, 5000), no2=(3, 5), so2=(2, 5), o3=(0.06, 0.12),
    nh3=(25, 35), voc=(0.5, 1.0)
    O2 별도: <16 위험, <18 주의, >23.5 주의(상한)
    """

    def test_normal_values_return_empty(self):
        result = check_threshold_exceeded(_reading(co=5.0, h2s=1.0, o2=21.0))
        self.assertEqual(result, [])

    def test_all_none_returns_empty(self):
        result = check_threshold_exceeded(_reading())
        self.assertEqual(result, [])

    def test_warning_boundary_is_inclusive(self):
        """주의 임계값과 같은 값(co=25)도 주의로 판정 (>= 비교)."""
        result = check_threshold_exceeded(_reading(co=25.0))
        self.assertEqual(_exceeded_map(result), {'co': '주의'})

    def test_danger_boundary_is_inclusive(self):
        result = check_threshold_exceeded(_reading(co=200.0))
        self.assertEqual(_exceeded_map(result), {'co': '위험'})

    def test_just_below_warning_is_normal(self):
        result = check_threshold_exceeded(_reading(co=24.9))
        self.assertEqual(result, [])

    def test_multiple_gases_reported_together(self):
        result = check_threshold_exceeded(_reading(co=250.0, h2s=12.0, voc=0.3))
        self.assertEqual(_exceeded_map(result), {'co': '위험', 'h2s': '주의'})

    # ── O2 역방향 (낮을수록 위험) + 상한 ──────────────────

    def test_o2_low_is_danger(self):
        result = check_threshold_exceeded(_reading(o2=15.0))
        self.assertEqual(_exceeded_map(result), {'o2': '위험'})

    def test_o2_between_16_and_18_is_warning(self):
        result = check_threshold_exceeded(_reading(o2=17.0))
        self.assertEqual(_exceeded_map(result), {'o2': '주의'})

    def test_o2_above_23_5_is_warning(self):
        """산소 과잉(23.5% 초과)도 주의 — 화재 위험 상한."""
        result = check_threshold_exceeded(_reading(o2=24.0))
        self.assertEqual(_exceeded_map(result), {'o2': '주의'})

    def test_o2_normal_range_is_empty(self):
        result = check_threshold_exceeded(_reading(o2=21.0))
        self.assertEqual(result, [])


class GetThresholdsTests(TestCase):

    def test_empty_db_falls_back_to_defaults(self):
        self.assertEqual(get_thresholds(scope='알림'), DEFAULT_THRESHOLDS)

    def test_db_policy_overrides_defaults(self):
        ThresholdPolicy.objects.create(
            metric_code='co', scope='알림', warning_max=10, danger_max=20,
        )

        thresholds = get_thresholds(scope='알림')

        self.assertEqual(thresholds, {'co': (10, 20)})
        # 주의: DB에 정책이 1건이라도 있으면 DEFAULT와 병합되지 않음
        # (DB에 없는 가스는 임계치 판단에서 제외됨)
        self.assertNotIn('h2s', thresholds)

    def test_scope_mismatch_falls_back_to_defaults(self):
        """다른 scope 전용 정책만 있으면 해당 scope 조회는 기본값 폴백."""
        ThresholdPolicy.objects.create(
            metric_code='co', scope='실시간 관제', warning_max=10, danger_max=20,
        )

        self.assertEqual(get_thresholds(scope='알림'), DEFAULT_THRESHOLDS)

    def test_empty_scope_policy_applies_to_all(self):
        """scope='' 정책은 범위 미지정 → 모든 scope에 적용."""
        ThresholdPolicy.objects.create(
            metric_code='co', scope='', warning_max=10, danger_max=20,
        )

        self.assertEqual(get_thresholds(scope='알림'), {'co': (10, 20)})
        self.assertEqual(get_thresholds(scope='실시간 관제'), {'co': (10, 20)})

    def test_o2_policy_is_excluded(self):
        """O2는 역방향 처리라 get_thresholds 반환값에서 제외."""
        ThresholdPolicy.objects.create(
            metric_code='o2', scope='', warning_max=18, danger_max=16,
        )
        ThresholdPolicy.objects.create(
            metric_code='co', scope='', warning_max=10, danger_max=20,
        )

        self.assertEqual(get_thresholds(scope='알림'), {'co': (10, 20)})

    def test_inactive_policy_is_ignored(self):
        ThresholdPolicy.objects.create(
            metric_code='co', scope='', warning_max=10, danger_max=20,
            is_active=False,
        )

        self.assertEqual(get_thresholds(scope='알림'), DEFAULT_THRESHOLDS)

    def test_db_policy_changes_event_severity(self):
        """DB 정책 ↔ 판단 함수 통합: 운영자가 임계치를 낮추면
        같은 측정값이 주의 → 위험으로 격상되는지."""
        reading = _reading(co=30.0)
        # 기본값 기준: co=30 → 주의(25 이상, 200 미만)
        self.assertEqual(_exceeded_map(check_threshold_exceeded(reading, scope='알림')),
                         {'co': '주의'})

        ThresholdPolicy.objects.create(
            metric_code='co', scope='알림', warning_max=10, danger_max=25,
        )
        # 강화된 정책 기준: co=30 → 위험(25 이상)
        self.assertEqual(_exceeded_map(check_threshold_exceeded(reading, scope='알림')),
                         {'co': '위험'})
