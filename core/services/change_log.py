"""
T1-δ: ChangeLog 작성 유틸리티.
사용처: facilities/views.py 의 ViewSet.perform_update / perform_destroy

설계 결정 (T1-δ 권장안):
- C1: before/after 둘 다 full snapshot (참조 무결성 추적용)
- E3: transaction.on_commit 으로 DB commit 후만 기록
- D1: actor = request.user.pk
"""
from django.db import transaction
from django.forms.models import model_to_dict
from core.models import ChangeLog


def capture_state(instance):
    """
    객체의 모든 필드를 dict 로 직렬화 (FK 는 ID 만).
    C1 정책 — 변경 시점의 전체 상태 보존.
    """
    if instance is None or instance.pk is None:
        return None
    data = model_to_dict(instance)
    for k, v in list(data.items()):
        if hasattr(v, 'pk'):
            data[k] = v.pk
    return data


def log_change(instance, before, after, action, user):
    """
    ChangeLog row 작성. transaction.on_commit 으로 DB 성공 시만 기록 (E3).
    """
    target_type = type(instance).__name__
    target_id = instance.pk
    actor_id = getattr(user, 'pk', None) if user and getattr(user, 'is_authenticated', False) else None

    def _write():
        ChangeLog.objects.create(
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
            action_type=action,
            before_data=before,
            after_data=after,
        )

    transaction.on_commit(_write)
