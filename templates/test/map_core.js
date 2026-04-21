/**
 * map_core.js
 * 지도 초기화 및 배경 이미지 처리
 *
 * 역할: Leaflet 지도 인스턴스 생성, 배경 도면 이미지 오버레이 적용,
 *       레이어 그룹(그릇) 생성, 줌/뷰 조작
 *       → 이미지를 화면에 올리는 것만 담당하며 데이터를 채우지 않음
 *
 * 의존성: map_config.js (map, imageOverlay, gridLayer, zoneLayer,
 *                        imgWidth, imgHeight, SAMPLE_IMAGE)
 * 로드 순서: map_config.js 다음
 *
 * 함수 목록:
 *   initMap()     — 지도·이미지·레이어 그룹 초기화 (시스템 시작 시 1회)
 *   fitMapView()  — 전체 도면이 보이도록 뷰 초기화
 *   zoomIn()      — 줌 +1
 *   zoomOut()     — 줌 -1
 */

// ─── 지도 초기화 ──────────────────────────────────────────────

/**
 * initMap
 * 입력: 없음
 * 참조: imgHeight, imgWidth, SAMPLE_IMAGE (map_config.js)
 * 출력: map, imageOverlay, gridLayer, zoneLayer 전역 변수 할당
 *
 * 주의: 레이어 그룹(gridLayer, zoneLayer)은 이 함수에서 그릇만 생성함
 *       실제 데이터 주입은 각 담당 파일(map_grid.js, map_zone.js)이 수행
 *       마우스 이벤트 등록은 map_zone.js의 initZoneEvents()에서 별도 수행
 */
function initMap() {
  map = L.map('map', {
    crs:        L.CRS.Simple,
    minZoom:    -3,
    maxZoom:    3,
    zoomControl: false,
  });

  const bounds = [[0, 0], [imgHeight, imgWidth]];

  imageOverlay = L.imageOverlay(SAMPLE_IMAGE, bounds, { opacity: 0.85 }).addTo(map);
  map.fitBounds(bounds);

  // 레이어 그룹 생성 — 순서가 Z-index이므로 변경 금지
  // 1. gridLayer  : 격자 (정적, interactive: false 적용은 map_grid.js에서)
  // 2. zoneLayer  : 구역 (동적, 실시간 갱신 대상)
  gridLayer = L.layerGroup().addTo(map);
  zoneLayer = L.layerGroup().addTo(map);
}

// ─── 지도 조작 ────────────────────────────────────────────────

/**
 * fitMapView
 * 입력: 없음
 * 참조: imgHeight, imgWidth (map_config.js)
 * 출력: 현재 도면 전체가 보이도록 지도 뷰 조정
 */
function fitMapView() {
  const bounds = [[0, 0], [imgHeight, imgWidth]];
  map.fitBounds(bounds);
}

/**
 * zoomIn
 * 입력: 없음
 * 참조: map (map_config.js)
 * 출력: 줌 레벨 +1
 */
function zoomIn() {
  map.zoomIn();
}

/**
 * zoomOut
 * 입력: 없음
 * 참조: map (map_config.js)
 * 출력: 줌 레벨 -1
 */
function zoomOut() {
  map.zoomOut();
}