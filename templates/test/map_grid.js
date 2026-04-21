/**
 * map_grid.js
 * 격자(Grid) 렌더링 및 설정 저장
 *
 * 역할: gridLayer 위에 격자선을 그리고, 격자 설정을 API에 저장/갱신
 *       → 격자는 정적 데이터이므로 설정 변경 시에만 재렌더링
 *
 * 의존성: map_config.js (gridLayer, cellWidth, cellHeight,
 *                        imgWidth, imgHeight, currentFloorId,
 *                        GRID_COLOR, GRID_WEIGHT, API_BASE)
 * 로드 순서: map_config.js, map_core.js 다음
 *
 * 함수 목록:
 *   initGrid()              — 최초 격자 렌더링 (map_core.js의 initMap 완료 후 호출)
 *   drawGrid(w, h, iw, ih)  — 격자 계산 및 렌더링
 *   applyGrid()             — UI 입력값으로 격자 재렌더링 + API 저장
 */

// ─── 격자 초기화 ──────────────────────────────────────────────

/**
 * initGrid
 * 입력: 없음
 * 참조: cellWidth, cellHeight, imgWidth, imgHeight (map_config.js)
 * 출력: gridLayer에 초기 격자 렌더링
 *
 * 호출 시점: initMap() 완료 직후 DOMContentLoaded에서 호출
 */
function initGrid() {
  drawGrid(cellWidth, cellHeight, imgWidth, imgHeight);
}

// ─── 격자 렌더링 ──────────────────────────────────────────────

/**
 * drawGrid
 * 입력:
 *   _cellWidth   {number} — 셀 가로 크기 (px)
 *   _cellHeight  {number} — 셀 세로 크기 (px)
 *   _imageWidth  {number} — 이미지 가로 크기 (px)
 *   _imageHeight {number} — 이미지 세로 크기 (px)
 * 참조: gridLayer, GRID_COLOR, GRID_WEIGHT (map_config.js)
 * 출력: gridLayer를 초기화 후 수직선(cols+1개) + 수평선(rows+1개) 추가
 *
 * 수직선: x = c * _cellWidth,  y: 0 → _imageHeight
 * 수평선: y = r * _cellHeight, x: 0 → _imageWidth
 *
 * [수정 내역]
 *   - cols 계산: _cellHeight → _cellWidth (오류 수정)
 *   - rows 계산: _imageWidth / _imageHight(미정의) → _imageHeight / _cellHeight (오류 수정)
 *   - 수평선 y 계산: _cellWidth → _cellHeight (오류 수정)
 */
function drawGrid(_cellWidth, _cellHeight, _imageWidth, _imageHeight) {
  gridLayer.clearLayers();

  const cols = Math.ceil(_imageWidth  / _cellWidth);
  const rows = Math.ceil(_imageHeight / _cellHeight);

  // 수직선 (세로 방향): x 좌표를 cellWidth 간격으로 이동
  for (let c = 0; c <= cols; c++) {
    const x = c * _cellWidth;
    L.polyline(
      [[0, x], [_imageHeight, x]],
      { color: GRID_COLOR, weight: GRID_WEIGHT, interactive: false }
    ).addTo(gridLayer);
  }

  // 수평선 (가로 방향): y 좌표를 cellHeight 간격으로 이동
  for (let r = 0; r <= rows; r++) {
    const y = r * _cellHeight;
    L.polyline(
      [[y, 0], [y, _imageWidth]],
      { color: GRID_COLOR, weight: GRID_WEIGHT, interactive: false }
    ).addTo(gridLayer);
  }
}

// ─── 격자 설정 적용 및 저장 ───────────────────────────────────

/**
 * applyGrid
 * 입력: DOM — #grid-cell-w (가로 셀 크기), #grid-cell-h (세로 셀 크기)
 * 참조: cellWidth, cellHeight, imgWidth, imgHeight,
 *       currentFloorId, API_BASE (map_config.js)
 * 출력:
 *   - cellWidth, cellHeight 전역 변수 갱신
 *   - drawGrid 재호출로 격자 재렌더링
 *   - currentFloorId가 있으면 API PATCH(기존) 또는 POST(신규)로 설정 저장
 */
function applyGrid() {
  cellWidth  = parseInt(document.getElementById('grid-cell-w').value) || 50;
  cellHeight = parseInt(document.getElementById('grid-cell-h').value) || 50;

  drawGrid(cellWidth, cellHeight, imgWidth, imgHeight);

  if (!currentFloorId) return;

  const cols = Math.ceil(imgWidth  / cellWidth);
  const rows = Math.ceil(imgHeight / cellHeight);
  const url  = `${API_BASE}/floor-grids/`;

  fetch(`${url}?floor_id=${currentFloorId}`)
    .then(r => r.json())
    .then(data => {
      if (data.length > 0) {
        // 기존 격자 설정 갱신
        fetch(`${url}${data[0].id}/`, {
          method:  'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ cell_width: cellWidth, cell_height: cellHeight, cols, rows }),
        });
      } else {
        // 신규 격자 설정 생성
        fetch(url, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({
            floor:       currentFloorId,
            cell_width:  cellWidth,
            cell_height: cellHeight,
            cols,
            rows,
            img_width:   imgWidth,
            img_height:  imgHeight,
          }),
        });
      }
    });
}