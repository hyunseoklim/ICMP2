/**
 * map_config.js
 * 공유 상수 및 전역 상태
 *
 * 역할: 모든 map_*.js 파일이 참조하는 상수와 전역 변수를 단일 위치에서 관리
 * 의존성: 없음 (다른 map_*.js 파일에 의존하지 않음)
 * 로드 순서: 반드시 첫 번째로 로드
 */

// ─── Leaflet 인스턴스 ─────────────────────────────────────────
// initMap() 호출 후 할당됨 (map_core.js)

let map          = null;   // L.Map 인스턴스
let imageOverlay = null;   // L.ImageOverlay — 배경 도면 이미지

// ─── 도면 크기 ────────────────────────────────────────────────
// loadFloorData() 호출 시 API 응답값으로 덮어씀 (map_events.js)

let floorWidthMeters  = 0;   // m — floor.width  (API 수신 후 갱신)
let floorLengthMeters = 0;   // m — floor.length (API 수신 후 갱신)

// ─── 격자 설정 ────────────────────────────────────────────────
// loadFloorData() 호출 시 갱신됨 (map_events.js)

let cellWidth  = 1.0;   // m — 격자 셀 가로 크기 (1m 고정 운용)
let cellHeight = 1.0;   // m — 격자 셀 세로 크기 (1m 고정 운용)

// ─── 층/도면 상태 ─────────────────────────────────────────────

let currentFloorId = null;   // 현재 활성 층 ID (API 키)

// ─── 레이어 등록부 ───────────────────────────────────────────
// Django INSTALLED_APPS 방식으로 관리
// zIndex 오름차순 = 화면 아래에서 위 순서
//
// interactive: false → pointerEvents: none (클릭 이벤트 통과)

const MAP_LAYERS = [
    { name: 'grid',     pane: 'gridPane',     zIndex: 200, interactive: false },
    { name: 'zone',     pane: 'zonePane',     zIndex: 300, interactive: true  },
    { name: 'geofence', pane: 'geofencePane', zIndex: 350, interactive: true  },
    { name: 'gas',      pane: 'gasPane',      zIndex: 400, interactive: true  },
    { name: 'power',    pane: 'powerPane',    zIndex: 410, interactive: true  },
    { name: 'location', pane: 'locationPane', zIndex: 420, interactive: true  },
    { name: 'device',   pane: 'devicePane',   zIndex: 430, interactive: true  },
    { name: 'worker',   pane: 'workerPane',   zIndex: 500, interactive: true  },
];

// ─── MapManager ───────────────────────────────────────────────
// 레이어 생성·동기화·조회를 담당하는 중앙 관리자

const MapManager = {
    layers: {},   // name → L.LayerGroup 객체 장부

    /**
     * syncLayers
     * MAP_LAYERS 등록부를 순회하여 Pane과 LayerGroup을 생성·등록한다.
     * 멱등성: 이미 존재하는 Pane/레이어는 재생성하지 않고 데이터만 비운다.
     */
    syncLayers: function (map) {
        MAP_LAYERS.forEach(layer => {
            // 1. Pane 생성 (중복 방지)
            if (!map.getPane(layer.pane)) {
                const pane = map.createPane(layer.pane);
                pane.style.zIndex = layer.zIndex;
                if (!layer.interactive) {
                    pane.style.pointerEvents = 'none';
                }
            }

            // 2. LayerGroup 생성 및 장부 등록
            if (this.layers[layer.name]) {
                this.layers[layer.name].clearLayers();   // 기존 데이터만 삭제
            } else {
                this.layers[layer.name] = L.layerGroup([], { pane: layer.pane }).addTo(map);
            }
        });
    },

    /**
     * getLayer
     * 등록된 레이어를 이름으로 조회한다.
     * 미등록 이름 요청 시 경고 후 null 반환.
     */
    getLayer: function (name) {
        if (!this.layers[name]) {
            console.warn(`⚠️ [MapManager] '${name}' 레이어가 등록되지 않았습니다.`);
            return null;
        }
        return this.layers[name];
    },
};

// ─── Zone 드로우 상태 ─────────────────────────────────────────
// map_zone.js의 ZoneState 객체로 관리됨
// 아래 변수는 하위 호환을 위해 유지하되 신규 코드에서는 ZoneState를 사용할 것

let zoneDrawMode      = false;   // 드로우 모드 활성 여부
let zoneDragStart     = null;    // L.LatLng — 드래그 시작 좌표
let zoneDragEnd       = null;    // L.LatLng — 드래그 종료 좌표
let zoneHighlightRect = null;    // L.Rectangle — 드래그 중 임시 사각형

// ─── 격자 스타일 상수 ─────────────────────────────────────────

const GRID_COLOR  = 'rgba(255, 0, 0, 0.4)';   // 격자선 색상
const GRID_WEIGHT = 0.5;                        // 격자선 두께(px)

// ─── Zone 색상 맵 ─────────────────────────────────────────────
// zone_type 값을 키로 사용 / renderZone()에서 참조됨

const ZONE_COLORS = {
    work:    '#378ADD',
    storage: '#639922',
    rest:    '#1D9E75',
    utility: '#BA7517',
    passage: '#888780',
    etc:     '#534AB7',
};