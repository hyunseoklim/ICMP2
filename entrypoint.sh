#!/bin/sh

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# 멀티프로세스 메트릭: 역할별 subdir로 분리한다.
# Docker는 모든 컨테이너 메인 프로세스를 PID 1로 띄우므로, 여러 컨테이너가 같은
# PROMETHEUS_MULTIPROC_DIR를 공유하면 counter_1.db/histogram_1.db가 충돌·손상된다
# (prometheus_client 파일명 = {type}_{getpid}.db). 따라서 컨테이너(역할)별 subdir를
# 쓰고, 각 컨테이너는 자기 subdir만 wipe한다(다른 subdir 삭제 금지 → 경합 없음).
# django metrics_view가 부모의 */*.db를 모아 단일 MultiProcessCollector.merge로 집계.
if [ -n "$PROMETHEUS_MULTIPROC_DIR" ]; then
  case "$*" in
    *consume_gas_stream*)   SUB=gas-consumer ;;
    *consume_power_stream*) SUB=power-consumer ;;
    *"-Q forecast"*)        SUB=celery-forecast ;;
    *"-Q events"*)          SUB=celery-events ;;
    *beat*)                 SUB=celery-beat ;;
    *worker*)               SUB=celery ;;
    *)                      SUB=django ;;   # 인자 없음 = daphne
  esac
  export PROMETHEUS_MULTIPROC_DIR="$PROMETHEUS_MULTIPROC_DIR/$SUB"
  mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
  rm -f "$PROMETHEUS_MULTIPROC_DIR"/*.db 2>/dev/null || true
fi

if [ $# -gt 0 ]; then
  exec "$@"
else
  exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
fi
