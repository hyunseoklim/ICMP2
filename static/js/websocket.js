/**
 * websocket.js — WebSocket 연결 관리자
 * 재연결 지수 백오프, 메시지 타입 라우팅
 */

(function() {
  const WS_URL = (location.protocol === 'https:' ? 'wss' : 'ws')
                 + '://' + location.host + '/ws/monitoring/';

  let socket = null;
  let reconnectDelay = 1000;
  const MAX_DELAY = 30000;
  const handlers = {};

  function connect() {
    socket = new WebSocket(WS_URL);

    socket.addEventListener('open', () => {
      console.info('[WS] 연결됨');
      reconnectDelay = 1000;
      document.dispatchEvent(new CustomEvent('wsConnected'));
    });

    socket.addEventListener('message', e => {
      try {
        const data = JSON.parse(e.data);
        const type = data.type;
        if (handlers[type]) {
          handlers[type].forEach(fn => fn(data.payload));
        }
        // 전체 구독자에게도 전달
        if (handlers['*']) {
          handlers['*'].forEach(fn => fn(data));
        }
      } catch (err) {
        console.warn('[WS] 메시지 파싱 실패', err);
      }
    });

    socket.addEventListener('close', () => {
      console.warn(`[WS] 연결 끊김. ${reconnectDelay}ms 후 재연결`);
      document.dispatchEvent(new CustomEvent('wsDisconnected'));
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_DELAY);
    });

    socket.addEventListener('error', err => {
      console.error('[WS] 오류', err);
      socket.close();
    });
  }

  /**
   * 특정 메시지 타입 구독
   * @param {string} type - 'worker_update' | 'gas_alert' | 'power_alert' | 'event_new' | '*'
   * @param {Function} fn
   */
  function on(type, fn) {
    if (!handlers[type]) handlers[type] = [];
    handlers[type].push(fn);
  }

  function off(type, fn) {
    if (!handlers[type]) return;
    handlers[type] = handlers[type].filter(h => h !== fn);
  }

  function send(type, payload) {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type, payload }));
    }
  }

  // 연결 시작
  connect();

  // 전역 노출
  window.SafetyWS = { on, off, send };
})();
