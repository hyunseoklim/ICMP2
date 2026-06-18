/**
 * alert_popup.js — 실시간 위험/주의 알람 팝업
 * /alerts/api/recent/ 를 5초마다 폴링 → 새 알람 감지 시 팝업 표시
 */
const AlertPopup = (() => {
    const POLL_INTERVAL = 5000;
    const SEEN_KEY = 'alert_popup_seen_ids';
    let queue = [];
    let isShowing = false;

    function getSeenIds() {
        try {
            return new Set(JSON.parse(sessionStorage.getItem(SEEN_KEY) || '[]'));
        } catch { return new Set(); }
    }

    function markSeen(id) {
        const seen = getSeenIds();
        seen.add(id);
        // 최대 200개만 보관 (메모리 방어)
        const arr = [...seen].slice(-200);
        sessionStorage.setItem(SEEN_KEY, JSON.stringify(arr));
    }

    function formatTime(isoStr) {
        const d = new Date(isoStr);
        const pad = n => String(n).padStart(2, '0');
        return `${d.getFullYear()} - ${pad(d.getMonth()+1)} - ${pad(d.getDate())} ` +
               `${pad(d.getHours())} : ${pad(d.getMinutes())} : ${pad(d.getSeconds())}`;
    }

    function buildPopupHTML(alarm) {
        const isDanger  = alarm.severity === 'danger';
        const colorClass = isDanger ? 'danger' : 'warning';
        const label      = isDanger ? '위험' : '주의';
        const headline   = isDanger ? '즉시 대피하세요!' : '주의하세요!';

        const icon = isDanger
            ? `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                 <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
                 <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
               </svg>`
            : `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                 <circle cx="12" cy="12" r="10"/>
                 <line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
               </svg>`;

        const detailUrl = '/alerts/';

        return `
        <div class="alert-popup-overlay" id="alertPopupOverlay">
          <div class="alert-popup-box alert-popup-box--${colorClass}">
            <div class="alert-popup-time">
              <span class="alert-popup-time-dot"></span>
              발생 시간&nbsp;&nbsp;${formatTime(alarm.occurred_at)}
            </div>
            <div class="alert-popup-icon alert-popup-icon--${colorClass}">${icon}</div>
            <div class="alert-popup-type">긴급 알림</div>
            <div class="alert-popup-headline alert-popup-headline--${colorClass}">${headline}</div>
            <div class="alert-popup-badge-row">
              <span class="alert-popup-badge alert-popup-badge--${colorClass}">${label}</span>
              <span class="alert-popup-msg">${alarm.message || alarm.title}</span>
            </div>
            <div class="alert-popup-actions">
              <a href="${detailUrl}" class="alert-popup-btn alert-popup-btn--detail">상세 확인</a>
              <button class="alert-popup-btn alert-popup-btn--confirm" id="alertPopupConfirm">확인</button>
            </div>
          </div>
        </div>`;
    }

    function showNext() {
        if (isShowing || queue.length === 0) return;
        const alarm = queue.shift();
        isShowing = true;

        document.body.insertAdjacentHTML('beforeend', buildPopupHTML(alarm));

        const overlay = document.getElementById('alertPopupOverlay');
        const confirmBtn = document.getElementById('alertPopupConfirm');

        confirmBtn.addEventListener('click', () => close(overlay));
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) close(overlay);
        });
    }

    function close(overlay) {
        overlay.classList.add('alert-popup-overlay--hiding');
        overlay.addEventListener('animationend', () => {
            overlay.remove();
            isShowing = false;
            showNext();
        }, { once: true });
    }

    async function poll() {
        try {
            const res = await fetch('/alerts/api/recent/?minutes=1&limit=10&mine=true');
            if (!res.ok) return;
            const data = await res.json();
            const seen = getSeenIds();

            const newAlarms = data
                .filter(a => (a.severity === 'danger' || a.severity === 'warning') && !seen.has(a.id));

            newAlarms.forEach(a => {
                markSeen(a.id);
                queue.push(a);
            });

            // danger 먼저 표시
            queue.sort((a, b) => {
                const rank = { danger: 0, warning: 1 };
                return (rank[a.severity] ?? 2) - (rank[b.severity] ?? 2);
            });

            showNext();
        } catch (e) {
            console.warn('[AlertPopup] 폴링 실패:', e);
        }
    }

    function handleIncoming(alarm) {
        const seen = getSeenIds();
        if (seen.has(alarm.id)) return;
        if (alarm.severity !== 'danger' && alarm.severity !== 'warning') return;
        markSeen(alarm.id);
        queue.push(alarm);
        queue.sort((a, b) => ({ danger: 0, warning: 1 }[a.severity] ?? 2) - ({ danger: 0, warning: 1 }[b.severity] ?? 2));
        showNext();
    }

    function connectWS() {
        const ws = new WebSocket(`ws://${location.host}/ws/alerts/`);

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'alert' && msg.data) handleIncoming(msg.data);
            } catch (e) {
                console.warn('[AlertPopup] WS 메시지 파싱 실패:', e);
            }
        };

        ws.onclose = () => setTimeout(connectWS, 3000);
        ws.onerror = () => ws.close();

        return ws;
    }

    function init() {
        connectWS();
        poll();
        setInterval(poll, POLL_INTERVAL);
    }

    return { init, poll };
})();

document.addEventListener('DOMContentLoaded', () => AlertPopup.init());
window.AlertPopup = AlertPopup;
