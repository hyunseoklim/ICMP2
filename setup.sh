#!/usr/bin/env bash
# ============================================================
# setup.sh — ICMP2 개발 환경 초기 세팅
#
# 사용법:
#   chmod +x setup.sh
#   ./setup.sh              # migrate + seed (기존 데이터 유지)
#   ./setup.sh --fresh      # DB 초기화 후 처음부터 시작
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── 인자 파싱 ──────────────────────────────────────────────
FRESH=false
for arg in "$@"; do
  case $arg in
    --fresh) FRESH=true ;;
    --help|-h)
      echo "사용법: ./setup.sh [--fresh]"
      echo "  --fresh   db.sqlite3 삭제 후 처음부터 세팅"
      exit 0 ;;
  esac
done

# ── 가상환경 활성화 ────────────────────────────────────────
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  info "가상환경 활성화: .venv"
elif [ -d "venv" ]; then
  source venv/bin/activate
  info "가상환경 활성화: venv"
else
  warn "가상환경을 찾을 수 없습니다. 시스템 Python을 사용합니다."
fi

# ── Python / Django 확인 ───────────────────────────────────
command -v python >/dev/null 2>&1 || error "python을 찾을 수 없습니다."
python -c "import django" 2>/dev/null || error "Django가 설치되어 있지 않습니다. (pip install -r requirements.txt)"

# ── --fresh: DB 초기화 ─────────────────────────────────────
if [ "$FRESH" = true ]; then
  warn "--fresh 옵션: db.sqlite3를 삭제하고 처음부터 세팅합니다."
  read -r -p "계속하시겠습니까? [y/N] " confirm
  if [[ "$confirm" =~ ^[Yy]$ ]]; then
    rm -f db.sqlite3
    success "db.sqlite3 삭제 완료"
  else
    info "취소했습니다."
    exit 0
  fi
fi

# ── migrate ────────────────────────────────────────────────
info "마이그레이션 실행 중..."
python manage.py migrate --run-syncdb
success "마이그레이션 완료"

# ── seed (마이그레이션 후 모든 시드 처리는 seed.py 단일 진입점) ──
# fixture 로드 포함 모든 초기 데이터는 core/management/commands/seed.py가 처리
info "시드 데이터 입력 중..."
python manage.py seed
success "시드 완료"

# ── 완료 ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}=============================="
echo -e " 세팅 완료!"
echo -e "==============================${NC}"
echo ""
echo "  관리자 계정 : admin / admin1234!"
echo "  현장관리자  : manager1 / manager1234!"
echo "  작업자      : worker1 / worker1234!"
echo ""
echo "  Django 서버 시작: python manage.py runserver"
echo ""