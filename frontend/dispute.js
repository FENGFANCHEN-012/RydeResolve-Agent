// ============================================================
// Dispute Resolution tab
// Pick a mock case -> see exactly what data is sent -> run the agents
// (POST /api/disputes/resolve-stream, SSE) or replay a saved run ->
// watch each agent in the flow graph, inspect its reasoning, retrieved
// policy clauses, input/output and raw LLM calls, and compare the
// verdict with the case's answer key.
// Relies on API_BASE and showToast() from index.html.
// ============================================================

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
                  sends: ['Dispute type & urgency → Case Brief', 'P0 → human review, skipping the debate'] },
    casebrief:  { name: 'Case Brief', role: 'Shared dossier (RAG, no LLM)', color: 'var(--agent-casebrief)', col: 3, row: 1,
                  receives: ['Classification', 'Collector findings', "This trip's platform rules", 'App events', 'Policy index (one search)'],
                  sends: ['Facts, conflicts, gaps, case rules, timeline, clauses → every agent'] },
    fraud:      { name: 'Fraud', role: 'Risk check (code rules)', color: 'var(--agent-fraud)', col: 3, row: 3,
                  receives: ["Filer's history", 'Confirmed flags', 'Claim evidence times', 'Pair history', 'Chat log'],
                  sends: ['Risk report → Arbitrator & Fairness only (never the advocates)', 'HIGH → human review via Fairness'] },
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
    ['classifier', 'casebrief', 'type'],
    ['casebrief', 'passenger', 'brief'],
    ['casebrief', 'policy', 'brief'],
    ['casebrief', 'driver', 'brief'],
    ['passenger', 'debate', 'opening'],
    ['driver', 'debate', 'opening'],
    ['casebrief', 'fraud', 'brief'],
    ['fraud', 'arbitrator', 'risk'],
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
    'recommendation', 'fairness_passed', 'reason', 'issues', 'level', 'summary', 'signals',
];

const rr = {
    cases: [], filter: '', current: null, detail: null,
    steps: {}, order: [], result: null, running: false, selected: 'case', follow: true,
    selection: 0, loading: false, loadError: null, failure: null, finished: false,
    request: null, saveWarning: null, clock: null, replaying: false, replayTime: null,
};

const rrEl = id => document.getElementById(id);

