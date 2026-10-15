// ============================================================
// Human Review Desk: escalated cases (left), the full case and the human decision (middle),
// the Tencent ADP policy assistant (right). Decisions are stored through
// POST /api/review/cases/{id}/decision -> reviews + review_details + audit log.
// ============================================================

// ?api=http://localhost:8001 points the page at another backend, as on the dashboard
const API_BASE = (new URLSearchParams(location.search).get('api') ||
    (location.protocol === 'file:' ? 'http://127.0.0.1:8000' : location.origin)).replace(/\/$/, '');
let apiToken = '';
async function api(path, options = {}) {
    const send = () => fetch(API_BASE + path, { ...options, headers: {
        'Content-Type': 'application/json', ...(apiToken ? { Authorization: `Bearer ${apiToken}` } : {}) } });
    let resp = await send();
    if (resp.status === 401 && !apiToken) {
        const code = window.prompt('Enter the access code supplied by the site administrator.');
        if (code) { apiToken = code.trim(); resp = await send(); }
    }
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(body.detail || `HTTP ${resp.status}`);
    return body;
}

const hv = {
    queue: [], current: null, data: null, showDone: false,
    mode: 'case', sessions: {}, consults: {},   // per ruling id: ADP Q&A kept for the decision record
};
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = v => v == null ? '—' : `S$${Number(v).toFixed(2)}`;
const words = v => String(v ?? '').replace(/_/g, ' ');
const hhmm = iso => { const m = String(iso || '').match(/T?(\d\d:\d\d)(:\d\d)?/); return m ? m[1] : esc(iso || ''); };
const VERDICTS = ['upheld', 'partially_upheld', 'dismissed'];
// ADP answers in Markdown; lists read fine as plain lines, bold needs rendering
const md = t => esc(t).replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>');

function toast(msg, type = '') {
    const t = $('hvToast');
    t.textContent = msg; t.className = `hv-toast show ${type}`;
    clearTimeout(toast.timer); toast.timer = setTimeout(() => t.classList.remove('show'), 3200);
}

// ---------------------------------------------------------------- queue

async function loadQueue() {
    try {
        hv.queue = (await api(`/api/review/queue?include_reviewed=${hv.showDone}`)).cases || [];
    } catch (e) {
        $('hvQueue').innerHTML = `<div class="hv-empty">Could not load cases (${esc(e.message)}).</div>`;
        return;
    }
    $('hvCount').textContent = hv.queue.filter(c => !c.review).length;
    renderQueue();
    if (!hv.current && hv.queue.length) selectCase(hv.queue[0].id);
}

function renderQueue() {
    $('hvQueue').innerHTML = hv.queue.map(c => `
        <button class="hv-item ${hv.current === c.id ? 'selected' : ''}" onclick="selectCase(${c.id})">
            <div class="hv-item-top"><b>${esc(c.dispute_id)}</b>
                ${c.review ? '<span class="hv-tag done">reviewed</span>' : `<span class="hv-tag esc">${esc(c.status === 'failed' ? 'failed' : 'escalated')}</span>`}
                <span class="when">#${c.id}</span></div>
            <div class="hv-item-desc">${esc(c.escalation_reason || c.description || words(c.dispute_type) || 'No details recorded')}</div>
        </button>`).join('') || '<div class="hv-empty">Nothing waiting. Every escalated case has a human decision.</div>';
}

// ---------------------------------------------------------------- case

async function selectCase(id) {
    hv.current = id; hv.data = null;
    renderQueue();
    renderChat();  // the assistant shows this case's own conversation
    $('hvCase').innerHTML = '<div class="hv-empty big">Loading case…</div>';
    try {
        const data = await api(`/api/review/cases/${id}`);
        if (hv.current !== id) return;
        hv.data = data;
    } catch (e) {
        $('hvCase').innerHTML = `<div class="hv-empty big">Could not load case (${esc(e.message)}).</div>`;
        return;
    }
    renderCase();
    renderChat();
}

// Snapshot (recorded at escalation) and the platform's raw dataset name things differently
function caseRecords(d) {
    const c = d.context, p = d.platform;
    if (c) return { description: c.description, reporter: c.reporter, type: c.type, trip: c.trip || {},
        chat: c.chat_log || [], gps: c.gps_trace || [], events: c.app_events || [],
        rider: c.rider_profile, driver: c.driver_profile, payment: c.payment, findings: c.findings || [],
        brief: c.case_brief, policy: c.platform_policy, filedAt: c.submitted_at, raw: c };
    if (p) { const t = p.dispute_ticket || {};
        return { description: t.description, reporter: t.filed_by, type: t.dispute_type, trip: p.trip_data || {},
            chat: p.chat_logs || [], gps: p.gps_telemetry || [], events: p.app_events || [],
            rider: p.rider_profile, driver: p.driver_profile, findings: [], policy: p.platform_policy,
            filedAt: t.filed_at, raw: p, olderRuling: true }; }
    return { trip: {}, chat: [], gps: [], events: [], findings: [], raw: {} };
}

