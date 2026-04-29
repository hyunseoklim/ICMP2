/** 담당 업무: 1m 단위의 SVG 격자 생성 및 렌더링 **/

 function loadGridLayer() {
    const gridLayer = MapManager.getLayer('grid');
    if (gridLayer) {
        // 멱등성 확보: 기존에 그려진 격자가 있다면 깨끗이 지움
        gridLayer.clearLayers(); 
        
        // 3. 실제 그리기 함수 호출 (그릇을 인자로 전달)
        setupSVGGrid(gridLayer, floorWidthMeters, floorLengthMeters);
    } else {
        console.error("🚫 [GridLayer] 'grid' 레이어를 찾을 수 없습니다. 설정을 확인하세요.");
    }
}
function setupSVGGrid(gridLayer, widthMeters, heightMeters) {
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("xmlns", svgNS);
    svg.setAttribute("viewBox", `0 0 ${widthMeters} ${heightMeters}`);

    // 패턴 정의: 1m 단위로 옅은 격자선을 그림
    svg.innerHTML = `
      <defs>
        <pattern id="gridPattern" width="1" height="1" patternUnits="userSpaceOnUse">
          <rect width="1" height="1" fill="none" 
                stroke="${GRID_COLOR}" 
                stroke-width="${GRID_WEIGHT}"/>
        </pattern>
      </defs>
      <rect width="${widthMeters}" height="${heightMeters}" fill="url(#gridPattern)" />
    `;

    const bounds = [[0, 0], [heightMeters, widthMeters]];
    
    // Leaflet의 svgOverlay를 생성하여 gridLayer(gridLayer)에 추가
    L.svgOverlay(svg, bounds, {
        interactive: false, // 클릭 이벤트가 아래 레이어로 전달되게 함
        opacity: 1,
        pane: 'gridPane'
    }).addTo(gridLayer);
}