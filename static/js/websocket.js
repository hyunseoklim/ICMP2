/**
 * websocket.js — FastAPI WebSocket 클라이언트
 * P1이 보내는 데이터 수신 → 화면 갱신
 */
const SafetyWS = {
    socket: null,
    handlers: {},
    reconnectDelay: 3000,

    connect() {
        const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.socket = new WebSocket(`${wsProtocol}//${location.host}/ws`);

        this.socket.onopen = () => {
            console.log('WebSocket 연결됨');
            document.dispatchEvent(new Event('wsConnected'));
        };

        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                (this.handlers[data.type] || []).forEach(h => h(data));
            } catch (e) {
                console.error('WS 메시지 파싱 실패:', e);
            }
        };

        this.socket.onclose = () => {
            console.warn('WebSocket 끊김, 재연결 시도...');
            setTimeout(() => this.connect(), this.reconnectDelay);
        };

        this.socket.onerror = (e) => {
            console.error('WebSocket 오류:', e);
        };
    },

    // 타입당 핸들러를 누적(배열) — 같은 페이지의 여러 모듈이 동일 이벤트
    // (예: story_reset)를 각자 구독할 수 있게 한다. 이전엔 마지막 등록만 남았음.
    on(type, handler) {
        (this.handlers[type] ||= []).push(handler);
    }
};

SafetyWS.connect();
window.SafetyWS = SafetyWS;