function points(r) {
    let list = r.findings.filter(f => ['conflict', 'gap', 'fact'].includes(f.kind));
    if (!list.length && r.brief) list = [...(r.brief.conflicts || []).map(f => ({ ...f, kind: 'conflict' })),
        ...(r.brief.gaps || []).map(f => ({ ...f, kind: 'gap' })), ...(r.brief.facts || []).map(f => ({ ...f, kind: 'fact' }))];
    // Conflicts first: they are what the reviewer has to settle
    const order = { conflict: 0, gap: 1, fact: 2 };
    return list.sort((a, b) => order[a.kind] - order[b.kind]);
}

function rows(obj, keys) {
    if (!obj) return '<div class="hv-empty" style="padding:0">Not recorded.</div>';
    // {"name": "Clarke Quay", "lat": ...} -> "Clarke Quay"; {"total_disputes": 1, ...} -> "total disputes 1 · ..."
    const show = v => !v || typeof v !== 'object' ? v : Array.isArray(v) ? v.map(show).join(', ') || 'none'
        : v.name ?? Object.entries(v).map(([k, x]) => `${words(k)} ${typeof x === 'object' ? JSON.stringify(x) : x}`).join(' · ');
    return (keys || Object.keys(obj)).filter(k => obj[k] != null && obj[k] !== '' && !String(k).startsWith('_'))
        .map(k => `<div class="hv-row"><span>${esc(words(k))}</span><span class="${/fraud/.test(k) && obj[k] && obj[k] !== 0 && String(obj[k]) !== '[]' ? 'flag' : ''}">${esc(show(obj[k]))}</span></div>`).join('');
}

// Tone tags on a chat message (D52): tone if not calm, then key moments; "AI" when a model relabelled it
function toneTags(t) {
    if (!t) return '';
    const tags = [...(t.tone && t.tone !== 'calm' ? [t.tone] : []), ...(t.events || [])];
    if (!tags.length && t.decided_by === 'llm') tags.push('calm');
    return `<div class="hv-tones">${tags.map(x => `<span class="hv-tone ${esc(x)}">${esc(x)}</span>`).join('')}${
        t.decided_by === 'llm' ? `<span class="hv-tone ai" title="${esc(t.why || '')}">AI checked</span>` : ''}</div>`;
}

