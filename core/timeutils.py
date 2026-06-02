"""공용 시각 표시 유틸 — 사람에게 보여줄 때 KST로 변환.

정책: 저장/기계 출력은 aware UTC(ISO), **사람이 보는 것은 KST로 변환 + 라벨**.
DB DateTimeField는 USE_TZ=True라 aware UTC로 반환되므로, 화면/CSV/알림 등
사람이 읽는 출력에서는 반드시 이 헬퍼(또는 timezone.localtime)를 거친다.
"""
from django.utils import timezone


def to_korea_time_str(dt, fmt='%Y-%m-%d %H:%M:%S %Z', default='-'):
    """aware UTC datetime → 한국 시각(KST) 표시 문자열.

    - dt가 None/falsy면 default 반환 (호출부 None 가드 불필요).
    - 기본 fmt는 '%Z'(=KST) 라벨 포함. 날짜만/시:분만 필요하면 fmt 지정.
    """
    if not dt:
        return default
    return timezone.localtime(dt).strftime(fmt)