function rrEsc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}
function rrTypeBadge(type) {
    const t = type || 'unknown';
    return `<span class="rr-type">${rrEsc(t.replace(/_/g, ' '))}</span>`;
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

// Agent prose: escape, then render **bold** and shrink rule ids (platform_policy.x) into quiet code tags
const RR_RULE_RE = /\b((?:platform|trip|driver|rider|ryde)_policy\.[a-z0-9_]+)(\s*=\s*[\w.$]+)?/gi;
function rrRich(text) {
    return rrEsc(text)
        .replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>')
        .replace(RR_RULE_RE, (m, id, val) => `<code class="rr-rule" title="${id}">${rrRuleName(id)}${val ? rrEsc(val.replace(/\s+/g, ' ')) : ''}</code>`);
}
// "platform_policy.free_cancellation_within_min_of_match" -> "free cancellation within min of match"
function rrRuleName(id) { return String(id).replace(/^[a-z_]+_policy\./i, '').replace(/_/g, ' '); }
function rrRuleChips(refs) {
    return refs.map(r => /^[a-z]+_policy\./i.test(r)
        ? `<span class="rr-cite" title="${rrEsc(r)}">${rrEsc(rrRuleName(r))}</span>`
        : `<span class="rr-cite doc">${rrEsc(r)}</span>`).join('');
}

// The trace keeps full provider errors under Raw data. Summaries must not
// mistake a quota fallback for an agent's analysis or a valid ruling.
function rrStepIssue(step) {
    if (!step || step.status === 'running') return null;
    const out = rrParse(step.output);
    // A successful retry/fallback is retained alongside earlier errors in the trace.
    const lastCall = (step.llm || []).at(-1);
    if (step.status === 'done' && lastCall && !lastCall.error &&
            typeof lastCall.response === 'string' && lastCall.response.trim() &&
            out && !out.error && !/LLM call failed|could not be generated automatically/i.test(
                typeof out === 'string' ? out : out.reasoning || out.reason || '')) return null;
    const details = [
        ...(step.llm || []).map(call => call.error),
        step.error,
        typeof out === 'string' ? out : out?.error,
        out?.reasoning, out?.reason,
    ].filter(value => typeof value === 'string').join(' ');
    if (/request too large|413.*tokens per minute/i.test(details)) {
        return { kind: 'capacity', short: 'Case exceeds provider capacity',
            message: 'The AI service could not accept the full case. No completed automated decision is available; this run requires manual review.' };
    }
    if (/token_quota_exceeded/i.test(details)) {
        return { kind: 'daily', short: 'Daily token quota reached',
            message: 'The provider’s daily token quota was reached. This review has no reliable completed verdict.' };
    }
    if (/tokens per day|TPD/i.test(details) && /rate_limit_exceeded|429/i.test(details)) {
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
    return issues.find(issue => issue.kind === 'daily') || issues[0] || null;
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
        const resp = await apiFetch(`${API_BASE}/api/disputes/cases`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
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
        const resp = await apiFetch(`${API_BASE}/api/disputes/traces`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const names = (await resp.json()).traces || [];
        rrEl('rrTraces').innerHTML = `<option value="">${names.length ? 'Choose a saved run…' : 'No saved runs yet'}</option>` +
            names.map(n => `<option value="${rrEsc(n)}">${rrEsc(n.replace(/\.json$/, '').replace(/^(\d{8})-(\d{6})_/, '$1 $2 · '))}</option>`).join('');
    } catch (e) {
        rrEl('rrTraces').innerHTML = '<option value="">Saved runs unavailable — check server readiness</option>';
    }
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
    const selection = ++rr.selection;
    rr.current = orderId;
    rr.detail = null;
    rr.loading = true; rr.loadError = null;
    if (!keepRun) rrResetRun();
    rrRenderLibrary();
    rrRenderHeader();
    rrEl('rrBrief').innerHTML = '<div class="rr-empty">Loading case data…</div>';
    try {
        const resp = await apiFetch(`${API_BASE}/api/disputes/cases/${encodeURIComponent(orderId)}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const detail = await resp.json();
        if (selection !== rr.selection) return;
        rr.detail = detail;
    } catch (e) {
        if (selection !== rr.selection) return;
        rr.loading = false; rr.loadError = e.message;
        rrEl('rrBrief').innerHTML = `<div class="rr-empty">Could not load case data (${rrEsc(e.message)}).</div>`;
        rrRenderAll();
        return;
    }
    rr.loading = false;
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
        : rr.loading ? ['', 'Loading case…']
        : rr.loadError ? ['error', 'Case unavailable']
        : rr.failure ? ['error', 'Incomplete · retry required']
        : rrRunIssue() ? ['error', rrRunIssue().kind === 'daily' ? 'Incomplete · quota reached' : 'Incomplete · review error']
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
    btn.disabled = rr.running || rr.loading || !rr.current || !rr.detail?.dataset;
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
        ...(d.chat_logs || []).map((m, i) => ({ ts: m.timestamp, kind: m.sender, label: m.type === 'call' ? `${m.sender} call` : m.sender, text: m.content,
            tone: rr.toneFor === d ? rr.tone[`chat_log[${i}]`] : null })),
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
                ${row('Photos', (d.evidence || []).length || null)}
                ${row('Trip policy', pol ? `${Object.keys(pol).length} rules` : 'none', pol ? '' : 'rr-flag')}
                ${row('Answer key', 'hidden from agents')}</div>
        </div>
        ${rrPhotos(d.evidence || [], true)}
        <details class="rr-more"><summary>Evidence timeline — chat + app events (${tl.length})</summary>
            <ul class="rr-tl">${tl.map(e => `<li><span class="time">${rrEsc(rrTime(e.ts))}</span>
                <span class="kind ${rrEsc(e.kind)}">${rrEsc(e.label)}</span><span class="txt">${rrEsc(e.text)}${rrToneTags(e.tone)}</span></li>`).join('')}</ul>
            <div class="rr-tone-note">Tone tags come from code word lists. Reviewers see them and they shape notice wording; they never change a ruling.</div></details>
        <details class="rr-more"><summary>Exact data sent to the agents (JSON)</summary>
            <pre class="rr-json">${rrJson(d)}</pre></details>`;
    if (rr.toneFor !== d && (d.chat_logs || []).length) rrLoadTone(d);
}

// Tone of each chat message (D52), computed by code on the server; shown next to the message
async function rrLoadTone(d) {
    rr.toneFor = d; rr.tone = {};
    try {
        const resp = await apiFetch(`${API_BASE}/api/chat-signals`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chat_log: d.chat_logs || [] }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const sig = await resp.json();
        if (rr.detail?.dataset !== d) return;  // another case was opened meanwhile
        for (const m of sig.messages || []) rr.tone[m.source] = m;
        rrRenderBrief();
    } catch (err) {
        console.warn('Chat tone unavailable', err);
    }
}

function rrToneTags(t) {
    if (!t) return '';
    const tags = [...(t.tone && t.tone !== 'calm' ? [t.tone] : []), ...(t.events || [])];
    return tags.map(x => ` <span class="rr-tone ${rrEsc(x)}">${rrEsc(x)}</span>`).join('');
}

// ---------------------------------------------------------------- run / replay

function rrResetRun() {
    rrStopClock();
    rr.steps = {}; rr.order = []; rr.result = null; rr.selected = 'case'; rr.follow = true;
    rr.failure = null; rr.finished = false; rr.request = null; rr.saveWarning = null;
    rr.replaying = false; rr.replayTime = null;
}

function rrSetRunning(on) {
    if (!on) rrStopClock();
    rr.running = on;
    if (on && !rr.replaying && rr.clock == null) rr.clock = setInterval(rrRefreshElapsed, 100);
    rrEl('rrTraces').disabled = on;
    rrRenderHeader();
}

function rrStepElapsed(s, now = performance.now()) {
    if (s.duration != null) return s.duration;
    if (rr.replaying) return s.startedTs == null || rr.replayTime == null
        ? 0 : Math.max(0, rr.replayTime - s.startedTs);
    return s.startedAt == null ? 0 : Math.max(0, (s.stoppedAt ?? now) - s.startedAt);
}

function rrStopClock() {
    if (rr.clock != null) clearInterval(rr.clock);
    rr.clock = null;
    const now = performance.now();
    for (const s of Object.values(rr.steps)) {
        if (s.status === 'running' && s.stoppedAt == null) s.stoppedAt = now;
    }
}

function rrRefreshElapsed() {
    // Update text only: preserve focus, expanded evidence, and the user's scroll position.
    for (const el of document.querySelectorAll('[data-rr-node-time]')) {
        const node = el.dataset.rrNodeTime;
        if (rrStepsOf(node).some(s => s.status === 'running')) el.textContent = rrNodeMeta(node);
    }
    for (const el of document.querySelectorAll('[data-rr-step-time]')) {
        const s = rr.steps[el.dataset.rrStepTime];
        if (s?.status === 'running') el.textContent = `${(rrStepElapsed(s) / 1000).toFixed(1)}s`;
    }
}

async function rrRun() {
    if (!rr.current || !rr.detail?.dataset || rr.loading || rr.running) return;
    const body = {
        order_id: rr.current,
        report_text: (rrEl('rrReport')?.value || '').trim(),
        reporter: rrEl('rrReporter')?.value || null,
    };
    rrResetRun();
    rr.request = body;
    rrSetRunning(true);
    rrRenderAll();
    let reader;
    try {
        const resp = await apiFetch(`${API_BASE}/api/disputes/resolve-stream`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
            signal: AbortSignal.timeout(900000),
        });
        if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
        reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        while (true) {
            const { value, done } = await rrReadStream(reader);
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            let cut;
            while ((cut = buf.indexOf('\n\n')) >= 0) {
                const chunk = buf.slice(0, cut); buf = buf.slice(cut + 2);
                const line = chunk.split('\n').find(l => l.startsWith('data: '));
                if (line) rrHandle(JSON.parse(line.slice(6)));
            }
        }
        if (!rr.finished || (!rr.result && !rr.failure)) {
            throw new Error('The connection ended before the review completed. Retry the case.');
        }
    } catch (e) {
        if (reader) await reader.cancel().catch(() => {});
        rr.failure = e.message;
        showToast(`Run failed: ${e.message}`, 'error');
    } finally {
        rrSetRunning(false);
        rrRenderAll();
        rrLoadTraces();
    }
}

async function rrReadStream(reader) {
    let timer;
    try {
        return await Promise.race([reader.read(), new Promise((_, reject) => {
            timer = setTimeout(() => {
                reader.cancel().catch(() => {});
                reject(new Error('No response from the server. The review is incomplete.'));
            }, 90000);
        })]);
    } finally { clearTimeout(timer); }
}

async function rrReplay(name) {
    if (!name || rr.running) return;
    try {
        const resp = await apiFetch(`${API_BASE}/api/disputes/traces/${encodeURIComponent(name)}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const events = (await resp.json()).events || [];
        const start = events.find(e => e.type === 'run_start');
        const orderId = start?.request?.order_id;
        rrResetRun();
        rr.replaying = true;
        rr.request = start?.request || null;
        rrSetRunning(true);
        if (orderId && orderId !== rr.current) await rrSelectCase(orderId, true);
        rrRenderAll();
        for (const ev of events) {
            rrHandle(ev);
            if (ev.type === 'step_start' || ev.type === 'step_end') await new Promise(r => setTimeout(r, 160));
        }
        // Old saved traces predate the terminal event but still contain a result.
        if (!rr.result && !rr.failure) rr.failure = 'This saved run has no completed result.';
    } catch (e) {
        rr.failure = e.message;
        showToast(`Replay failed: ${e.message}`, 'error');
    } finally {
        rrSetRunning(false);
        rrRenderAll();
        rrEl('rrTraces').value = '';
    }
}

function rrHandle(ev) {
    // Replay follows recorded event time, never the age of the saved run or playback speed.
    if (rr.replaying && Number.isFinite(ev.ts)) rr.replayTime = Math.max(rr.replayTime ?? 0, ev.ts * 1000);
    if (ev.type === 'run_start') {
        rr.request = ev.request;
    } else if (ev.type === 'step_start') {
        rr.steps[ev.id] = { id: ev.id, agent: ev.agent, title: ev.title, input: ev.input, output: null,
                            llm: [], retrievals: [], tools: [], status: 'running', duration: null,
                            startedAt: performance.now(), startedTs: Number.isFinite(ev.ts) ? ev.ts * 1000 : null };
        rr.order.push(ev.id);
        if (rr.follow) rr.selected = ev.id;
    } else if (ev.type === 'llm_call') {
        rr.steps[ev.step_id]?.llm.push(ev);
    } else if (ev.type === 'retrieval') {
        rr.steps[ev.step_id]?.retrievals.push(ev);
    } else if (ev.type === 'tool_call') {
        rr.steps[ev.step_id]?.tools.push(ev);
    } else if (ev.type === 'step_end' || ev.type === 'step_error') {
        const s = rr.steps[ev.id];
        if (s) {
            s.duration = ev.duration_ms ?? rrStepElapsed(s);
            s.status = ev.type === 'step_end' ? 'done' : 'error';
            s.output = ev.type === 'step_end' ? ev.output : { error: ev.error };
        }
    } else if (ev.type === 'result') {
        rr.result = ev.result;
        rr.saveWarning = ev.result?.storage_warning || null;
        if (rr.follow) rr.selected = ev.result?.status === 'escalated_to_human' ? 'human' : (rr.selected || 'case');
    } else if (ev.type === 'error') {
        rrStopClock();
        rr.failure = ev.message || 'The review could not be completed.';
        showToast(`Pipeline error: ${ev.message}`, 'error');
    } else if (ev.type === 'done') {
        rrStopClock();
        rr.finished = true;
        if (ev.trace_saved === false || ev.trace_name === null)
            rr.saveWarning = 'The run could not be saved. Replay is unavailable; check the record store.';
    }
    rrRenderAll();
    if (ev.type === 'result' && rr.follow) rrEl('rrCaseTitle').scrollIntoView({ block: 'start' });
}

// ---------------------------------------------------------------- step -> node mapping

// Fraud risk pill for the escalated summary (MEDIUM / HIGH only; LOW is the normal case)
function rrRiskFact(res) {
    const r = res.fraud_report;
    if (!r || r.level === 'low') return '';
    return `<span class="rr-fact" title="${rrEsc(r.summary || '')}">Risk <b>${rrEsc(r.level.toUpperCase())}</b></span>`;
}

function rrNodeOf(step) {
    if (/^Round /.test(step.title)) return 'debate';
    return { Collector: 'collector', Classifier: 'classifier', CaseBrief: 'casebrief', Passenger: 'passenger', Driver: 'driver',
             Policy: 'policy', Arbitrator: 'arbitrator', Fairness: 'fairness', Executor: 'executor', Fraud: 'fraud',
             ImageAnalyst: 'collector' }[step.agent] || 'debate';
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
            const f = o.findings || [];
            if (f.length) {
                const n = k => f.filter(x => x.kind === k).length;
                return `${n('fact')} facts · ${n('conflict')} conflicts · ${n('gap')} gaps`;
            }
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
    const ms = steps.reduce((a, s) => a + rrStepElapsed(s), 0);
    const llm = steps.reduce((a, s) => a + s.llm.length, 0);
    return `${(ms / 1000).toFixed(1)}s${llm ? ` · ${llm} LLM` : ''}`;
}

// ---------------------------------------------------------------- graph

// ---------------------------------------------------------------- full chain of an agent

// Edges of this run: a route to human review counts only from the agent that escalated
function rrLiveEdges() {
    const from = rrEscalatedFrom();
    return RR_EDGES.filter(([a, b]) => b !== 'human' || a === from);
}

// Everything upstream and downstream of an agent, grouped into stages by distance from Case data
function rrChain(key) {
    const edges = rrLiveEdges();
    const walk = forward => {
        const seen = new Set(), todo = [key];
        while (todo.length) {
            const k = todo.pop();
            for (const [a, b] of edges) {
                const [x, y] = forward ? [a, b] : [b, a];
                if (x === k && !seen.has(y)) { seen.add(y); todo.push(y); }
            }
        }
        return seen;
    };
    const up = walk(false), down = walk(true);
    const inUp = k => k === key || up.has(k), inDown = k => k === key || down.has(k);
    const chainEdges = edges.filter(([a, b]) => (inUp(a) && inUp(b)) || (inDown(a) && inDown(b)));
    const rank = { case: 0 };
    for (let changed = true; changed;) {
        changed = false;
        for (const [a, b] of edges) {
            if (rank[a] != null && (rank[b] == null || rank[b] < rank[a] + 1)) { rank[b] = rank[a] + 1; changed = true; }
        }
    }
    const nodes = [...up, key, ...down].filter(k => rrNodeStatus(k) !== 'hidden');
    const stages = [];
    for (const k of nodes.sort((a, b) => rank[a] - rank[b])) {
        const last = stages[stages.length - 1];
        if (last && rank[last[0]] === rank[k]) last.push(k); else stages.push([k]);
    }
    return { nodes: new Set(nodes), edges: new Set(chainEdges.map(([a, b]) => `${a}>${b}`)), list: chainEdges, stages };
}

function rrSelectedNode() {
    const step = rr.steps[rr.selected];
    return step ? rrNodeOf(step) : rr.selected;
}

function rrRenderChain(key) {
    const chain = rrChain(key);
    return `<div class="rr-sec"><h5>Full chain</h5><ol class="rr-chainlist">${chain.stages.map((stage, i) => {
        const into = [...new Set(chain.list.filter(([, b]) => stage.includes(b)).map(([, , l]) => l))];
        return `${i ? `<li class="rr-hop" aria-hidden="true">↓ ${rrEsc(into.join(' · '))}</li>` : ''}
            <li class="rr-stage ${stage.length < 2 ? '' : stage.includes('human') ? 'parallel branch' : 'parallel'}">${stage.map(k => `<button class="rr-chain-node ${rrNodeStatus(k)} ${k === key ? 'current' : ''}"
                style="--c:${RR_NODES[k].color}" onclick="rrSelect('${k}')" ${k === key ? 'aria-current="true"' : ''}>
                <span class="rr-dot"></span><b>${rrEsc(RR_NODES[k].name)}</b><span>${rrEsc(RR_NODES[k].role)}</span></button>`).join('')}</li>`;
    }).join('')}</ol></div>`;
}

function rrRenderGraph() {
    const g = rrEl('rrGraph');
    const chain = rrChain(rrSelectedNode());
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
                    onclick="event.stopPropagation(); rrSelect('${s.id}')"
                    onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); rrSelect('${s.id}'); }">${rrEsc(label)}</span>`;
            }).join('')}</div>`;
        }
        return `<button class="rr-node ${st} ${isSel ? 'selected' : ''} ${chain.nodes.has(key) ? 'in-chain' : 'off-chain'}" data-node="${key}"
                    style="--c:${n.color}; grid-column:${n.col}; grid-row:${n.row}; ${key === 'debate' ? 'align-self:center;' : ''}"
                    onclick="rrSelect('${key}')">
                <div class="rr-node-top"><span class="rr-dot"></span><span class="rr-node-name">${rrEsc(n.name)}</span>
                    <span class="rr-node-meta" data-rr-node-time="${key}">${rrEsc(rrNodeMeta(key))}</span></div>
                <div class="rr-node-role">${rrEsc(n.role)}</div>
                <div class="rr-node-sum">${rrEsc(rrNodeSummary(key))}</div>${extra}
            </button>`;
    }).join('');
    g.classList?.add('has-chain');
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
    const chain = rrChain(rrSelectedNode()).edges;
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
        cls += chain.has(`${from}>${to}`) ? ' chain' : ' off-chain';
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
        <span class="rr-sub">${rrEsc(s ? s.title : node.role)}${s
            ? ` · <span data-rr-step-time="${rrEsc(s.id)}">${(rrStepElapsed(s) / 1000).toFixed(1)}s</span>` : ''}${s?.status === 'running' ? ' · running…' : ''}</span></div>`;
    head += rrRenderChain(RR_NODES[nodeKey] ? nodeKey : 'case');

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
    if (s.tools.length) {
        html += `<div class="rr-sec"><h5>Tools run (${s.tools.length} · deterministic, 0 tokens)</h5>
            <div class="rr-clauses">${s.tools.map(t => {
                // Collector returns findings; Fraud lookups also return history objects or null.
                const count = Array.isArray(t.findings) ? t.findings.length : t.findings == null ? 0 : 1;
                return `<details class="rr-clause"><summary>
                <span><span class="src">${rrEsc(t.tool)}</span>${Object.keys(t.args || {}).length
                    ? ` <span class="sec">${rrEsc(JSON.stringify(t.args))}</span>` : ''}</span>
                <span class="rr-node-meta">${count} result${count === 1 ? '' : 's'}</span>
                </summary><div class="excerpt">${rrToolResult(t.findings)}</div></details>`;
            }).join('')}</div></div>`;
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

// Keep structured lookup data visible, including older saved tool events.
function rrToolResult(value) {
    if (value == null) return 'No result was returned by this lookup.';
    if (Array.isArray(value)) {
        if (!value.length) return 'Nothing to report for this case.';
        return value.map(item => item && typeof item === 'object' && typeof item.statement === 'string'
            ? `[${rrEsc(item.kind || 'result')}] ${rrEsc(item.statement)}`
            : `<pre class="rr-json">${rrJson(item)}</pre>`).join('<br>');
    }
    return `<pre class="rr-json">${rrJson(value)}</pre>`;
}

// Uploaded photos as thumbnails. The file is fetched with the access code (an <img src> cannot
// send it), then shown from a blob URL; see rrHydratePhotos.
function rrPhotos(evidence, large = false) {
    const photos = evidence.map((e, i) => ({ ...e, i })).filter(e => /\.(jpe?g|png|webp)$/i.test(e.file_url || e.file || ''));
    if (!photos.length) return '';
    return `<div class="rr-label" style="margin-top:10px">Uploaded photos${large ? ' (click to enlarge)' : ''}</div>
        <div class="rr-photos${large ? ' large' : ''}">${photos.map(e =>
        `<figure><img alt="evidence[${e.i}]" title="Open full size" data-ev="${rrEsc(e.file_url || e.file)}"
            onclick="this.src && window.open(this.src, '_blank')"><figcaption>evidence[${e.i}] · ${rrEsc(e.uploaded_by)}${
            e.uploaded_at ? ' · uploaded ' + rrEsc(rrTime(e.uploaded_at)) : ''}${
            e.description ? `<br>“${rrEsc(e.description)}”` : ''}</figcaption></figure>`).join('')}</div>`;
}
const rrPhotoCache = {};
async function rrHydratePhotos(root) {
    for (const img of root.querySelectorAll('img[data-ev]:not([src])')) {
        const url = img.dataset.ev;
        try {
            if (!rrPhotoCache[url]) {
                const resp = await apiFetch(`${API_BASE}/api/evidence-file?url=${encodeURIComponent(url)}`);
                if (!resp.ok) throw new Error(resp.status);
                rrPhotoCache[url] = URL.createObjectURL(await resp.blob());
            }
            img.src = rrPhotoCache[url];
        } catch { img.replaceWith(Object.assign(document.createElement('span'), { className: 'rr-hint', textContent: 'photo not available' })); }
    }
}
if (typeof MutationObserver !== 'undefined') {
    new MutationObserver(() => rrHydratePhotos(document)).observe(document.body, { childList: true, subtree: true });
}

// Collector findings: conflicts and gaps first, each with the data it came from
function rrFindings(findings) {
    if (!findings.length) return '';
    const order = { conflict: 0, gap: 1, fact: 2 };
    const sorted = [...findings].sort((a, b) => order[a.kind] - order[b.kind]);
    return `<div class="rr-label" style="margin-top:10px">Findings (computed by tools, no LLM)</div>
        <ul class="rr-findings">${sorted.map(f => `<li class="rr-finding ${rrEsc(f.kind)}">
            <span class="rr-kind">${rrEsc(f.kind)}</span>
            <div>${rrEsc(f.statement)}${f.sources?.length
                ? `<div class="rr-src">${f.sources.map(rrEsc).join(' · ')}</div>` : ''}</div></li>`).join('')}</ul>`;
}

function rrReasoning(agent, out) {
    if (out == null) return '<div class="rr-hint">No output.</div>';
    if (typeof out === 'string') return `<div class="rr-prose">${rrRich(out)}</div>`;
    if (agent === 'Collector') {
        const dc = out.data_completeness || {};
        const fields = ['trip', 'payment', 'chat_log', 'gps_trace', 'rider_profile', 'driver_profile', 'app_events', 'platform_policy'];
        const count = v => Array.isArray(v) ? ` (${v.length})` : '';
        return `<div class="rr-kv">
            <div class="k">Case</div><div>${rrEsc(out.dispute_id)} · ${rrEsc(out.type || 'type unknown')} · filed by ${rrEsc(out.reporter)}</div>
            <div class="k">Source</div><div>${rrEsc(dc.source || 'not found on platform')}</div>
            <div class="k">Data found</div><div>${fields.map(f =>
                `<span class="rr-chip ${out[f] != null ? 'ok' : 'miss'}">${f}${count(out[f])}</span>`).join('')}</div></div>`
            + rrPhotos(out.evidence || [])
            + rrFindings(out.findings || []);
    }
    if (agent === 'ImageAnalyst') {
        const reports = out.reports || [];
        return `<div class="rr-hint">A vision model describes each photo. Its view is not a verified fact: it can only
            raise doubts, which send the case to a person; it never approves a charge or refund.</div>
            ${reports.map(r => `<div class="rr-kv" style="margin-top:8px">
                <div class="k">${rrEsc(r.evidence)}</div><div>${rrEsc(r.description || '')}</div>
                <div class="k">Seen</div><div>${rrEsc(r.scene)} · mess ${r.mess_visible ? 'yes' : 'no'} · ${rrEsc(r.severity)}
                    · matches claim: ${rrEsc(r.matches_claim)}</div>
                ${(r.generation_or_editing_signs || []).length ? `<div class="k">Edit signs</div><div>${
                    r.generation_or_editing_signs.map(rrEsc).join('; ')}</div>` : ''}</div>`).join('')}`
            + rrFindings(out.findings || []);
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
            : `<div class="rr-prose">${rrRich(String(v))}</div>`;
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
        const party = s.agent === 'Policy' ? 'Policy check' : s.agent === 'Passenger' ? 'Passenger advocate' : 'Driver advocate';
        const turn = s.agent === 'Policy' ? 'neutral' : isRound ? s.title.replace(/:.*/, '') : 'Opening';
        return `<button class="rr-bubble ${cls} ${issue ? 'failed' : ''} ${rr.selected === s.id ? 'selected' : ''} ${s.status === 'running' ? 'rr-thinking' : ''}"
                    aria-pressed="${rr.selected === s.id}" onclick="rrSelect('${s.id}')">
            ${reply ? `<div class="reply">${rrEsc(reply)}</div>` : ''}
            <div class="who"><span class="rr-party">${rrEsc(party)}</span><span class="rr-turn">${rrEsc(turn)}</span><span class="rr-turn-status">${issue ? 'Incomplete' : s.status === 'running'
                ? `Thinking… · <span data-rr-step-time="${rrEsc(s.id)}">${(rrStepElapsed(s) / 1000).toFixed(1)}s</span>`
                : (rrStepElapsed(s) / 1000).toFixed(1) + 's'}</span></div>
            ${s.status === 'running' ? '' : `<div class="txt">${rrRich(text)}</div>`}</button>`;
    }).join('');
    const sel = el.querySelector('.rr-bubble.selected');
    if (sel && rr.follow && !rr.result) sel.scrollIntoView({ block: 'nearest' });
}

// ---------------------------------------------------------------- verdict vs answer key

// Verdicts are about the complaint, not the charge: "dismissed" on a no-show dispute means the
// fee stands (what the organiser's sample calls "charge UPHELD"), so say it in words.
function rrVerdictLabel(verdict) {
    if (!verdict) return 'No verdict available';
    const filer = rrFiler();
    const who = filer === 'driver' ? "Driver's claim" : filer === 'rider' ? "Rider's complaint" : 'Complaint';
    return `${who} ${verdict.replace(/_/g, ' ')}`;
}

function rrFiler() {
    const filer = rr.request?.reporter || rr.detail?.dataset?.dispute_ticket?.filed_by;
    return filer === 'passenger' ? 'rider' : filer;
}

function rrChargeStands(verdict) {
    const trip = rr.detail?.dataset?.trip_data || {};
    if (verdict !== 'dismissed' || rrFiler() !== 'rider') return null;
    if (trip.cancellation_fee != null) return `${rrMoney(trip.cancellation_fee)} cancellation fee stands`;
    if (trip.cleaning_fee != null) return `${rrMoney(trip.cleaning_fee)} cleaning fee stands`;
    if (trip.total_fare != null) return `${rrMoney(trip.total_fare)} fare stands`;
    return null;
}

function rrRenderVerdict() {
    const el = rrEl('rrVerdict');
    const res = rr.result;
    const label = '<div class="rr-verdict-label">Resolution</div>';
    if (rr.failure) {
        el.dataset.tone = 'alert';
        el.innerHTML = label + `<div class="rr-outcome"><span class="rr-outcome-icon" aria-hidden="true">!</span><span class="rr-pill-lg escalated">Incomplete</span></div>
            <div class="rr-verdict-text">${rrEsc(rr.failure)} No completed decision is available. Retry the review.</div>`;
        el.hidden = false;
        return;
    }
    if (!res) {
        el.dataset.tone = rr.running ? 'running' : 'idle';
        el.innerHTML = label + `<div class="rr-pill-lg">${rr.running ? 'Review in progress' : 'Awaiting review'}</div>
            <div class="rr-verdict-text">${rr.running ? 'The agents are reviewing the evidence. The decision will appear here.'
                : 'Run the agents or replay a saved run to see the decision, reasoning and any refund.'}</div>`;
        return;
    }
    const quotaIssue = rrRunIssue();
    if (quotaIssue) {
        el.dataset.tone = 'alert';
        el.innerHTML = label + `<div class="rr-verdict-summary"><div class="rr-outcome"><span class="rr-outcome-icon" aria-hidden="true">!</span><span class="rr-pill-lg escalated">Incomplete</span></div>
            <div class="rr-verdict-text">${rrEsc(quotaIssue.message)} Review the completed turns below and retry after the service issue is resolved.</div></div>`;
        el.hidden = false;
        return;
    }
    const exp = rr.detail?.expected_outcome;
    let main;
    const escalated = rrEscalated();
    const v = res.verdict || {};
    const tile = (k, x, cls = '') => `<div class="rr-tile ${cls}"><div class="k">${rrEsc(k)}</div><div class="x">${rrEsc(x)}</div></div>`;
    if (escalated) {
        el.dataset.tone = 'alert';
        main = `<div class="rr-verdict-summary">
            <div class="rr-outcome"><span class="rr-outcome-icon" aria-hidden="true">!</span>
                <span class="rr-pill-lg escalated">${res.status === 'failed' ? 'Incomplete · human review' : 'Escalated to human review'}</span></div>
            <div class="rr-verdict-text">${rrRich(res.reason)}</div>
            <div class="rr-verdict-facts">${res.classification?.urgency ? `<span class="rr-fact">Urgency <b>${rrEsc(res.classification.urgency)}</b></span>` : ''}${
                v.verdict ? `<span class="rr-fact">Proposed <b>${rrEsc(rrVerdictLabel(v.verdict))}</b></span>
                <span class="rr-fact">Refund <b>${v.refund_amount != null ? rrMoney(v.refund_amount) : 'none'}</b></span>` : ''}${
                res.fairness ? `<span class="rr-fact">Fairness <b>${rrEsc((res.fairness.recommendation || '').replace(/_/g, ' '))}</b></span>` : ''}${
                rrRiskFact(res)
            }</div></div>`;
    } else {
        el.dataset.tone = { upheld: 'ok', partially_upheld: 'partial', dismissed: 'neutral' }[v.verdict] || 'neutral';
        const icon = { upheld: '✓', partially_upheld: '◐', dismissed: '✕' }[v.verdict] || '•';
        const conf = Math.round((v.confidence || 0) * 100);
        const stands = rrChargeStands(v.verdict);
        const refund = Number(v.refund_amount) > 0;
        const tiles = [
            tile('Refund', refund ? rrMoney(v.refund_amount) : 'None', refund ? 'money' : 'muted'),
            stands ? tile('Charge', stands, 'stands') : null,
            tile('Confidence', `${conf}%`, 'conf'),
        ].filter(Boolean).join('');
        const facts = [
            v.compensation ? ['Compensation', v.compensation] : null,
            v.driver_penalty ? ['Driver', v.driver_penalty] : null,
            v.human_review_needed ? ['Review', 'human required'] : v.escalation_recommended ? ['Review', 'flagged for audit'] : null,
            res.fraud_report && res.fraud_report.level !== 'low' ? ['Risk', res.fraud_report.level.toUpperCase()] : null,
        ].filter(Boolean);
        const refs = v.policy_references || [];
        main = `<div class="rr-verdict-summary">
            <div class="rr-outcome"><span class="rr-outcome-icon" aria-hidden="true">${icon}</span>
                <span class="rr-pill-lg ${rrEsc(v.verdict || '')}">${rrEsc(rrVerdictLabel(v.verdict))}</span></div>
            <div class="rr-tiles">${tiles}</div>
            <h4 class="rr-why">Why</h4>
            <div class="rr-verdict-text">${rrRich(v.rationale || '')}</div>
            ${facts.length ? `<div class="rr-verdict-facts">${facts.map(([k, x]) => `<span class="rr-fact">${rrEsc(k)} <b>${rrEsc(x)}</b></span>`).join('')}</div>` : ''}
            <div class="rr-cites"><span class="k">Rules cited</span>${refs.length ? rrRuleChips(refs) : '<span class="rr-cite doc">no policy cited</span>'}</div>
            </div>`;
    }

    let key = '<div class="rr-key"><h4>Answer key</h4><div class="rr-hint">This case has no machine-readable expected outcome.</div></div>';
    if (exp) {
        const gotHuman = escalated || !!v.human_review_needed;
        const mark = ok => ok == null ? '<span class="rr-na">n/a</span>' : ok ? '<span class="rr-ok">✓</span>' : '<span class="rr-bad">✗</span>';
        const vOk = exp.verdict == null ? null : !escalated && v.verdict === exp.verdict;
        const expRefund = exp.refund_amount;
        const rOk = expRefund == null || escalated ? null : Math.abs((v.refund_amount || 0) - expRefund) < 0.01;
        key = `<div class="rr-key"><h4>Answer key · hidden from agents</h4>
            <div class="row"><span>Verdict</span><span>${rrEsc(exp.verdict ? rrVerdictLabel(exp.verdict) : 'human review')}</span>${mark(vOk)}</div>
            <div class="row"><span>Refund</span><span>${expRefund == null ? '—' : rrMoney(expRefund)}</span>${mark(rOk)}</div>
            <div class="row"><span>Human review</span><span>${exp.requires_human_review ? 'yes' : 'no'}</span>${mark(gotHuman === !!exp.requires_human_review)}</div>
            <div class="why">${rrEsc(exp.reason)}</div></div>`;
    }
    const keyOpen = el.querySelector('.rr-key-details')?.open;
    // What each party is told: the executor writes one notice per party from the ruling's fields
    // in the language the viewer picks (Singapore's four official languages), re-rendered by the API
    if (rr.noticeFor !== res) { rr.noticeFor = res; rr.noticeByLang = {}; rr.noticeLang = 'en'; }
    const notes = (rr.noticeByLang[rr.noticeLang] || res.execution?.notifications || []).filter(n => n && n.message);
    const langs = RR_NOTICE_LANGS.map(([code, name]) => `<button type="button" class="rr-lang${code === rr.noticeLang ? ' on' : ''}"
        data-notice-lang="${code}" aria-pressed="${code === rr.noticeLang}">${name}</button>`).join('');
    const notices = notes.length ? `<div class="rr-notices"><h4>Sent to both parties <span class="rr-hint">simulated, not delivered</span>
        <span class="rr-langs" role="group" aria-label="Notice language">${langs}</span></h4>
        <div class="rr-notice-grid">${notes.map(n => `<div class="rr-notice ${rrEsc(n.recipient)}">
            <div class="rr-notice-to">To the ${rrEsc(n.recipient)}</div>
            <div class="rr-notice-subj">${rrEsc(n.subject || '')}</div>
            <div class="rr-prose">${rrRich(n.message)}</div></div>`).join('')}</div></div>` : '';
    el.innerHTML = `${label}${rr.saveWarning ? `<div class="rr-verdict-text">${rrEsc(rr.saveWarning)}</div>` : ''}<div class="rr-verdict-main">${main}</div>${notices}
        <details class="rr-key-details" ${keyOpen ? 'open' : ''}><summary>Compare with answer key · hidden from agents</summary>${key}</details>`;
    el.hidden = false;
    el.onclick = e => {  // one handler for the language buttons, which are re-rendered with the panel
        const b = e.target?.closest?.('[data-notice-lang]');
        if (b) rrNoticeLang(b.dataset.noticeLang);
    };
}

const RR_NOTICE_LANGS = [['en', 'English'], ['zh', '中文'], ['ms', 'Melayu'], ['ta', 'தமிழ்']];

async function rrNoticeLang(lang) {
    const res = rr.result;
    if (!res) return;
    if (lang !== 'en' && !rr.noticeByLang[lang]) {
        try {
            const resp = await apiFetch(`${API_BASE}/api/notices`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    verdict: res.verdict || {}, dispute_id: res.dispute_id || rr.current || '',
                    reporter: rr.request?.reporter || rr.detail?.dataset?.dispute_ticket?.filed_by || null,
                    escalated: rrEscalated(), language: lang, chat_signals: res.chat_signals || null,
                }),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            if (rr.result !== res) return;  // another case was opened meanwhile
            rr.noticeByLang[lang] = (await resp.json()).notifications;
        } catch (err) {
            console.warn('Notice translation failed', err);
            return;
        }
    }
    rr.noticeLang = lang;
    rrRenderVerdict();
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
rrEl('rrFlow').addEventListener('toggle', () => requestAnimationFrame(rrDrawEdges));
rrEl('rrFilter').addEventListener('input', e => { rr.filter = e.target.value; rrRenderLibrary(); });
rrEl('rrTraces').addEventListener('change', e => rrReplay(e.target.value));
rrRenderGraph();
rrRenderVerdict();
rrLoadCases();
