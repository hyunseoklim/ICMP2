"""domain — AI 엔진 서비스의 도메인 분기 (2a: 한 코드베이스, 컨테이너별 1도메인).

`AI_DOMAIN` 환경변수(gas|power)로 컨테이너가 담당할 도메인을 정한다. 한 컨테이너는
자기 도메인의 stream·group·core만 다루므로 가스/전력이 런타임에 누수되지 않는다
(수직 분리). 잘못된 값이면 기동 단계에서 즉시 실패한다.
"""
import os

VALID = ("gas", "power")

DOMAIN = os.environ.get("AI_DOMAIN", "").strip().lower()
if DOMAIN not in VALID:
    raise RuntimeError(
        f"AI_DOMAIN 환경변수는 {VALID} 중 하나여야 합니다 (현재: {DOMAIN!r})"
    )

# 계약(ai-engine-contract.md §1)
RAW_STREAM = f"stream:{DOMAIN}:raw"
AI_GROUP = f"{DOMAIN}_ai"
RESULT_STREAM = f"stream:{DOMAIN}:result"
