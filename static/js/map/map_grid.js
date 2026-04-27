/**
 * map_grid.js
 * 격자(Grid) 렌더링
 *
 * 역할: gridLayer 위에 격자선을 그림
 *       → 격자는 정적 데이터이므로 층 변경 시에만 재렌더링
 *       → JS는 서버에서 받은 lines를 그대로 렌더링만 수행 (연산 없음)
 *
 * 의존성: map_config.js (gridLayer, GRID_COLOR, GRID_WEIGHT)
 * 로드 순서: map_config.js, map_core.js 다음
 *
 * 함수 목록:
 *   drawGrid(lines)  — 서버에서 받은 lines로 격자 렌더링
 *   applyGrid()      — UI 입력값으로 cell_size 변경 후 재렌더링
 *
 * [수정 내역]
 *   - 좌표계 변경: px → meter
 *   - drawGrid 인자 변경: 4개 px 값 → lines 객체 1개
 *   - initGrid() 제거: loadFloorData()에서 drawGrid() 직접 호출로 대체
 *   - applyGrid(): cell_size(m) 기준으로 변경, floor-grids PATCH 제거
 */

// ─── 격자 렌더링 ──────────────────────────────────────────────

/**
 * drawGrid
 * 입력:
 *   lines {object} — /api/floors/<id>/grid-data/ 응답의 lines 필드
 *     {
 *       vertical:   [{x, y1, y2}, ...]   — 수직선 (meter 단위)
 *       horizontal: [{y, x1, x2}, ...]   — 수평선 (meter 단위)
 *     }
 * 참조: gridLayer, GRID_COLOR, GRID_WEIGHT (map_config.js)
 * 출력: gridLayer를 초기화 후 수직선 + 수평선 추가
 *
 * 좌표계: meter (Leaflet이 화면 px로 자동 변환)
 * Leaflet L.CRS.Simple 좌표: [y, x] 순서
 *
 * JS 연산 없음 — 서버에서 받은 좌표 그대로 사용
 */
function drawGrid(lines) {
  gridLayer.clearLayers();

  // 수직선: x 고정, y1 → y2
  // Leaflet 좌표: [[y1, x], [y2, x]]
  lines.vertical.forEach(l => {
    L.polyline(
      [[l.y1, l.x], [l.y2, l.x]],
      { color: GRID_COLOR, weight: GRID_WEIGHT, interactive: false }
    ).addTo(gridLayer);
  });

  // 수평선: y 고정, x1 → x2
  // Leaflet 좌표: [[y, x1], [y, x2]]
  lines.horizontal.forEach(l => {
    L.polyline(
      [[l.y, l.x1], [l.y, l.x2]],
      { color: GRID_COLOR, weight: GRID_WEIGHT, interactive: false }
    ).addTo(gridLayer);
  });
}

// ─── 격자 설정 적용 ───────────────────────────────────────────

/**
 * applyGrid
 * 입력: DOM — #grid-cell-w (cell_size, meter 단위)
 * 참조: currentFloorId, API_BASE (map_config.js)
 * 출력:
 *   - /api/floor-grids/ PATCH으로 cell_size 저장
 *   - /api/floors/<id>/grid-data/ 재호출로 격자 갱신
 *
 * 주의: #grid-cell-w, #grid-cell-h 모두 cell_size(m) 단위로 입력
 *       (가로/세로 동일한 cell_size 사용)
 */
function applyGrid() {
  const cellSize = parseFloat(document.getElementById('grid-cell-w').value) || 1.0;

  if (!currentFloorId) return;

  // 1. FloorGrid cell_size 업데이트
  fetch(`${API_BASE}/floor-grids/?floor_id=${currentFloorId}`)
    .then(r => r.json())
    .then(data => {
      if (data.length === 0) return;

      const gridId = data[0].id;
      return fetch(`${API_BASE}/floor-grids/${gridId}/`, {
        method:  'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ cell_size: cellSize }),
      });
    })
    .then(() => {
      // 2. 변경된 cell_size 기준으로 격자 재렌더링
      return fetch(`${API_BASE}/floors/${currentFloorId}/grid-data/`);
    })
    .then(r => r.json())
    .then(g => {
      // 전역 변수 갱신
      cellWidth  = g.cell_size;
      cellHeight = g.cell_size;

      // UI 동기화
      document.getElementById('grid-cell-w').value = g.cell_size;
      document.getElementById('grid-cell-h').value = g.cell_size;

      // 격자 재렌더링
      drawGrid(g.lines);
    });
}