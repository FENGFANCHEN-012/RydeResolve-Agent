// ============================================================
// Dispute Resolution tab
// Pick a mock case -> see exactly what data is sent -> run the agents
// (POST /api/disputes/resolve-stream, SSE) or replay a saved run ->
// watch each agent in the flow graph, inspect its reasoning, retrieved
// policy clauses, input/output and raw LLM calls, and compare the
// verdict with the case's answer key.
// Relies on API_BASE and showToast() from index.html.
// ============================================================

const RR_TYPE_COLORS = {
    route_deviation: '#2563eb', no_show: '#0d9488', no_show_charge: '#0d9488',
    fare_dispute: '#d97706', cancellation_refund: '#7c3aed', service_quality: '#db2777',
    driver_rights: '#0891b2', cleaning_fee: '#65a30d', accident_liability: '#dc2626',
    safety_incident: '#dc2626',
};

// Graph nodes: grid position + what flows in and out (shown in the inspector)
const RR_NODES = {
    case:       { name: 'Case data', role: 'Mock platform record', color: 'var(--agent-case)', col: 1, row: 2,
                  receives: ['Dataset file (answer key stripped)'],
                  sends: ['Ticket, trip, GPS, chat, app events, profiles, policy → Collector'] },
    collector:  { name: 'Collector', role: 'Gather & normalise', color: 'var(--agent-collector)', col: 2, row: 2,
                  receives: ['Case data', 'Complaint text override (optional)'],
                  sends: ['DisputeContext → Classifier, advocates, Policy, Arbitrator'] },
    classifier: { name: 'Classifier', role: 'Type & urgency', color: 'var(--agent-classifier)', col: 3, row: 2,
                  receives: ['Complaint text', 'Type stated in the case data'],
                  sends: ['Dispute type → advocates & Policy (RAG query)', 'P0 → human review, skipping the debate'] },
    passenger:  { name: 'Passenger', role: 'Rider advocate', color: 'var(--agent-passenger)', col: 4, row: 1,
                  receives: ['DisputeContext', 'Dispute type', 'Policy clauses (RAG)'],
                  sends: ['Opening analysis → debate & Arbitrator'] },
    policy:     { name: 'Policy', role: 'RAG compliance check', color: 'var(--agent-policy)', col: 4, row: 2,
                  receives: ['DisputeContext', 'Dispute type', 'Policy clauses (RAG)'],
                  sends: ['Who complied, violations, clause refs → Arbitrator'] },
    driver:     { name: 'Driver', role: 'Driver advocate', color: 'var(--agent-driver)', col: 4, row: 3,
                  receives: ['DisputeContext', 'Dispute type', 'Policy clauses (RAG)'],
                  sends: ['Opening analysis → debate & Arbitrator'] },
    debate:     { name: 'Debate', role: 'Rebuttal rounds', color: 'var(--agent-debate)', col: 5, row: '1 / span 3',
                  receives: ['Both opening analyses', "Each rebuttal answers the other side's latest turn"],
                  sends: ['Full debate transcript → Arbitrator'] },
    arbitrator: { name: 'Arbitrator', role: 'Weigh & rule', color: 'var(--agent-arbitrator)', col: 6, row: 2,
                  receives: ['DisputeContext', 'Passenger & driver analyses', 'Policy evaluation', 'Debate transcript'],
                  sends: ['Decision (verdict, refund, penalty) → Fairness'] },
    fairness:   { name: 'Fairness', role: 'Audit the decision', color: 'var(--agent-fairness)', col: 7, row: 2,
                  receives: ['Decision', 'Passenger & driver analyses', 'Policy evaluation', 'Debate transcript'],
                  sends: ['Proceed → Executor', 'Escalate / amend / block → human review'] },
    executor:   { name: 'Executor', role: 'Apply decision', color: 'var(--agent-executor)', col: 8, row: 2,
                  receives: ['Decision cleared by Fairness'], sends: ['Simulated refund / penalty / notifications'] },
    human:      { name: 'Human review', role: 'Escalated', color: 'var(--agent-human)', col: '6 / span 3', row: 3,
                  receives: ['Classifier: P0 / safety', 'Fairness: decision not cleared', 'Any agent failure'],
                  sends: ['Case handed to a person — no automated ruling'] },
};

// [from, to, label]
const RR_EDGES = [
    ['case', 'collector', 'dataset'],
    ['collector', 'classifier', 'context'],
    ['classifier', 'passenger', 'type'],
    ['classifier', 'policy', 'RAG query'],
    ['classifier', 'driver', 'type'],
    ['passenger', 'debate', 'opening'],
    ['driver', 'debate', 'opening'],
    ['policy', 'arbitrator', 'compliance'],
    ['debate', 'arbitrator', 'transcript'],
    ['arbitrator', 'fairness', 'decision'],
    ['fairness', 'executor', 'cleared'],
    ['classifier', 'human', 'P0 escalation'],
    ['fairness', 'human', 'not cleared'],
];

const RR_REASONING_KEYS = [
    'verdict', 'dispute_type', 'urgency', 'confidence', 'stance', 'reasoning', 'rationale',
    'remedy_requested', 'evidence', 'contradictory_evidence', 'missing_evidence', 'obligations',
    'passenger_compliant', 'driver_compliant', 'violations', 'policy_references',
    'refund_amount', 'compensation', 'driver_penalty', 'actions_taken',
    'requires_human', 'requires_human_review', 'human_review_needed', 'escalation_recommended',
    'recommendation', 'fairness_passed', 'reason', 'issues',
];

const rr = {
    cases: [], filter: '', current: null, detail: null,
    steps: {}, order: [], result: null, running: false, selected: 'case', follow: true,
};

const rrEl = id => document.getElementById(id);