function renderCase() {
    const d = hv.data, ru = d.ruling, r = caseRecords(d), done = d.reviews.length > 0;
    const pts = points(r);
    const senderClass = s => /driver/i.test(s) ? 'driver' : /rider|passenger/i.test(s) ? 'rider' : 'system';
    const tone = d.response?.chat_signals
        ? Object.fromEntries((d.response.chat_signals.messages || []).map(m => [m.source, m])) : null;
    const html = `
        <header class="hv-casehead">
            <h2>${esc(ru.dispute_id)} <span class="hv-tag type">${esc(words(ru.dispute_type || r.type || 'unknown'))}</span></h2>
            <div class="meta">Ruling #${ru.id} · order ${esc(ru.order_id || '—')} · filed by ${esc(r.reporter || '—')}${r.filedAt ? ` · ${esc(String(r.filedAt).replace('T', ' ').slice(0, 16))}` : ''} · recorded ${esc(String(ru.created_at || '').slice(0, 16).replace('T', ' '))}</div>
        </header>
        ${done ? `<div class="hv-banner done"><div class="hv-label">Decided by a person</div>
            <p>${esc(words(d.reviews[d.reviews.length - 1].final_verdict))} · refund ${money(d.reviews[d.reviews.length - 1].final_refund)}</p></div>` : ''}
        <div class="hv-banner"><div class="hv-label">Why the AI handed this to a person${d.escalation?.source ? ` · ${esc(d.escalation.source)}` : ''}</div>
            <p>${esc(d.escalation?.reason || d.response?.reason || 'The escalation reason was not recorded for this older ruling.')}</p></div>

        <section class="hv-sec"><h3>Complaint <small>from the ${esc(r.reporter || 'filer')}</small></h3>
            <div class="hv-quote">${esc(r.description || 'No complaint text recorded.')}</div></section>

        <section class="hv-sec"><h3>Points in dispute <small>${pts.filter(p => p.kind === 'conflict').length} conflicts · ${pts.filter(p => p.kind === 'gap').length} gaps · from the Collector's checks of the records</small></h3>
            <div class="hv-points">${pts.map(p => `<div class="hv-point ${esc(p.kind)} ${p.disputed ? 'disputed' : ''}">
                <span class="k">${esc(p.kind === 'fact' && p.disputed ? 'disputed' : p.kind)}</span>
                <div>${esc(p.statement)}${(p.sources || []).length ? `<div class="src">source: ${esc(p.sources.join(', '))}</div>` : ''}</div></div>`).join('')
                || `<div class="hv-empty" style="padding:0">${r.olderRuling ? 'This ruling was recorded before the review desk captured findings. Read the records below.' : 'No conflicts or gaps were found.'}</div>`}</div></section>

        <section class="hv-sec"><h3>AI's proposal <small>${ru.verdict ? 'not executed: a person must decide' : 'none: the case went to a person before any ruling'}</small></h3>
            ${ru.verdict ? `<div class="hv-proposal"><div class="hv-tiles">
                <div class="hv-tile"><div class="hv-label">Verdict</div><div class="x">${esc(words(ru.verdict))}</div></div>
                <div class="hv-tile"><div class="hv-label">Refund</div><div class="x">${money(ru.refund_amount)}</div></div>
                <div class="hv-tile"><div class="hv-label">Confidence</div><div class="x">${ru.confidence != null ? Math.round(ru.confidence * 100) + '%' : '—'}</div></div></div>
                <div class="hv-prose">${esc(ru.rationale || '')}</div></div>`
            : '<div class="hv-empty" style="padding:0">The AI did not draft a ruling. Decide from the records and policy.</div>'}</section>

        <section class="hv-sec"><h3>Trip and people</h3><div class="hv-cards">
            <div class="hv-card"><h4 class="hv-label">Trip</h4>${rows(r.trip)}</div>
            <div class="hv-card rider"><h4 class="hv-label">Rider</h4>${rows(r.rider)}</div>
            <div class="hv-card driver"><h4 class="hv-label">Driver</h4>${rows(r.driver)}</div>
            ${r.payment ? `<div class="hv-card"><h4 class="hv-label">Payment</h4>${rows(r.payment)}</div>` : ''}
        </div></section>

        <section class="hv-sec"><h3>In-app chat <small>${r.chat.length} messages${tone ? ' · tone tags: code, doubtful ones checked by a model; never used in the ruling' : ''}</small></h3>
            <div class="hv-chatlog">${r.chat.map((m, i) => `<div class="hv-msg ${senderClass(m.sender)}">
                <div class="who">${esc(m.sender || 'system')}<time>${hhmm(m.timestamp)}</time></div>${esc(m.content ?? m.message ?? '')}${toneTags(tone?.[`chat_log[${i}]`])}</div>`).join('')
                || '<div class="hv-empty" style="padding:0">No chat.</div>'}</div></section>

        <section class="hv-sec"><h3>App events <small>${r.events.length} events · ${r.gps.length} GPS points</small></h3>
            <ul class="hv-tl">${r.events.map(e => `<li><span class="t">${hhmm(e.timestamp)}</span><span class="e">${esc(words(e.event_type))}</span>
                <span class="d">${esc(JSON.stringify(e.details ?? Object.fromEntries(Object.entries(e).filter(([k]) => !['timestamp', 'event_type'].includes(k)))))}</span></li>`).join('')
                || '<li><span class="d">No events.</span></li>'}</ul>
            ${r.policy ? `<details class="hv-raw"><summary>This trip's platform rules (${Object.keys(r.policy).length})</summary><pre>${esc(JSON.stringify(r.policy, null, 2))}</pre></details>` : ''}
            <details class="hv-raw"><summary>All records (JSON)</summary><pre>${esc(JSON.stringify(r.raw, null, 2))}</pre></details></section>

        ${done ? `<section class="hv-sec"><h3>Human decisions</h3><div class="hv-past">${d.reviews.map(v => `<div class="hv-card">
            <div class="hv-row"><span>Decision</span><span>${esc(v.action)} → ${esc(words(v.final_verdict))} · ${money(v.final_refund)}</span></div>
            ${v.driver_penalty ? `<div class="hv-row"><span>Driver</span><span>${esc(v.driver_penalty)}</span></div>` : ''}
            <div class="hv-row"><span>By</span><span>${esc(v.reviewer_name ? `${v.reviewer_name} (${v.reviewer})` : v.reviewer)} · ${esc(String(v.created_at).slice(0, 16).replace('T', ' '))}</span></div>
            <div class="hv-prose" style="margin-top:8px">${esc(v.reason)}</div>
            ${v.internal_note ? `<div class="hv-prose" style="color:var(--text-muted);margin-top:6px">Note: ${esc(v.internal_note)}</div>` : ''}
            ${(v.ai_consultations || []).length ? `<div class="hv-row"><span>AI consulted</span><span>${v.ai_consultations.length} question(s)</span></div>` : ''}
        </div>`).join('')}</div></section>` : ''}

        ${renderForm(ru, done)}`;
    $('hvCase').innerHTML = html;
    $('hvCase').scrollTop = 0;
    bindForm(ru);
}

// ---------------------------------------------------------------- decision

function renderForm(ru, done) {
    const consults = hv.consults[ru.id] || [];
    return `<form class="hv-decide" id="hvForm">
        <h3>${done ? 'Record another decision' : 'Your decision'}</h3>
        <div class="hv-hint" style="padding:0">Saved to the database with your access identity and written to the audit log. It also becomes a pending precedent the AI can learn from after approval.</div>
        <div class="hv-choice">
            <label><input type="radio" name="action" value="confirm" ${ru.verdict ? '' : 'disabled'}> Confirm the AI's proposal</label>
            <label><input type="radio" name="action" value="override" checked> Make my own decision</label>
        </div>
        <div class="hv-grid">
            <label class="hv-field"><span>Verdict <em>*</em></span><select name="final_verdict">
                <option value="">Choose…</option>${VERDICTS.map(v => `<option value="${v}">${words(v)}</option>`).join('')}</select></label>
            <label class="hv-field"><span>Refund (S$)</span><input name="final_refund" type="number" min="0" step="0.01" placeholder="0.00"></label>
            <label class="hv-field"><span>Driver action</span><input name="driver_penalty" maxlength="200" placeholder="e.g. warning, suspend pending investigation"></label>
            <label class="hv-field"><span>Your name</span><input name="reviewer_name" maxlength="64" placeholder="shown next to the decision"></label>
            <label class="hv-field full"><span>Reason <em>*</em> <small style="color:var(--text-muted);font-weight:400">which records and which policy decided it</small></span><textarea name="reason" required></textarea></label>
            <label class="hv-field full"><span>Internal note</span><textarea name="internal_note" style="min-height:56px" placeholder="not sent to either party"></textarea></label>
        </div>
        <label class="hv-toggle" style="margin-top:10px"><input type="checkbox" name="attach" ${consults.length ? 'checked' : 'disabled'}>
            Attach the ${consults.length} question(s) asked to the policy assistant</label>
        <div class="hv-actions"><button class="hv-btn primary" type="submit">Save decision</button>
            <span class="hv-hint" style="padding:0" id="hvFormMsg"></span></div>
    </form>`;
}

function bindForm(ru) {
    const form = $('hvForm');
    const sync = () => {
        const confirm = form.action.value === 'confirm';
        if (confirm) { form.final_verdict.value = ru.verdict || ''; form.final_refund.value = ru.refund_amount ?? ''; }
        form.final_verdict.disabled = form.final_refund.disabled = confirm;
    };
    form.querySelectorAll('input[name=action]').forEach(i => i.addEventListener('change', sync));
    form.addEventListener('submit', async ev => {
        ev.preventDefault();
        const action = form.action.value;
        const verdict = form.final_verdict.value || null;
        if (action === 'override' && !verdict) { toast('Choose a verdict.', 'error'); form.final_verdict.focus(); return; }
        if (!form.reason.value.trim()) { toast('Write the reason for the decision.', 'error'); form.reason.focus(); return; }
        const body = {
            action, reason: form.reason.value.trim(),
            final_verdict: action === 'override' ? verdict : null,
            final_refund: action === 'override' && form.final_refund.value !== '' ? Number(form.final_refund.value) : null,
            driver_penalty: form.driver_penalty.value, internal_note: form.internal_note.value,
            reviewer_name: form.reviewer_name.value,
            ai_consultations: form.attach.checked ? hv.consults[ru.id] || [] : [],
        };
        const btn = form.querySelector('button[type=submit]');
        btn.disabled = true; $('hvFormMsg').textContent = 'Saving…';
        try {
            const res = await api(`/api/review/cases/${ru.id}/decision`, { method: 'POST', body: JSON.stringify(body) });
            toast(`Decision saved (review #${res.review_id}${res.precedent ? `, precedent #${res.precedent.id} pending approval` : ''}).`);
            hv.consults[ru.id] = [];
            await loadQueue();
            await selectCase(ru.id);
        } catch (e) {
            toast(`Not saved: ${e.message}`, 'error');
            $('hvFormMsg').textContent = '';
            btn.disabled = false;
        }
    });
    sync();
}

