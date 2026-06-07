"""ai_engine/service — AI 엔진 서비스 래퍼 (배포 단위: 별도 컨테이너).

이 패키지는 ai_engine 라이브러리(gas·power)를 Redis Stream 소비/발행으로 감싸는
오케스트레이션 계층이다. 라이브러리(분석)와 분리해, 서비스 배선만 담당한다.

- ai_main.py : FastAPI 진입점 + lifespan(소비 루프 기동)
- consumer.py: stream:*:raw 소비 → 분석 → stream:*:result 발행   (F1-2 예정)
- adapters.py: raw dict → SensorBundle, 분석결과 → result payload
"""
