/**
 * map_init.js
 * 진입점 — 초기화 순서 제어
 *
 * 역할: DOMContentLoaded 시점에 각 모듈의 init 함수를 순서대로 호출
 *       각 파일의 역할 분리 이후 이 파일만이 초기화 흐름을 알고 있음
 *
 * HTML 로드 순서 (script 태그 순서와 일치해야 함):
 *   1. map_config.js  — 공유 상수 및 전역 상태
 *   2. map_core.js    — 지도 초기화 및 이미지 처리
 *   3. map_grid.js    — 격자 렌더링
 *   4. map_zone.js    — Zone 드래그 및 렌더링
 *   5. map_events.js  — 레이어 제어, 층 로드, UI 패널
 *   6. map_init.js    — 진입점 (현재 파일, 마지막 로드)
 *
 * HTML script 태그 예시:
 *   <script src="map_config.js"></script>
 *   <script src="map_core.js"></script>
 *   <script src="map_grid.js"></script>
 *   <script src="map_zone.js"></script>
 *   <script src="map_events.js"></script>
 *   <script src="map_init.js"></script>
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. 지도 인스턴스 및 레이어 그룹(그릇) 생성
  //    → map, imageOverlay, gridLayer, zoneLayer 할당
  initMap();

  // 2. 격자 초기 렌더링
  //    → gridLayer에 현재 cellWidth/cellHeight 기준 격자선 추가
  initGrid();

  // 3. Zone 드로우 마우스 이벤트 등록
  //    → map에 mousedown/mousemove/mouseup 핸들러 연결
  initZoneEvents();
});