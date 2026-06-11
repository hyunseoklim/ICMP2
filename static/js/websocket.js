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
                if (this.handlers[data.type]) {
                    this.handlers[data.type](data);
                }
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

    on(type, handler) {
        this.handlers[type] = handler;
    }
};

SafetyWS.connect();
window.SafetyWS = SafetyWS;