// ---------------------------------------------------------------- ADP assistant

const SUGGEST = {
    case: ['How should this case be ruled under Ryde policy?', 'Which policies apply to the points in dispute?',
           'What action should be taken against the driver, if any?', 'Is the rider owed a refund, and how much?'],
    policy: ['What is the cancellation fee after a driver is assigned?', 'When can a driver charge a no-show fee?',
             'What evidence is needed for a cleaning fee claim?', 'What happens after a safety report?'],
};
const chatKey = () => hv.mode === 'case' ? `case-${hv.current}` : 'policy';
hv.chats = {};

function renderChat() {
    $('hvSuggest').innerHTML = SUGGEST[hv.mode].map(q => `<button type="button" onclick="askADP(${JSON.stringify(q).replace(/"/g, '&quot;')})">${esc(q)}</button>`).join('');
    const msgs = hv.chats[chatKey()] || [];
    $('hvChat').innerHTML = msgs.map(m => m.q != null ? `<div class="hv-q">${esc(m.q)}</div>`
        : `<div class="hv-a ${m.err ? 'err' : ''} ${m.thinking ? 'thinking' : ''}"><div class="hv-prose">${md(m.a || (m.thinking ? 'Searching Ryde policy' : ''))}</div>
            ${(m.references || []).length ? `<div class="hv-refs">${m.references.map(r => `<span>${esc(r)}</span>`).join('')}</div>` : ''}</div>`).join('')
        || `<div class="hv-empty" style="padding:8px 0">${hv.mode === 'case'
            ? (hv.current ? 'Questions here include this case\'s summary and points in dispute, so the assistant answers about this case.' : 'Pick a case first.')
            : 'Ask about any Ryde policy. The case is not sent.'}</div>`;
    $('hvChat').scrollTop = $('hvChat').scrollHeight;
    $('hvQuestion').placeholder = hv.mode === 'case' ? 'Ask how policy applies to this case…' : 'Ask about a Ryde policy…';
}

