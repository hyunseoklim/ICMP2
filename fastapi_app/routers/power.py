"""
전력 영역 HTTP 엔드포인트 (Phase 5에서 작성).

본 파일은 위치 예약용 자리표시자.

Phase 5에서 작성 예시:
    from fastapi import APIRouter
    from fastapi_app.ai_engine.power.modules.isolation_forest import PowerIsolationForestDetector
    from fastapi_app.ai_engine.power.modules.arima import PowerARIMAPredictor
    
    router = APIRouter(prefix="/api/power", tags=["power"])
    
    @router.post("/predict")
    def predict_power(payload: dict):
        ...
"""
