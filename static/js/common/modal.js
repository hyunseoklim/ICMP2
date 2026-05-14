/**
 * 공용 모달 (common-modal)
 *
 * 사용처: templates/components/confirm_modal.html 가 include 된 페이지
 *
 * API:
 *   window.Modal.confirm({ title, message, onConfirm, onCancel })
 *     - [취소] / [확인] 두 버튼 표시
 *     - 확인 → onConfirm() 호출 후 닫힘
 *     - 취소 → onCancel() 호출 후 닫힘
 *
 *   window.Modal.info({ title, message, onClose })
 *     - [확인] 버튼만 표시 ([취소] 숨김)
 *     - 확인 → onClose() 호출 후 닫힘
 */
(function () {
    const overlay    = document.getElementById('common-modal-overlay');
    const titleEl    = document.getElementById('common-modal-title');
    const messageEl  = document.getElementById('common-modal-message');
    const cancelBtn  = document.getElementById('common-modal-cancel');
    const confirmBtn = document.getElementById('common-modal-confirm');

    if (!overlay || !confirmBtn) {
        console.warn('[modal] common-modal element 미발견 — confirm_modal.html include 여부 확인');
        return;
    }

    let currentOnConfirm = null;
    let currentOnCancel  = null;
    let currentOnClose   = null;

    function show({ title, message, showCancel }) {
        if (titleEl)   titleEl.textContent   = title   || '';
        if (messageEl) {
            messageEl.textContent = message || '';
            messageEl.style.display = message ? '' : 'none';
        }
        if (cancelBtn) cancelBtn.style.display = showCancel ? '' : 'none';
        overlay.style.display = 'flex';
        overlay.setAttribute('aria-hidden', 'false');
    }

    function hide() {
        overlay.style.display = 'none';
        overlay.setAttribute('aria-hidden', 'true');
        // 콜백은 hide 호출 전에 백업 후 처리 (재진입 안전)
    }

    cancelBtn?.addEventListener('click', () => {
        const cb = currentOnCancel;
        currentOnConfirm = null;
        currentOnCancel  = null;
        currentOnClose   = null;
        hide();
        if (typeof cb === 'function') {
            try { cb(); } catch (e) { console.error('[modal] onCancel 콜백 오류:', e); }
        }
    });

    confirmBtn.addEventListener('click', () => {
        const cb    = currentOnConfirm;
        const close = currentOnClose;
        currentOnConfirm = null;
        currentOnCancel  = null;
        currentOnClose   = null;
        hide();
        if (typeof cb === 'function') {
            try { cb(); } catch (e) { console.error('[modal] onConfirm 콜백 오류:', e); }
        }
        if (typeof close === 'function') {
            try { close(); } catch (e) { console.error('[modal] onClose 콜백 오류:', e); }
        }
    });

    window.Modal = {
        confirm({ title, message, onConfirm, onCancel } = {}) {
            currentOnConfirm = onConfirm || null;
            currentOnCancel  = onCancel  || null;
            currentOnClose   = null;
            show({ title, message, showCancel: true });
        },
        info({ title, message, onClose } = {}) {
            currentOnConfirm = null;
            currentOnCancel  = null;
            currentOnClose   = onClose || null;
            show({ title, message, showCancel: false });
        },
    };
})();