async function askADP(question) {
    question = (question || '').trim();
    if (!question) return;
    if (hv.mode === 'case' && !hv.current) { toast('Pick a case first.', 'error'); return; }
    const key = chatKey(), rulingId = hv.mode === 'case' ? hv.current : null;
    const msgs = hv.chats[key] = hv.chats[key] || [];
    const pending = { thinking: true };
    msgs.push({ q: question }, pending);
    $('hvQuestion').value = ''; $('hvAskBtn').disabled = true;
    renderChat();
    try {
        const res = await api('/api/review/ask', { method: 'POST',
            body: JSON.stringify({ question, ruling_id: rulingId, session_id: hv.sessions[key] || null }) });
        hv.sessions[key] = res.session_id;
        Object.assign(pending, { thinking: false, a: res.answer || 'No answer was returned.', references: res.references });
        if (rulingId != null) {
            (hv.consults[rulingId] = hv.consults[rulingId] || []).push({ q: question, a: res.answer, references: res.references });
            if (hv.current === rulingId && hv.data) refreshAttach(rulingId);
        }
    } catch (e) {
        Object.assign(pending, { thinking: false, err: true, a: `The policy assistant is unavailable: ${e.message}` });
    } finally {
        $('hvAskBtn').disabled = false;
        if (chatKey() === key) renderChat();
    }
}

// Keep the decision form's typed values; only update the "attach questions" line
function refreshAttach(rulingId) {
    const box = $('hvForm')?.attach;
    if (!box) return;
    const n = (hv.consults[rulingId] || []).length;
    box.disabled = !n; box.checked = !!n;
    box.parentElement.lastChild.textContent = ` Attach the ${n} question(s) asked to the policy assistant`;
}

document.querySelectorAll('.hv-mode').forEach(b => b.addEventListener('click', () => {
    hv.mode = b.dataset.mode;
    document.querySelectorAll('.hv-mode').forEach(x => { x.classList.toggle('active', x === b); x.setAttribute('aria-selected', x === b); });
    renderChat();
}));
$('hvAskForm').addEventListener('submit', ev => { ev.preventDefault(); askADP($('hvQuestion').value); });
$('hvQuestion').addEventListener('keydown', ev => {
    if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); askADP($('hvQuestion').value); }
});
$('hvShowDone').addEventListener('change', e => { hv.showDone = e.target.checked; loadQueue(); });

renderChat();
loadQueue();
