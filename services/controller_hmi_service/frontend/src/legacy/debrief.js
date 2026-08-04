// debrief.js — instructor debrief modal shown after "End Session".

const Debrief = (() => {
    const API = '/api/v1/hmi/debrief/generate';
    let _closeResolver = null;

    function _modal() { return document.getElementById('debrief-modal'); }
    function _body()  { return document.getElementById('debrief-body'); }

    function _openModal() {
        const m = _modal();
        if (!m) return;
        m.classList.remove('debrief-hidden');
        const closeBtn = document.getElementById('debrief-close');
        if (closeBtn && !closeBtn.dataset.wired) {
            closeBtn.dataset.wired = '1';
            closeBtn.addEventListener('click', _closeModal);
        }
    }

    function _closeModal() {
        const m = _modal();
        if (m) m.classList.add('debrief-hidden');
        if (_closeResolver) { _closeResolver(); _closeResolver = null; }
    }

    function _showLoading(text) {
        const b = _body();
        if (b) b.innerHTML = `<div class="debrief-loading">${text}</div>`;
    }

    function _showError(text) {
        const b = _body();
        if (b) b.innerHTML = `<div class="debrief-error">${_escape(text)}</div>`;
    }

    function _escape(s) {
        return String(s || '').replace(/[&<>"]/g, c => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]
        ));
    }

    function _renderJson(data) {
        const b = _body();
        if (!b) return;
        if (data.too_short || !data.debrief) {
            b.innerHTML = `<div class="debrief-empty">${_escape(
                'Session too short to evaluate — no transmissions were captured.'
            )}</div>`;
            return;
        }
        const d = data.debrief;
        const overall = d.overall_score ?? '?';
        const cats = Array.isArray(d.categories) ? d.categories : [];

        const catHtml = cats.map(cat => {
            const examples = (cat.examples || []).map(ex => {
                const mark = (ex.verdict || '').toLowerCase() === 'good' ? '✔'
                           : (ex.verdict || '').toLowerCase() === 'bad'  ? '✘' : '·';
                const cls = (ex.verdict || '').toLowerCase() === 'good' ? 'good'
                           : (ex.verdict || '').toLowerCase() === 'bad'  ? 'bad' : '';
                return `<li class="debrief-ex ${cls}">
                    <span class="debrief-ex-mark">${mark}</span>
                    <div class="debrief-ex-body">
                        <div class="debrief-ex-head"><strong>${_escape(ex.ts || '--:--:--')}</strong>
                        <em>"${_escape(ex.quote || '')}"</em></div>
                        <div class="debrief-ex-note">${_escape(ex.note || '')}</div>
                    </div>
                </li>`;
            }).join('');
            return `<section class="debrief-category">
                <header class="debrief-cat-head">
                    <h3>${_escape((cat.name || '').replace(/^./, c => c.toUpperCase()))}</h3>
                    <span class="debrief-score">${cat.score ?? '?'}<small>/10</small></span>
                </header>
                <p class="debrief-cat-summary">${_escape(cat.summary || '')}</p>
                ${examples ? `<ul class="debrief-examples">${examples}</ul>` : ''}
            </section>`;
        }).join('');

        const strengths = (d.strengths || []).map(s => `<li>${_escape(s)}</li>`).join('');
        const improvements = (d.improvements || []).map(s => `<li>${_escape(s)}</li>`).join('');
        const summary = _escape(d.instructor_summary || '');

        b.innerHTML = `
            <div class="debrief-overall">
                <span class="debrief-overall-label">Overall</span>
                <span class="debrief-overall-score">${overall}<small>/100</small></span>
            </div>
            <div class="debrief-grid">${catHtml}</div>
            ${strengths ? `<section class="debrief-block"><h3>Strengths</h3><ul>${strengths}</ul></section>` : ''}
            ${improvements ? `<section class="debrief-block"><h3>Improvements</h3><ul>${improvements}</ul></section>` : ''}
            ${summary ? `<section class="debrief-narrative"><h3>Instructor summary</h3><p>${summary}</p></section>` : ''}
        `;
    }

    async function openAndGenerate(sessionId, icao) {
        _openModal();
        _showLoading('Generating instructor debrief…');
        try {
            const resp = await fetch(API, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, airport_icao: icao || '' }),
            });
            if (!resp.ok) {
                const txt = await resp.text().catch(() => '');
                _showError(`Debrief failed (${resp.status}). ${txt}`);
                return;
            }
            const data = await resp.json();
            _renderJson(data);
        } catch (err) {
            _showError('Debrief request failed: ' + (err && err.message ? err.message : err));
        }
    }

    function waitClose() {
        return new Promise(resolve => { _closeResolver = resolve; });
    }

    return { openAndGenerate, waitClose };
})();

// Bridge for the inline on*= handlers in index.html (removed in Phase 3).
window.Debrief = Debrief;
export { Debrief };
