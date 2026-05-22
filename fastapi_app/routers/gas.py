"""
가스 영역 HTTP 엔드포인트 (Phase 5에서 작성).

본 파일은 위치 예약용 자리표시자.

Phase 5에서 작성 예시:
    from fastapi import APIRouter
    from fastapi_app.ai_engine.gas.modules.isolation_forest import GasIsolationForestDetector
    from fastapi_app.ai_engine.gas.modules.arima import GasARIMAPredictor
    from fastapi_app.adapters.orm_to_data_point import bundle_dict_to_sensor_bundle
    
    router = APIRouter(prefix="/api/gas", tags=["gas"])
    
    @router.post("/predict")
    def predict_gas(payload: dict):
        bundle = bundle_dict_to_sensor_bundle(payload)
        if_result = gas_if_detector.predict(bundle)
        arima_result = gas_arima_predictor.predict(...)
        return {
            "if": if_result.to_dict(),
            "arima": arima_result.to_dict(),
        }
"""
