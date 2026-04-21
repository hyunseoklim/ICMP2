/**
 * map_config.js
 * 공유 상수 및 전역 상태
 *
 * 역할: 모든 map_*.js 파일이 참조하는 상수와 전역 변수를 단일 위치에서 관리
 * 의존성: 없음 (다른 map_*.js 파일에 의존하지 않음)
 * 로드 순서: 반드시 첫 번째로 로드
 *
 * 외부에서 사용하는 항목:
 *   - Leaflet 인스턴스: map, imageOverlay, gridLayer, zoneLayer
 *   - 도면 크기: imgWidth, imgHeight
 *   - 격자 설정: cellWidth, cellHeight
 *   - 상태: currentFloorId, zoneDrawMode
 *   - 드래그 상태: zoneDragStart, zoneDragEnd, zoneHighlightRect
 *   - 스타일 상수: GRID_COLOR, GRID_WEIGHT
 *   - Zone 색상 맵: ZONE_COLORS
 */

// ─── Leaflet 인스턴스 ─────────────────────────────────────────
// initMap() 호출 후 할당됨 (map_core.js)

let map          = null;   // L.Map 인스턴스
let imageOverlay = null;   // L.ImageOverlay — 배경 도면 이미지
let gridLayer    = null;   // L.LayerGroup  — 격자 레이어
let zoneLayer    = null;   // L.LayerGroup  — 구역 레이어

// ─── 도면 크기 ────────────────────────────────────────────────
// loadFloorData() 호출 시 API 응답값으로 덮어씀 (map_events.js)

let imgWidth  = 1000;   // px — 도면 이미지 가로 크기
let imgHeight = 1000;   // px — 도면 이미지 세로 크기

// ─── 격자 설정 ────────────────────────────────────────────────
// applyGrid() 호출 시 갱신됨 (map_grid.js)

let cellWidth  = 50;   // px — 격자 셀 가로 크기
let cellHeight = 50;   // px — 격자 셀 세로 크기

// ─── 층/도면 상태 ─────────────────────────────────────────────

let currentFloorId = null;   // 현재 활성 층 ID (API 키)

// ─── Zone 드래그 상태 ─────────────────────────────────────────
// onMapMouseDown/Move/Up에서 갱신됨 (map_zone.js)

let zoneDrawMode      = false;   // 드로우 모드 활성 여부
let zoneDragStart     = null;    // L.LatLng — 드래그 시작 좌표
let zoneDragEnd       = null;    // L.LatLng — 드래그 종료 좌표
let zoneHighlightRect = null;    // L.Rectangle — 드래그 중 임시 사각형

// ─── 격자 스타일 상수 ─────────────────────────────────────────

const GRID_COLOR  = 'rgb(255, 0, 0)';   // 격자선 색상
const GRID_WEIGHT = 0.5;                // 격자선 두께(px)

// ─── Zone 색상 맵 ─────────────────────────────────────────────
// zone_type 값을 키로 사용
// renderZone()에서 참조됨 (map_zone.js)

const ZONE_COLORS = {
  work:    '#378ADD',
  storage: '#639922',
  rest:    '#1D9E75',
  utility: '#BA7517',
  passage: '#888780',
  etc:     '#534AB7',
};