/**
 * map_core.js
 * 지도 초기화 및 배경 이미지 처리
 *
 * 역할: Leaflet 지도 인스턴스 생성, MapManager를 통한 레이어 골조 생성,
 *       배경 도면 이미지 오버레이 적용, 줌·뷰 조작
 *       → 이미지를 화면에 올리는 것만 담당하며 데이터를 채우지 않음
 *
 * 의존성: map_config.js (map, imageOverlay, floorWidthMeters,
 *                        floorLengthMeters, MapManager)
 * 로드 순서: map_config.js 다음
 *
 * 함수 목록:
 *   initMap()    — 지도·레이어 골조 초기화 (시스템 시작 시 1회)
 *   fitMapView() — 전체 도면이 보이도록 뷰 초기화
 *   zoomIn()     — 줌 +1
 *   zoomOut()    — 줌 -1
 */

// ─── 지도 초기화 ──────────────────────────────────────────────

/**
 * initMap
 * 입력: 없음
 * 출력: map 생성, MapManager를 통해 모든 레이어 Pane·LayerGroup 확보
 *
 * 주의:
 *   - 배경 도면(imageOverlay)은 층 선택 전까지 빈 상태로 둔다.
 *     실제 도면 URL과 bounds는 loadFloorData()에서 설정한다.
 *   - 마우스 이벤트 등록은 map_init.js의 initZoneEvents()에서 수행한다.
 *   - 격자·구역 데이터 주입은 loadFloorData() 호출 시 각 담당 파일이 수행한다.
 */
function initMap() {
    map = L.map('map', {
        crs:         L.CRS.Simple,
        minZoom:     -3,
        maxZoom:     3,
        zoomControl: false,
    });

    // MAP_LAYERS 등록부를 순회하여 Pane과 LayerGroup을 일괄 생성
    MapManager.syncLayers(map);

    // 도면 데이터가 없는 초기 상태에서도 지도를 표시할 수 있도록
    // imageOverlay를 빈 bounds로 미리 생성해 둔다.
    // 실제 URL과 크기는 loadFloorData()에서 setBounds/setUrl로 교체한다.
    const initialBounds = [[0, 0], [1, 1]];
    imageOverlay = L.imageOverlay('', initialBounds, { opacity: 0.85 }).addTo(map);
}

// ─── 지도 조작 ────────────────────────────────────────────────
// HTML에서 onclick="fitMapView()" / onclick="zoomIn()" 형태로 직접 호출됨

/**
 * fitMapView
 * 현재 도면 전체가 보이도록 지도 뷰 조정
 * loadFloorData() 이후 floorWidthMeters·floorLengthMeters가 갱신된 뒤 호출 가능
 */
function fitMapView() {
    if (!floorWidthMeters || !floorLengthMeters) return;
    const bounds = [[0, 0], [floorLengthMeters, floorWidthMeters]];
    map.fitBounds(bounds, { padding: [0, 0] });
}

function zoomIn()  { map.zoomIn();  }
function zoomOut() { map.zoomOut(); }