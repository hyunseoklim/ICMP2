"""ai_main — AI 엔진 서비스 진입점 (별도 컨테이너 `ai-engine`).

수집기 main.py의 lifespan+background-task 패턴을 재사용한다. 단 수집기와 달리
HTTP/WS를 제공하지 않고, lifespan에서 Redis Stream 소비 루프를 띄우는 것이 본 역할.

범위(F1-1): "켜지고 health 응답하는 빈 소비 서비스"까지.
  - 소비 루프(consumer.run)·분석(PredictionSubsystem)·결과 발행은 F1-2~F1-4에서 채운다.
  - /predict 라우터는 미배선(결정 C5).

배포(B안): `pip install .`(pyproject)로 gas/power가 top-level 설치되므로 sys.path 조작 불필요.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import analyzer, domain
from .consumer import run as consume_run

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[ai-engine:%s] 기동 — 모델 로드", domain.DOMAIN)
    analyzer.bootstrap()
    task = asyncio.create_task(consume_run(analyzer.handle))
    yield
    task.cancel()
    logger.info("[ai-engine:%s] 종료 — 소비 루프 취소", domain.DOMAIN)


app = FastAPI(title=f"ICMP2 AI 엔진 ({domain.DOMAIN})", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": f"ai-engine-{domain.DOMAIN}"}