function rrEsc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}
function rrTypeBadge(type) {
    const t = type || 'unknown';
    return `<span class="rr-type" style="--t:${RR_TYPE_COLORS[t] || '#9ca3af'}">${rrEsc(t.replace(/_/g, ' '))}</span>`;
}
function rrTime(iso) {
    if (!iso) return '—';
    const m = String(iso).match(/T(\d\d:\d\d)(:\d\d)?/);
    return m ? m[1] + (m[2] && m[2] !== ':00' ? m[2] : '') : String(iso);
}
function rrMoney(v) { return v == null ? '—' : `S$${Number(v).toFixed(2)}`; }
function rrParse(v) {
    if (typeof v !== 'string') return v;
    const t = v.trim().replace(/^```(?:json)?\s*|```$/g, '');
    if (!/^[\[{]/.test(t)) return v;
    try { return JSON.parse(t); } catch (e) { return v; }
}
function rrJson(value) {
    if (typeof value === 'string') return rrEsc(value);
    return rrEsc(JSON.stringify(value, null, 2) ?? 'null')
        .replace(/(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)?/g,
                 (m, str, colon) => colon ? `<span class="jk">${str}</span>${colon}` : `<span class="js">${str}</span>`)
        .replace(/\b(-?\d+(?:\.\d+)?)\b(?![^<]*<\/span>)/g, '<span class="jn">$1</span>')
        .replace(/\b(true|false|null)\b(?![^<]*<\/span>)/g, '<span class="jb">$1</span>');
}
function rrClip(s, n) { s = String(s ?? ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; }

// The trace keeps full provider errors under Raw data. Summaries must not
// mistake a quota fallback for an agent's analysis or a valid ruling.
function rrStepIssue(step) {
    if (!step || step.status === 'running') return null;
    const out = rrParse(step.output);
    const details = [
        ...(step.llm || []).map(call => call.error),
        step.error,
        typeof out === 'string' ? out : out?.error,
        out?.reasoning, out?.reason,
    ].filter(value => typeof value === 'string').join(' ');
    if (/tokens per day|\\bTPD\\b/i.test(details) && /rate_limit_exceeded|429/i.test(details)) {
        return { kind: 'daily', short: 'Groq daily token limit reached',
            message: 'Groq’s daily token limit was reached. The remaining AI analysis was not completed, so this run has no reliable verdict.' };
    }
    if (/GenerateRequestsPerDay|requests per day|daily quota/i.test(details)) {
        return { kind: 'daily', short: 'Gemini daily limit reached',
            message: 'Gemini’s daily request limit was reached. This turn has no AI analysis; the run cannot produce a reliable verdict.' };
    }
    if (/GenerateRequestsPerMinute|requests per minute/i.test(details)) {
        return { kind: 'minute', short: 'Gemini rate limit reached',
            message: 'Gemini’s short-term request limit was reached. This turn has no AI analysis.' };
    }
    if (step.status === 'error' || (step.llm || []).some(call => call.error) ||
            /LLM call failed|could not be generated automatically/i.test(details)) {
        return { kind: 'error', short: 'AI analysis unavailable',
            message: 'This turn could not be generated. Open Raw data for the technical details.' };
    }
    return null;
}

function rrRunIssue() {
    const issues = rr.order.map(id => rrStepIssue(rr.steps[id])).filter(Boolean);
    return issues.find(issue => issue.kind === 'daily') || null;
}

function rrDebateText(output, agent) {
    const out = rrParse(output);
    if (typeof out === 'string') {
        return /^\s*(?:\{|```json\b)/i.test(out)
            ? 'The reply was not readable. Select this turn to inspect its raw output.' : out;
    }
    if (!out || typeof out !== 'object') return 'No analysis was returned.';
    if (agent === 'Policy') {
        const yn = value => value === true ? 'complied' : value === false ? 'did not comply' : 'unclear';
        return `Rider ${yn(out.passenger_compliant)}; driver ${yn(out.driver_compliant)}.` +
            (out.violations?.length ? `\nPossible violations: ${out.violations.join('; ')}` : '') +
            (out.reasoning ? `\n${out.reasoning}` : '');
    }
    const summary = [out.stance, out.reasoning, out.summary, out.rationale]
        .filter(value => typeof value === 'string' && value.trim()).join('\n\n');
    const refs = Array.isArray(out.policy_references)
        ? out.policy_references.filter(value => typeof value === 'string').slice(0, 3) : [];
    return (summary || 'No readable summary was returned. Select this turn to inspect its raw output.') +
        (refs.length ? `\nPolicies: ${refs.join('; ')}` : '');
}

// ---------------------------------------------------------------- cases

async function rrLoadCases() {
    try {
        const resp = await fetch(`${API_BASE}/api/disputes/cases`);
        rr.cases = ((await resp.json()).cases || []).sort((a, b) =>
            (a.dispute_type || '').localeCompare(b.dispute_type || '') || (a.dispute_id || '').localeCompare(b.dispute_id || ''));
        rrEl('rrCaseCount').textContent = rr.cases.length;
        rrRenderLibrary();
        if (rr.cases.length && !rr.current) rrSelectCase(rr.cases[0].order_id);
    } catch (e) {
        rrEl('rrCaseList').innerHTML = '<div class="rr-empty">Server offline — retrying… (start uvicorn on :8000)</div>';
        setTimeout(rrLoadCases, 3000);
        return;
    }
    rrLoadTraces();
}

async function rrLoadTraces() {
    try {
        const names = (await (await fetch(`${API_BASE}/api/disputes/traces`)).json()).traces || [];
        rrEl('rrTraces').innerHTML = `<option value="">${names.length ? 'Choose a saved run…' : 'No saved runs yet'}</option>` +
            names.map(n => `<option value="${rrEsc(n)}">${rrEsc(n.replace(/\.json$/, '').replace(/^(\d{8})-(\d{6})_/, '$1 $2 · '))}</option>`).join('');
    } catch (e) { /* offline: keep placeholder */ }
}

function rrRenderLibrary() {
    const q = rr.filter.toLowerCase();
    const shown = rr.cases.filter(c => !q ||
        [c.dispute_id, c.order_id, c.dispute_type, c.description, c.filed_by].join(' ').toLowerCase().includes(q));
    let html = '', group = null;
    for (const c of shown) {
        const g = (c.dispute_type || 'unknown').replace(/_/g, ' ');
        if (g !== group) { group = g; html += `<div class="rr-group">${rrEsc(g)}</div>`; }
        html += `<button class="rr-case ${rr.current === c.order_id ? 'selected' : ''}" onclick="rrSelectCase('${rrEsc(c.order_id)}')">
            <div class="rr-case-top"><span class="rr-case-id">${rrEsc(c.dispute_id || c.order_id)}</span>
                ${rrTypeBadge(c.dispute_type)}<span class="rr-case-by">${c.filed_by === 'driver' ? 'driver' : 'rider'}</span></div>
            <div class="rr-case-desc">${rrEsc(c.description)}</div></button>`;
    }
    rrEl('rrCaseList').innerHTML = html || '<div class="rr-empty">No case matches.</div>';
}

async function rrSelectCase(orderId, keepRun = false) {
    if (rr.running && !keepRun) return;
    rr.current = orderId;
    rr.detail = null;
    if (!keepRun) rrResetRun();
    rrRenderLibrary();
    rrRenderHeader();
    rrEl('rrBrief').innerHTML = '<div class="rr-empty">Loading case data…</div>';
    try {
        const resp = await fetch(`${API_BASE}/api/disputes/cases/${encodeURIComponent(orderId)}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        rr.detail = await resp.json();
    } catch (e) {
        rrEl('rrBrief').innerHTML = `<div class="rr-empty">Could not load case data (${rrEsc(e.message)}).</div>`;
        return;
    }
    rrRenderHeader();
    rrRenderBrief();
    rrRenderAll();
}

function rrCaseMeta() { return rr.cases.find(c => c.order_id === rr.current) || {}; }

// ---------------------------------------------------------------- header + brief

function rrRenderHeader() {
    const c = rrCaseMeta();
    const ticket = rr.detail?.dataset?.dispute_ticket || {};
    const status = rr.running ? ['running', `Running · ${rr.order.filter(id => rr.steps[id].status !== 'running').length} steps done`]
        : rr.result?.status === 'failed' ? ['error', 'Failed · sent to human review']
        : rr.result?.status === 'escalated_to_human' ? ['escalated', 'Escalated to human']
        : rr.result ? ['done', 'Resolved'] : ['', 'Ready'];
    rrEl('rrCaseTitle').innerHTML = `
        <h2>${rrEsc(c.dispute_id || rr.current || 'Pick a case')} ${c.dispute_type ? rrTypeBadge(c.dispute_type) : ''}</h2>
        <div class="rr-sub">${rrEsc(rr.current || '')}${ticket.filed_by ? ` · filed by ${rrEsc(ticket.filed_by)}` : ''}${
            ticket.filed_at ? ` · ${rrEsc(ticket.filed_at.replace('T', ' ').slice(0, 16))}` : ''}${
            c.source ? ` · <span title="${rrEsc(c.source)}">${rrEsc(rrClip(c.source, 48))}</span>` : ''}</div>`;
    const st = rrEl('rrStatus');
    st.className = `rr-status ${status[0]}`;
    st.textContent = status[1];
    const btn = rrEl('rrRunBtn');
    btn.disabled = rr.running || !rr.current;
    btn.textContent = rr.running ? 'Running…' : 'Run agents';
}

function rrRenderBrief() {
    const d = rr.detail?.dataset;
    if (!d) return;
    const t = d.dispute_ticket || {}, trip = d.trip_data || {}, r = d.rider_profile || {}, dr = d.driver_profile || {};
    const pol = d.cancellation_policy || d.platform_policy;
    const row = (k, v, cls = '') => v == null || v === '' ? '' : `<div class="row"><span>${rrEsc(k)}</span><span class="${cls}">${rrEsc(v)}</span></div>`;
    const hist = h => h ? `${h.total_disputes ?? 0} (${h.upheld ?? h.upheld_against ?? 0} upheld${h.upheld_against != null ? ' against' : ''})` : null;

    const tripRows = trip.cancellation_time || trip.cancellation_fee != null
        ? row('Scheduled', rrTime(trip.scheduled_time)) + row('Driver arrived', trip.driver_arrival_time ? rrTime(trip.driver_arrival_time) : 'never')
          + row('Cancelled', rrTime(trip.cancellation_time)) + row('Fee', rrMoney(trip.cancellation_fee)) + row('Reason', trip.cancellation_reason)
        : row('Pickup → drop-off', `${rrTime(trip.pickup_time)} → ${rrTime(trip.dropoff_time)}`)
          + row('Distance', trip.actual_distance_km != null ? `${trip.actual_distance_km} km (est. ${trip.estimated_distance_km})` : null)
          + row('Fare', trip.total_fare != null ? `${rrMoney(trip.total_fare)} (est. ${rrMoney(trip.estimated_fare)})` : null)
          + row('Surge', trip.fare_breakdown?.surge_multiplier ? `${trip.fare_breakdown.surge_multiplier}x` : null)
          + row('Cleaning fee', trip.cleaning_fee != null ? rrMoney(trip.cleaning_fee) : (trip.cleaning_fee_claimed != null ? `${rrMoney(trip.cleaning_fee_claimed)} claimed` : null));

    // Chat + app events merged into one timeline: exactly what the agents can see
    const tl = [
        ...(d.chat_logs || []).map(m => ({ ts: m.timestamp, kind: m.sender, label: m.type === 'call' ? `${m.sender} call` : m.sender, text: m.content })),
        ...(d.app_events || []).map(e => ({ ts: e.timestamp, kind: 'event', label: e.event_type.replace(/_/g, ' '), text: e.details })),
    ].sort((a, b) => String(a.ts).localeCompare(String(b.ts)));

    rrEl('rrBrief').innerHTML = `
        <div class="rr-complaint">“${rrEsc(t.description)}”</div>
        <div class="rr-complaint-meta">Complaint from the ${rrEsc(t.filed_by || 'reporter')} · status ${rrEsc(t.status || '—')}</div>
        <div class="rr-cards">
            <div class="rr-card"><h4>Trip</h4>
                <div class="big">${rrEsc(trip.pickup_location?.name || '—')} → ${rrEsc(trip.dropoff_location?.name || '—')}</div>${tripRows}</div>
            <div class="rr-card"><h4>Rider</h4><div class="big">${rrEsc(r.name || r.rider_id || '—')}</div>
                ${row('Trips / rating', r.total_trips != null ? `${r.total_trips} · ★ ${r.avg_rating}` : null)}
                ${row('Past disputes', hist(r.dispute_history))}
                ${row('Fraud flags', r.fraud_flags ? `${r.fraud_flags} · ${r.fraud_flag_details || ''}` : (r.fraud_flags === 0 ? 'none' : null), r.fraud_flags ? 'rr-flag' : '')}
                ${row('Pays by', r.payment_method)}</div>
            <div class="rr-card"><h4>Driver</h4><div class="big">${rrEsc(dr.name || dr.driver_id || '—')}</div>
                ${row('Vehicle', dr.vehicle)}
                ${row('Trips / rating', dr.total_trips != null ? `${dr.total_trips} · ★ ${dr.avg_rating}` : null)}
                ${row('Past disputes', hist(dr.dispute_history))}
                ${row('Fraud flags', dr.fraud_flags ? dr.fraud_flags : (dr.fraud_flags === 0 ? 'none' : null), dr.fraud_flags ? 'rr-flag' : '')}</div>
            <div class="rr-card"><h4>Evidence sent</h4>
                ${row('GPS points', (d.gps_telemetry || []).length || '0 — no GPS', (d.gps_telemetry || []).length ? '' : 'rr-flag')}
                ${row('Chat messages', (d.chat_logs || []).length)}
                ${row('App events', (d.app_events || []).length)}
                ${row('Trip policy', pol ? `${Object.keys(pol).length} rules` : 'none', pol ? '' : 'rr-flag')}
                ${row('Answer key', 'hidden from agents')}</div>
        </div>
        <details class="rr-more"><summary>Evidence timeline — chat + app events (${tl.length})</summary>
            <ul class="rr-tl">${tl.map(e => `<li><span class="time">${rrEsc(rrTime(e.ts))}</span>
                <span class="kind ${rrEsc(e.kind)}">${rrEsc(e.label)}</span><span class="txt">${rrEsc(e.text)}</span></li>`).join('')}</ul></details>
        <details class="rr-more"><summary>Exact data sent to the agents (JSON)</summary>
            <pre class="rr-json">${rrJson(d)}</pre></details>`;
}

// ---------------------------------------------------------------- run / replay

function rrResetRun() {
    rr.steps = {}; rr.order = []; rr.result = null; rr.selected = 'case'; rr.follow = true;
}

function rrSetRunning(on) {
    rr.running = on;
    rrEl('rrTraces').disabled = on;
    rrRenderHeader();
}

async function rrRun() {
    if (!rr.current || rr.running) return;
    const body = {
        order_id: rr.current,
        report_text: (rrEl('rrReport')?.value || '').trim(),
        reporter: rrEl('rrReporter')?.value || null,
    };
    rrResetRun();
    rrSetRunning(true);
    rrRenderAll();
    try {
        const resp = await fetch(`${API_BASE}/api/disputes/resolve-stream`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        });
        if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            let cut;
            while ((cut = buf.indexOf('\n\n')) >= 0) {
                const chunk = buf.slice(0, cut); buf = buf.slice(cut + 2);
                const line = chunk.split('\n').find(l => l.startsWith('data: '));
                if (line) rrHandle(JSON.parse(line.slice(6)));
            }
        }
    } catch (e) {
        showToast(`Run failed: ${e.message}`, 'error');
    } finally {
        rrSetRunning(false);
        rrRenderAll();
        rrLoadTraces();
    }
}

async function rrReplay(name) {
    if (!name || rr.running) return;
    try {
        const events = (await (await fetch(`${API_BASE}/api/disputes/traces/${encodeURIComponent(name)}`)).json()).events || [];
        const start = events.find(e => e.type === 'run_start');
        const orderId = start?.request?.order_id;
        rrResetRun();
        rrSetRunning(true);
        if (orderId && orderId !== rr.current) await rrSelectCase(orderId, true);
        rrRenderAll();
        for (const ev of events) {
            rrHandle(ev);
            if (ev.type === 'step_start' || ev.type === 'step_end') await new Promise(r => setTimeout(r, 160));
        }
    } catch (e) {
        showToast(`Replay failed: ${e.message}`, 'error');
    } finally {
        rrSetRunning(false);
        rrRenderAll();
        rrEl('rrTraces').value = '';
    }
}

function rrHandle(ev) {
    if (ev.type === 'step_start') {
        rr.steps[ev.id] = { id: ev.id, agent: ev.agent, title: ev.title, input: ev.input, output: null,
                            llm: [], retrievals: [], status: 'running', duration: null };
        rr.order.push(ev.id);
        if (rr.follow) rr.selected = ev.id;
    } else if (ev.type === 'llm_call') {
        rr.steps[ev.step_id]?.llm.push(ev);
    } else if (ev.type === 'retrieval') {
        rr.steps[ev.step_id]?.retrievals.push(ev);
    } else if (ev.type === 'step_end' || ev.type === 'step_error') {
        const s = rr.steps[ev.id];
        if (s) {
            s.status = ev.type === 'step_end' ? 'done' : 'error';
            s.output = ev.type === 'step_end' ? ev.output : { error: ev.error };
            s.duration = ev.duration_ms;
        }
    } else if (ev.type === 'result') {
        rr.result = ev.result;
        if (rr.follow) rr.selected = ev.result?.status === 'escalated_to_human' ? 'human' : (rr.selected || 'case');
    } else if (ev.type === 'error') {
        showToast(`Pipeline error: ${ev.message}`, 'error');
    }
    rrRenderAll();
}

// ---------------------------------------------------------------- step -> node mapping

function rrNodeOf(step) {
    if (/^Round /.test(step.title)) return 'debate';
    return { Collector: 'collector', Classifier: 'classifier', Passenger: 'passenger', Driver: 'driver',
             Policy: 'policy', Arbitrator: 'arbitrator', Fairness: 'fairness', Executor: 'executor' }[step.agent] || 'debate';
}
function rrStepsOf(node) { return rr.order.map(id => rr.steps[id]).filter(s => rrNodeOf(s) === node); }
// A failed run is also routed to human review by the workflow
function rrEscalated() { return ['escalated_to_human', 'failed'].includes(rr.result?.status); }
// Which node sent the case to human review (for the escalation edge)
function rrEscalatedFrom() {
    if (!rrEscalated()) return null;
    return rrStepsOf('fairness').length ? 'fairness' : 'classifier';
}

function rrNodeStatus(node) {
    if (node === 'case') return rr.detail ? 'done' : 'idle';
    if (node === 'human') return rrEscalated() ? 'done' : 'hidden';
    const steps = rrStepsOf(node);
    if (!steps.length) {
        return rr.result && !rr.running ? 'skipped' : 'idle';
    }
    if (steps.some(s => s.status === 'error')) return 'error';
    if (steps.some(s => s.status === 'running')) return 'running';
    return 'done';
}

function rrNodeSummary(node) {
    const d = rr.detail?.dataset;
    if (node === 'case') {
        if (!d) return '';
        return `${(d.gps_telemetry || []).length} GPS · ${(d.chat_logs || []).length} chat · ${(d.app_events || []).length} events`;
    }
    if (node === 'human') return rrEscalated() ? rrClip(rrEscalatedFrom() === 'classifier'
        ? rr.result.classification?.reasoning || rr.result.reason : rr.result.reason, 110) : '';
    const steps = rrStepsOf(node);
    const s = steps[0];
    if (!s || s.status === 'running' && node !== 'debate') return s ? 'Working…' : '';
    const issue = steps.map(rrStepIssue).find(Boolean);
    if (issue) return issue.short;
    const o = rrParse(s.output) || {};
    switch (node) {
        case 'collector': {
            const miss = o.data_completeness?.missing || [];
            return miss.length ? `Missing: ${miss.join(', ')}` : 'All 8 data sources found';
        }
        case 'classifier':
            return `${(o.dispute_type || 'unknown').replace(/_/g, ' ')} · ${o.urgency || '?'} · ${Math.round((o.confidence || 0) * 100)}%${o.requires_human ? ' · human' : ''}`;
        case 'passenger': case 'driver':
            return typeof o === 'string' ? rrClip(o, 120) : rrClip(o.stance || o.reasoning || '', 120);
        case 'policy': {
            const n = s.retrievals.reduce((a, r) => a + r.clauses.length, 0);
            const yn = v => v === true ? '✓' : v === false ? '✗' : '?';
            return `Rider ${yn(o.passenger_compliant)} · Driver ${yn(o.driver_compliant)} · ${n} clauses`;
        }
        case 'debate': return `${steps.filter(x => x.status === 'done').length} / ${steps.length} turns`;
        case 'fairness': {
            const n = (o.issues || []).length;
            return `${(o.recommendation || '?').replace(/_/g, ' ')} · ${o.fairness_passed ? 'passed' : 'not passed'} · ${n} issue${n === 1 ? '' : 's'}`;
        }
        case 'arbitrator':
            return `${(o.verdict || '?').replace(/_/g, ' ')} · ${Math.round((o.confidence || 0) * 100)}%${o.refund_amount != null ? ` · ${rrMoney(o.refund_amount)}` : ''}`;
        case 'executor': {
            const n = (o.actions_taken || []).length;
            return o.executed === false ? 'Held for human review' : `${n} action${n === 1 ? '' : 's'} applied`;
        }
    }
    return '';
}

function rrNodeMeta(node) {
    const steps = rrStepsOf(node);
    if (!steps.length) return '';
    const ms = steps.reduce((a, s) => a + (s.duration || 0), 0);
    const llm = steps.reduce((a, s) => a + s.llm.length, 0);
    return `${(ms / 1000).toFixed(1)}s${llm ? ` · ${llm} LLM` : ''}`;
}

// ---------------------------------------------------------------- graph

function rrRenderGraph() {
    const g = rrEl('rrGraph');
    const nodesHtml = Object.entries(RR_NODES).map(([key, n]) => {
        const st = rrNodeStatus(key);
        if (st === 'hidden') return '';
        const selStep = rr.steps[rr.selected];
        const isSel = rr.selected === key || (selStep && rrNodeOf(selStep) === key);
        let extra = '';
        if (key === 'debate') {
            extra = `<div class="rr-pills">${rrStepsOf('debate').map(s => {
                const side = s.agent === 'Passenger' ? 'p' : 'd';
                const label = s.title.replace(/^Round (\d+).*/, `R$1 ${side === 'p' ? 'P' : 'D'}`);
                return `<span class="rr-pill ${side} ${s.status} ${rr.selected === s.id ? 'selected' : ''}" role="button" tabindex="0"
                    onclick="event.stopPropagation(); rrSelect('${s.id}')">${rrEsc(label)}</span>`;
            }).join('')}</div>`;
        }
        return `<button class="rr-node ${st} ${isSel ? 'selected' : ''}" data-node="${key}"
                    style="--c:${n.color}; grid-column:${n.col}; grid-row:${n.row}; ${key === 'debate' ? 'align-self:center;' : ''}"
                    onclick="rrSelect('${key}')">
                <div class="rr-node-top"><span class="rr-dot"></span><span class="rr-node-name">${rrEsc(n.name)}</span>
                    <span class="rr-node-meta">${rrEsc(rrNodeMeta(key))}</span></div>
                <div class="rr-node-role">${rrEsc(n.role)}</div>
                <div class="rr-node-sum">${rrEsc(rrNodeSummary(key))}</div>${extra}
            </button>`;
    }).join('');
    g.innerHTML = `<svg class="rr-edges" id="rrEdges" aria-hidden="true"></svg>${nodesHtml}` +
        '<svg class="rr-edges labels" id="rrEdgeLabels" aria-hidden="true"></svg>';
    requestAnimationFrame(rrDrawEdges);
}

function rrDrawEdges() {
    const g = rrEl('rrGraph'), svg = rrEl('rrEdges');
    if (!g || !svg) return;
    const box = g.getBoundingClientRect();
    const rect = key => {
        const el = g.querySelector(`[data-node="${key}"]`);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { l: r.left - box.left, r: r.right - box.left, t: r.top - box.top, b: r.bottom - box.top,
                 cy: (r.top + r.bottom) / 2 - box.top, cx: (r.left + r.right) / 2 - box.left };
    };
    let paths = '', labels = '';
    for (const [from, to, label] of RR_EDGES) {
        const a = rect(from), b = rect(to);
        if (!a || !b) continue;
        const sf = rrNodeStatus(from), stt = rrNodeStatus(to);
        let cls = stt === 'running' ? 'active' : (stt === 'done' || stt === 'error') && sf !== 'idle' ? 'done'
                : stt === 'skipped' ? 'skipped' : '';
        if (to === 'human') {
            if (from !== rrEscalatedFrom()) continue;
            cls = 'escalate';
        }
        // Source directly above the human-review box: straight drop onto its top
        if (to === 'human' && a.cx > b.l && a.cx < b.r) {
            const x = a.cx, ya = a.b, yb2 = b.t - 6;
            paths += `<path class="rr-edge ${cls}" d="M${x},${ya} L${x},${yb2}"/>` +
                     `<path class="rr-arrow ${cls}" d="M${x - 4},${yb2} L${x},${yb2 + 6} L${x + 4},${yb2} Z"/>`;
            labels += `<text class="rr-edge-label ${cls}" x="${x + 6}" y="${(ya + yb2) / 2 + 4}" text-anchor="start">${rrEsc(label)}</text>`;
            continue;
        }
        let x1 = a.r, y1 = a.cy, x2 = b.l - 6, y2 = b.cy;
        if (to === 'human') { x1 = a.cx; y1 = a.b; x2 = b.l - 6; y2 = b.cy; }
        const dx = Math.max(24, (x2 - x1) / 2);
        const blocker = Object.keys(RR_NODES).map(rect).find(r => r && r.l > x1 + 4 && r.r < x2 - 4 && r.t < y1 && r.b > y1);
        let d, yb = null;
        if (to === 'human') d = `M${x1},${y1} C${x1},${y2} ${x1 + 20},${y2} ${x2},${y2}`;
        else if (blocker) {
            yb = blocker.b + 16;
            d = `M${x1},${y1} C${x1 + 24},${y1} ${x1 + 14},${yb} ${x1 + 40},${yb} L${x2 - 40},${yb} C${x2 - 14},${yb} ${x2 - 24},${y2} ${x2},${y2}`;
        } else d = `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`;
        paths += `<path class="rr-edge ${cls}" d="${d}"/>` +
                 `<path class="rr-arrow ${cls}" d="M${x2},${y2 - 4} L${x2 + 6},${y2} L${x2},${y2 + 4} Z"/>`;
        const mx = to === 'human' ? x2 - 50 : (x1 + x2) / 2;
        const my = to === 'human' ? y2 - 6 : yb != null ? yb - 5 : (y1 + y2) / 2 - 5;
        labels += `<text class="rr-edge-label ${cls}" x="${mx}" y="${my}" text-anchor="middle">${rrEsc(label)}</text>`;
    }
    svg.innerHTML = paths;
    rrEl('rrEdgeLabels').innerHTML = labels;
}

// ---------------------------------------------------------------- inspector

function rrSelect(key) {
    rr.selected = key;
    rr.follow = false;
    rrRenderGraph();
    rrRenderInspector();
    rrRenderDebate();
}

function rrRenderInspector() {
    const el = rrEl('rrInspector');
    const key = rr.selected;
    const step = rr.steps[key];
    const nodeKey = step ? rrNodeOf(step) : key;
    const node = RR_NODES[nodeKey] || RR_NODES.case;
    // A node with several steps (debate) shows the latest one unless a round was picked
    const s = step || rrStepsOf(nodeKey).slice(-1)[0];

    const io = `<div class="rr-sec"><h5>Connections</h5><div class="rr-io" style="--c:${node.color}">
        <div><div class="rr-hint">Receives</div><ul>${node.receives.map(x => `<li>${rrEsc(x)}</li>`).join('')}</ul></div>
        <div><div class="rr-hint">Sends</div><ul>${node.sends.map(x => `<li>${rrEsc(x)}</li>`).join('')}</ul></div></div></div>`;
    let head = `<div class="rr-insp-head" style="--c:${node.color}"><h2>${rrEsc(node.name)}</h2>
        <span class="rr-sub">${rrEsc(s ? s.title : node.role)}${s && s.status !== 'running' && s.duration != null
            ? ` · ${(s.duration / 1000).toFixed(2)}s` : ''}${s?.status === 'running' ? ' · running…' : ''}</span></div>`;

    if (nodeKey === 'case') {
        el.innerHTML = head + io + (rr.detail
            ? `<div class="rr-sec"><h5>What goes in</h5><div class="rr-prose">The case file is loaded from <b>${rrEsc(rrCaseMeta().source || '')}</b>. The answer key (expected_outcome) is removed before any agent sees it. The full payload is under “Exact data sent to the agents” in the case brief above.</div></div>`
            : '<div class="rr-empty">Loading…</div>');
        return;
    }
    if (nodeKey === 'human') {
        const c = rr.result?.classification || {};
        const f = rr.result?.fairness;
        el.innerHTML = head + io + (rrEscalated() ? `<div class="rr-sec"><h5>Why it was escalated</h5><div class="rr-kv">
            <div class="k">from</div><div>${rrEsc(RR_NODES[rrEscalatedFrom()]?.name || '?')}${rr.result.status === 'failed' ? ' (a step failed)' : ''}</div>
            <div class="k">reason</div><div class="rr-prose">${rrEsc(rr.result.reason)}</div>
            ${f ? `<div class="k">fairness</div><div class="rr-prose">${rrEsc((f.recommendation || '').replace(/_/g, ' '))}: ${rrEsc(f.reason)}</div>`
                : `<div class="k">urgency</div><div>${rrEsc(c.urgency)}</div>
            <div class="k">classifier</div><div class="rr-prose">${rrEsc(c.reasoning)}</div>`}</div></div>`
            : '<div class="rr-empty">Not escalated in this run.</div>');
        return;
    }
    if (!s) {
        el.innerHTML = head + io + `<div class="rr-empty">${rrEscalated() ? 'Skipped — the case went straight to human review.'
            : 'Not run yet. Press <b>Run agents</b> or replay a saved run.'}</div>`;
        return;
    }

    const out = rrParse(s.output);
    const issue = rrStepIssue(s);
    let html = head + io;
    html += `<div class="rr-sec"><h5>Reasoning</h5>${s.status === 'running'
        ? '<div class="rr-empty" style="padding:0">Agent is working…</div>'
        : issue ? `<div class="rr-prose rr-issue">${rrEsc(issue.message)}</div>`
        : rrReasoning(s.agent, out)}</div>`;

    const clauses = s.retrievals.flatMap(r => r.clauses);
    if (s.retrievals.length) {
        html += `<div class="rr-sec"><h5>Policy clauses retrieved (RAG · query type “${rrEsc(s.retrievals[0].dispute_type || 'none')}”)</h5>
            <div class="rr-clauses">${clauses.map(c => `<details class="rr-clause"><summary>
                <span><span class="src">${rrEsc(c.source)}</span> › <span class="sec">${rrEsc(c.section || '—')}</span></span>
                <span class="rr-sim" title="similarity ${c.similarity}"><div style="width:${Math.max(4, Math.min(100, (c.similarity || 0) * 150))}%"></div></span>
                </summary><div class="excerpt">${rrEsc(c.excerpt)}</div></details>`).join('') || '<div class="rr-hint">No clauses returned.</div>'}</div></div>`;
    }
    if (/^Round /.test(s.title) && s.input?.rebutting) {
        html += `<div class="rr-sec"><h5>Responding to</h5><div class="rr-prose" style="color:var(--on-dark-muted)">${rrEsc(rrClip(
            typeof s.input.rebutting === 'string' ? s.input.rebutting : JSON.stringify(s.input.rebutting), 700))}</div></div>`;
    }
    html += `<div class="rr-sec"><h5>Raw data</h5>
        <details class="rr-details"><summary>Input given to this step</summary><pre class="rr-json">${rrJson(rrParse(s.input))}</pre></details>
        ${s.status !== 'running' ? `<details class="rr-details"><summary>Exact output</summary><pre class="rr-json">${rrJson(out)}</pre></details>` : ''}
        ${s.llm.map((c, i) => `<details class="rr-details"><summary>LLM call ${i + 1}${c.error ? ' — <span class="rr-bad">failed</span>' : ''}
            <span class="rr-node-meta">${(c.duration_ms / 1000).toFixed(2)}s</span></summary>
            <div class="rr-label">Prompt sent</div><pre class="rr-json">${rrEsc(c.prompt || '')}</pre>
            <div class="rr-label">${c.error ? 'Error' : 'Raw reply'}</div><pre class="rr-json">${rrEsc(c.error || c.response || '')}</pre></details>`).join('')}
        ${!s.llm.length && s.status !== 'running' ? '<div class="rr-hint" style="margin-top:6px">No LLM call — this step is deterministic code.</div>' : ''}
    </div>`;
    el.innerHTML = html;
}

function rrReasoning(agent, out) {
    if (out == null) return '<div class="rr-hint">No output.</div>';
    if (typeof out === 'string') return `<div class="rr-prose">${rrEsc(out)}</div>`;
    if (agent === 'Collector') {
        const dc = out.data_completeness || {};
        const fields = ['trip', 'payment', 'chat_log', 'gps_trace', 'rider_profile', 'driver_profile', 'app_events', 'platform_policy'];
        const count = v => Array.isArray(v) ? ` (${v.length})` : '';
        return `<div class="rr-kv">
            <div class="k">Case</div><div>${rrEsc(out.dispute_id)} · ${rrEsc(out.type || 'type unknown')} · filed by ${rrEsc(out.reporter)}</div>
            <div class="k">Source</div><div>${rrEsc(dc.source || 'not found on platform')}</div>
            <div class="k">Data found</div><div>${fields.map(f =>
                `<span class="rr-chip ${out[f] != null ? 'ok' : 'miss'}">${f}${count(out[f])}</span>`).join('')}</div></div>`;
    }
    if (agent === 'Executor') {
        const actions = out.actions_taken || [];
        return `<div class="rr-kv"><div class="k">Actions</div><div>${actions.length
            ? `<ul>${actions.map(a => `<li>${rrEsc(typeof a === 'string' ? a : JSON.stringify(a))}</li>`).join('')}</ul>`
            : 'None — no refund, compensation or penalty needed.'}</div>
            <div class="k">Executed</div><div>${out.executed === false ? 'No — waiting for human review' : 'Yes (simulated)'}</div></div>`;
    }
    const rows = RR_REASONING_KEYS.filter(k => out[k] !== undefined && out[k] !== null && !(Array.isArray(out[k]) && !out[k].length));
    if (!rows.length) return `<pre class="rr-json">${rrJson(out)}</pre>`;
    return `<div class="rr-kv">${rows.map(k => {
        let v = out[k];
        if (k === 'confidence' && typeof v === 'number') v = `${Math.round(v * 100)}%`;
        const body = Array.isArray(v)
            ? `<ul>${v.map(x => `<li>${rrEsc(typeof x === 'string' ? x : JSON.stringify(x))}</li>`).join('')}</ul>`
            : `<div class="rr-prose">${rrEsc(String(v))}</div>`;
        return `<div class="k">${rrEsc(k.replace(/_/g, ' '))}</div><div>${body}</div>`;
    }).join('')}</div>`;
}

// ---------------------------------------------------------------- debate transcript

function rrRenderDebate() {
    const el = rrEl('rrDebate');
    const turns = rr.order.map(id => rr.steps[id]).filter(s => ['Passenger', 'Driver', 'Policy'].includes(s.agent));
    if (!turns.length) {
        el.innerHTML = `<div class="rr-empty">${rrEscalated() ? 'No debate — the case was escalated to a human.'
            : 'The advocates’ openings, the policy check and every rebuttal appear here as a conversation.'}</div>`;
        return;
    }
    let lastOther = { Passenger: 'Driver opening', Driver: 'Passenger rebuttal' };
    const quotaIssue = rrRunIssue();
    el.innerHTML = (quotaIssue ? `<div class="rr-run-alert">${rrEsc(quotaIssue.message)} Earlier completed turns remain visible below.</div>` : '') +
    turns.map(s => {
        const isRound = /^Round /.test(s.title);
        const cls = s.agent === 'Passenger' ? 'p' : s.agent === 'Driver' ? 'd' : 'pol';
        const issue = rrStepIssue(s);
        const text = s.status === 'running' ? '' : issue ? issue.message : rrDebateText(s.output, s.agent);
        const reply = isRound ? `↳ replying to ${s.agent === 'Passenger' ? lastOther.Passenger : lastOther.Driver}` : '';
        if (isRound) {
            const r = s.title.match(/^Round (\d+)/)[1];
            if (s.agent === 'Passenger') lastOther.Driver = `Passenger R${r}`;
            else lastOther.Passenger = `Driver R${r}`;
        }
        const who = s.agent === 'Policy' ? 'Policy check' : `${s.agent} ${isRound ? s.title.replace(/:.*/, '') : 'opening'}`;
        return `<button class="rr-bubble ${cls} ${issue ? 'failed' : ''} ${rr.selected === s.id ? 'selected' : ''} ${s.status === 'running' ? 'typing' : ''}"
                    onclick="rrSelect('${s.id}')">
            ${reply ? `<div class="reply">${rrEsc(reply)}</div>` : ''}
            <div class="who">${rrEsc(who)}<span>${issue ? 'incomplete' : s.status === 'running' ? 'thinking' : ((s.duration || 0) / 1000).toFixed(1) + 's'}</span></div>
            <div class="txt">${rrEsc(rrClip(text, 900))}</div></button>`;
    }).join('');
    const sel = el.querySelector('.rr-bubble.selected');
    if (sel && rr.follow) sel.scrollIntoView({ block: 'nearest' });
}

// ---------------------------------------------------------------- verdict vs answer key

function rrRenderVerdict() {
    const el = rrEl('rrVerdict');
    const res = rr.result;
    if (!res) { el.hidden = true; return; }
    const quotaIssue = rrRunIssue();
    if (quotaIssue) {
        el.innerHTML = `<div class="rr-verdict-main"><span class="rr-pill-lg escalated">Incomplete</span>
            <div class="rr-verdict-text">${rrEsc(quotaIssue.message)} Review completed turns above and retry when the provider quota is available.</div></div>`;
        el.hidden = false;
        return;
    }
    const exp = rr.detail?.expected_outcome;
    let main;
    const escalated = res.status === 'escalated_to_human';
    const v = res.verdict || {};
    if (escalated) {
        main = `<span class="rr-pill-lg escalated">Escalated</span>
            <div><div class="rr-verdict-text">${rrEsc(res.reason)}</div>
            <div class="rr-verdict-facts"><span class="rr-fact">Urgency <b>${rrEsc(res.classification?.urgency)}</b></span>${
                v.verdict ? `<span class="rr-fact">Proposed <b>${rrEsc(v.verdict.replace(/_/g, ' '))}</b></span>
                <span class="rr-fact">Refund <b>${v.refund_amount != null ? rrMoney(v.refund_amount) : 'none'}</b></span>` : ''}${
                res.fairness ? `<span class="rr-fact">Fairness <b>${rrEsc((res.fairness.recommendation || '').replace(/_/g, ' '))}</b></span>` : ''
            }</div></div><div></div>`;
    } else {
        const conf = Math.round((v.confidence || 0) * 100);
        const facts = [
            ['Refund', v.refund_amount != null ? rrMoney(v.refund_amount) : 'none'],
            v.compensation ? ['Compensation', v.compensation] : null,
            v.driver_penalty ? ['Driver', v.driver_penalty] : null,
            v.human_review_needed ? ['Review', 'human required'] : v.escalation_recommended ? ['Review', 'flagged for audit'] : null,
            (v.policy_references || []).length ? ['Cites', v.policy_references.join(', ')] : ['Cites', 'no policy'],
        ].filter(Boolean);
        main = `<span class="rr-pill-lg ${rrEsc(v.verdict || '')}">${rrEsc((v.verdict || '?').replace(/_/g, ' '))}</span>
            <div><div class="rr-verdict-text">${rrEsc(v.rationale || '')}</div>
            <div class="rr-verdict-facts">${facts.map(([k, x]) => `<span class="rr-fact">${rrEsc(k)} <b>${rrEsc(x)}</b></span>`).join('')}</div></div>
            <div class="rr-conf"><div class="num">${conf}%</div><div class="lbl">confidence</div><div class="bar"><div style="width:${conf}%"></div></div></div>`;
    }

    let key = '<div class="rr-key"><h4>Answer key</h4><div class="rr-hint">This case has no machine-readable expected outcome.</div></div>';
    if (exp) {
        const gotHuman = escalated || !!v.human_review_needed;
        const mark = ok => ok == null ? '<span class="rr-na">n/a</span>' : ok ? '<span class="rr-ok">✓</span>' : '<span class="rr-bad">✗</span>';
        const vOk = exp.verdict == null ? null : !escalated && v.verdict === exp.verdict;
        const expRefund = exp.refund_amount;
        const rOk = expRefund == null || escalated ? null : Math.abs((v.refund_amount || 0) - expRefund) < 0.01;
        key = `<div class="rr-key"><h4>Answer key · hidden from agents</h4>
            <div class="row"><span>Verdict</span><span>${rrEsc(exp.verdict ? exp.verdict.replace(/_/g, ' ') : 'human review')}</span>${mark(vOk)}</div>
            <div class="row"><span>Refund</span><span>${expRefund == null ? '—' : rrMoney(expRefund)}</span>${mark(rOk)}</div>
            <div class="row"><span>Human review</span><span>${exp.requires_human_review ? 'yes' : 'no'}</span>${mark(gotHuman === !!exp.requires_human_review)}</div>
            <div class="why">${rrEsc(exp.reason)}</div></div>`;
    }
    el.innerHTML = `<div class="rr-verdict-main">${main}</div>${key}`;
    el.hidden = false;
}

// ---------------------------------------------------------------- render all

function rrRenderAll() {
    rrRenderHeader();
    rrRenderGraph();
    rrRenderVerdict();
    rrRenderInspector();
    rrRenderDebate();
}

window.addEventListener('resize', () => requestAnimationFrame(rrDrawEdges));
rrEl('rrFilter').addEventListener('input', e => { rr.filter = e.target.value; rrRenderLibrary(); });
rrEl('rrTraces').addEventListener('change', e => rrReplay(e.target.value));
rrRenderGraph();
rrLoadCases();