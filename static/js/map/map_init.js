/**
 * map_init.js
 * 진입점 — 초기화 순서 제어
 *
 * 역할: DOMContentLoaded 시점에 각 모듈의 초기화 함수를 순서대로 호출한다.
 *       이 파일만이 전체 초기화 흐름을 알고 있다.
 *
 * HTML 로드 순서 (script 태그 순서와 일치해야 함):
 *   1. map_config.js  — 공유 상수, MapManager, MAP_LAYERS
 *   2. map_core.js    — 지도 인스턴스 생성, 레이어 골조(Pane/LayerGroup) 생성
 *   3. map_grid.js    — SVG 격자 렌더링
 *   4. map_zone.js    — Zone 드래그 및 렌더링
 *   5. map_events.js  — 레이어 제어, 층 로드, UI 패널
 *   6. sensor.js      — 센서 마커
 *   7. worker_sim.js  — 작업자 마커
 *   8. geofence.js    — 위험구역 원
 *   9. map_init.js    — 진입점 (현재 파일, 마지막 로드)
 *
 * 초기화 흐름:
 *   initMap()        → Leaflet 지도 생성 + MapManager.syncLayers() 호출
 *                      (모든 레이어의 Pane과 LayerGroup이 이 시점에 확보됨)
 *   initZoneEvents() → 지도 마우스 이벤트 등록
 *                      (initMap 완료 후 map 객체가 존재하는 시점에 호출)
 *
 *   이후 데이터 로드는 층 선택(loadFloorData) 시점에 발생하므로
 *   DOMContentLoaded에서는 데이터를 채우지 않는다.
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. 지도 인스턴스 + 모든 레이어 골조(Pane/LayerGroup) 생성
    initMap();

    // 2. Zone 드로우 마우스 이벤트 등록
    initZoneEvents();
});