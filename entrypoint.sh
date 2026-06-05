#!/bin/sh

python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ $# -gt 0 ]; then
  exec "$@"
else
  # 멀티프로세스 메트릭 dir 정리 — django(인자 없음=스크래퍼)만, 최초 기동 시 1회.
  # celery/consumer는 django(service_started) 이후 기동하므로, 여기서 죽은 PID의
  # stale .db를 제거하면 이후 프로세스들이 fresh 파일로 기록한다(라이브 .db 미삭제).
  if [ -n "$PROMETHEUS_MULTIPROC_DIR" ] && [ -d "$PROMETHEUS_MULTIPROC_DIR" ]; then
    rm -f "$PROMETHEUS_MULTIPROC_DIR"/*.db 2>/dev/null || true
  fi
  exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
fi
