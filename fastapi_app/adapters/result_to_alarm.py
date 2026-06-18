"""
AI 엔진 결과 ↔ Django 알람 모델 변환층 (Phase 5에서 작성).

본 파일은 위치 예약용 자리표시자.

Phase 5에서 작성 예시:
    # from alerts.models import AlarmEvent
    
    def threshold_result_to_alarm_event(result) -> dict:
        '''Threshold 모듈 결과를 Django AlarmEvent 생성용 dict로 변환.'''
        ...
    
    def arima_result_to_alarm_event(result) -> dict:
        '''ARIMA 예측 결과(사전 경고)를 AlarmEvent로 변환.'''
        ...
    
    def isolation_forest_result_to_alarm_event(result) -> dict:
        '''IF 모듈 결과(ANOMALY)를 AlarmEvent로 변환.'''
        ...
"""
