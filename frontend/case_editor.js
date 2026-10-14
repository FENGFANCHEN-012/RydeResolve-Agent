// ============================================================
// Case editor: build a case by hand, or copy the open case and change it.
// Edits a working copy of the dataset (same format as the case files): fields the form does not
// show are kept as they are. Save sends the dataset and the photos to POST /api/custom-cases; the
// server assigns the ids and the new case is listed and selected, ready to run.
// Relies on API_BASE, apiFetch(), showToast() (index.html) and rr*, rrEsc() (dispute.js).
// ============================================================

const ce = { data: null, photos: [], rules: [], policyKey: 'platform_policy', texts: null, saving: false };

const CE_TYPES = ['no_show', 'cancellation', 'fare_dispute', 'route_deviation', 'service_quality',
    'cleaning_fee', 'delivery_dispute', 'driver_rights', 'accident_liability'];
const CE_TIME_MODES = {
    set: 'Set time and place below',
    own: "Keep the photo's own time and place",
    none: 'No time or place (strip them)',
    copy: 'Exact copy of the original file',
};

// ---- small helpers

function ceGet(obj, path) { return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj); }
function ceSet(obj, path, value) {
    const keys = path.split('.');
    let o = obj;
    for (const k of keys.slice(0, -1)) { if (o[k] == null || typeof o[k] !== 'object') o[k] = {}; o = o[k]; }
    const last = keys[keys.length - 1];
    if (value === undefined) delete o[last]; else o[last] = value;
}
// ISO time (any offset) <-> datetime-local value in Singapore time
function ceToLocal(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return '';
    return new Date(d.getTime() + 8 * 3600 * 1000).toISOString().slice(0, 19);
}
function ceFromLocal(v) {
    if (!v) return undefined;
    return (v.length === 16 ? v + ':00' : v) + '+08:00';
}
function ceNow() { return ceToLocal(new Date().toISOString()); }
// A rule value typed as text: numbers, true/false, lists and objects become JSON values
function ceValue(text) {
    const t = String(text ?? '').trim();
    if (t === '') return null;
    try { return JSON.parse(t); } catch (e) { return t; }
}
function ceValueText(v) { return v == null ? '' : (typeof v === 'string' ? v : JSON.stringify(v)); }

// ---- open / close

function ceBlank() {
    const now = ceToLocal(new Date().toISOString());
    return {
        dispute_ticket: { filed_by: 'rider', dispute_type: 'no_show', description: '', filed_at: ceFromLocal(now), status: 'open' },
        rider_profile: { rider_id: 'R-0001', name: '', dispute_history: { total_disputes: 0, upheld: 0, rejected: 0 }, fraud_flags: 0 },
        driver_profile: { driver_id: 'D-0001', name: '', dispute_history: { total_disputes: 0, upheld_against: 0, rejected: 0 }, fraud_flags: 0 },
        trip_data: { rider_id: 'R-0001', driver_id: 'D-0001', pickup_location: {}, dropoff_location: {} },
        gps_telemetry: [], chat_logs: [], app_events: [], platform_policy: {},
    };
}

async function ceOpen(copy) {
    if (copy && !rr.detail?.dataset) { showToast('Pick a case first.', 'error'); return; }
    const data = copy ? JSON.parse(JSON.stringify(rr.detail.dataset)) : ceBlank();
    delete data._source;
    ce.data = data;
    ce.policyKey = data.cancellation_policy ? 'cancellation_policy' : 'platform_policy';
    ce.rules = Object.entries(data[ce.policyKey] || {}).map(([key, v]) => {
        const wrapped = v && typeof v === 'object' && !Array.isArray(v) && 'value' in v;
        return { key, value: ceValueText(wrapped ? v.value : v), text: wrapped ? (v.text || '') : '', check: wrapped ? v.check : undefined };
    });
    ce.photos = (data.evidence || []).filter(e => e && e.file_url).map(e => ({
        source: `existing:${e.file_url}`, url: e.file_url, file: null, uploaded_by: e.uploaded_by || 'driver',
        uploaded_at: ceToLocal(e.uploaded_at), description: e.description || '', time_mode: 'own',
        taken_at: '', lat: '', lng: '', software: '',
    }));
    delete data.evidence;
    rrEl('ceTitle').textContent = copy ? `New case — copy of ${data.dispute_ticket?.dispute_id || rr.current}` : 'New case';
    if (!ce.texts) {
        try {
            const resp = await apiFetch(`${API_BASE}/api/case-rule-texts`);
            ce.texts = resp.ok ? (await resp.json()).texts || {} : {};
        } catch (e) { ce.texts = {}; }
    }
    ceRender();
    rrEl('ceDialog').showModal();
}

function ceClose() {
    for (const p of ce.photos) if (p.preview) URL.revokeObjectURL(p.preview);
    rrEl('ceDialog').close();
}

// ---- render

function ceField(label, path, kind = 'text', opts = {}) {
    const v = ceGet(ce.data, path);
    const id = `ce_${path.replace(/\./g, '_')}`;
    let input;
    if (kind === 'time') {
        input = `<input id="${id}" class="rr-input" type="datetime-local" step="1" data-path="${path}" data-kind="time" value="${rrEsc(ceToLocal(v))}">`;
    } else if (kind === 'select') {
        input = `<select id="${id}" class="rr-select" data-path="${path}" data-kind="text">${opts.options.map(o =>
            `<option value="${rrEsc(o)}" ${o === v ? 'selected' : ''}>${rrEsc(o)}</option>`).join('')}</select>`;
    } else if (kind === 'area') {
        input = `<textarea id="${id}" class="rr-textarea" data-path="${path}" data-kind="text" placeholder="${rrEsc(opts.placeholder || '')}">${rrEsc(v ?? '')}</textarea>`;
    } else {
        const list = opts.list ? `list="${opts.list}"` : '';
        input = `<input id="${id}" class="rr-input" ${kind === 'num' ? 'type="number" step="any"' : 'type="text"'} ${list}
            data-path="${path}" data-kind="${kind}" value="${rrEsc(v ?? '')}" placeholder="${rrEsc(opts.placeholder || '')}">`;
    }
    return `<label class="ce-field ${opts.wide ? 'wide' : ''}" for="${id}"><span>${rrEsc(label)}</span>${input}</label>`;
}

function ceSection(title, body, hint = '') {
    return `<fieldset class="ce-sec"><legend>${rrEsc(title)}</legend>${hint ? `<p class="rr-hint">${rrEsc(hint)}</p>` : ''}${body}</fieldset>`;
}

// One editable table: cols = [[label, field, kind, width?]]
function ceTable(name, rows, cols, addLabel) {
    const head = cols.map(c => `<th>${rrEsc(c[0])}</th>`).join('') + '<th></th>';
    const body = rows.map((r, i) => `<tr>${cols.map(([, f, kind, opts]) => {
        const v = r[f];
        if (kind === 'time') return `<td><input class="rr-input" type="datetime-local" step="1" data-list="${name}" data-i="${i}" data-f="${f}" data-kind="time" value="${rrEsc(ceToLocal(v))}"></td>`;
        if (kind === 'select') return `<td><select class="rr-select" data-list="${name}" data-i="${i}" data-f="${f}" data-kind="text">${opts.map(o =>
            `<option ${o === v ? 'selected' : ''}>${rrEsc(o)}</option>`).join('')}</select></td>`;
        const list = kind === 'rulekey' ? 'list="ceRuleKeys"' : '';
        return `<td><input class="rr-input" type="${kind === 'num' ? 'number' : 'text'}" ${kind === 'num' ? 'step="any"' : ''} ${list}
            data-list="${name}" data-i="${i}" data-f="${f}" data-kind="${kind === 'rulekey' ? 'text' : kind}" value="${rrEsc(v ?? '')}"></td>`;
    }).join('')}<td><button type="button" class="rr-btn ghost ce-x" onclick="ceRemoveRow('${name}', ${i})" aria-label="Remove row">×</button></td></tr>`).join('');
    return `<div class="ce-table-wrap"><table class="ce-table"><thead><tr>${head}</tr></thead><tbody>${body ||
        `<tr><td colspan="${cols.length + 1}" class="rr-empty">None yet.</td></tr>`}</tbody></table></div>
        <button type="button" class="rr-btn ghost" onclick="ceAddRow('${name}')">+ ${rrEsc(addLabel)}</button>`;
}

const CE_LISTS = {
    chat_logs: [['Time', 'timestamp', 'time'], ['From', 'sender', 'select', ['rider', 'driver', 'system']],
                ['Kind', 'type', 'select', ['message', 'call']], ['Message', 'content', 'text']],
    app_events: [['Time', 'timestamp', 'time'], ['Event', 'event_type', 'text'], ['Details', 'details', 'text']],
    gps_telemetry: [['Time', 'timestamp', 'time'], ['Lat', 'lat', 'num'], ['Lng', 'lng', 'num'],
                    ['Speed km/h', 'speed_kmh', 'num'], ['Status', 'status', 'text']],
    rules: [['Rule key', 'key', 'rulekey'], ['Value', 'value', 'text'], ['What it covers', 'text', 'text']],
};

function ceRows(name) { return name === 'rules' ? ce.rules : (ce.data[name] = ce.data[name] || []); }

function ceRender() {
    const d = ce.data;
    const types = [...new Set([...CE_TYPES, ...rr.cases.map(c => c.dispute_type).filter(Boolean)])];
    const ticket = ceSection('Complaint',
        `<div class="ce-grid">${ceField('Dispute type', 'dispute_ticket.dispute_type', 'text', { list: 'ceTypes' })}
            ${ceField('Filed by', 'dispute_ticket.filed_by', 'select', { options: ['rider', 'driver'] })}
            ${ceField('Filed at', 'dispute_ticket.filed_at', 'time')}
            ${ceField('Complaint', 'dispute_ticket.description', 'area', { wide: true, placeholder: 'What the filer says happened and what they ask for' })}</div>`);
    const trip = ceSection('Trip',
        `<div class="ce-grid">
            ${ceField('Pickup place', 'trip_data.pickup_location.name')}${ceField('Pickup lat', 'trip_data.pickup_location.lat', 'num')}${ceField('Pickup lng', 'trip_data.pickup_location.lng', 'num')}
            ${ceField('Drop-off place', 'trip_data.dropoff_location.name')}${ceField('Drop-off lat', 'trip_data.dropoff_location.lat', 'num')}${ceField('Drop-off lng', 'trip_data.dropoff_location.lng', 'num')}
            ${ceField('Scheduled', 'trip_data.scheduled_time', 'time')}${ceField('Driver arrived', 'trip_data.driver_arrival_time', 'time')}${ceField('Pickup', 'trip_data.pickup_time', 'time')}
            ${ceField('Drop-off', 'trip_data.dropoff_time', 'time')}${ceField('Cancelled at', 'trip_data.cancellation_time', 'time')}${ceField('Cancel reason', 'trip_data.cancellation_reason', 'text', { placeholder: 'e.g. rider_no_show' })}
            ${ceField('Estimated fare S$', 'trip_data.estimated_fare', 'num')}${ceField('Fare charged S$', 'trip_data.total_fare', 'num')}${ceField('Cancellation fee S$', 'trip_data.cancellation_fee', 'num')}
            ${ceField('Cleaning fee S$', 'trip_data.cleaning_fee', 'num')}${ceField('Estimated km', 'trip_data.estimated_distance_km', 'num')}${ceField('Actual km', 'trip_data.actual_distance_km', 'num')}
        </div>`, 'Leave a field empty when it does not apply (e.g. no drop-off for a cancelled trip). Times are Singapore time.');
    const person = (who, extra) => `<div class="ce-grid">
            ${ceField('ID', `${who}_profile.${who}_id`)}${ceField('Name', `${who}_profile.name`)}${ceField('Account age (days)', `${who}_profile.account_age_days`, 'num')}
            ${ceField('Total trips', `${who}_profile.total_trips`, 'num')}${ceField('Rating', `${who}_profile.avg_rating`, 'num')}${ceField('Fraud flags', `${who}_profile.fraud_flags`, 'num')}
            ${ceField('Past disputes', `${who}_profile.dispute_history.total_disputes`, 'num')}
            ${who === 'rider' ? ceField('Upheld', 'rider_profile.dispute_history.upheld', 'num') : ceField('Upheld against', 'driver_profile.dispute_history.upheld_against', 'num')}
            ${ceField('Rejected', `${who}_profile.dispute_history.rejected`, 'num')}${extra}</div>`;
    const people = ceSection('Rider', person('rider', ceField('Pays by', 'rider_profile.payment_method')))
        + ceSection('Driver', person('driver', ceField('Vehicle', 'driver_profile.vehicle', 'text', { placeholder: 'Toyota Corolla (SKV 1234 A)' })));
    const chat = ceSection('In-app chat', ceTable('chat_logs', d.chat_logs || [], CE_LISTS.chat_logs, 'Add message'),
        'What the rider and driver said to each other, in time order.');
    const events = ceSection('App events', ceTable('app_events', d.app_events || [], CE_LISTS.app_events, 'Add event'),
        'Platform records, e.g. driver_arrived, driver_cancelled, cancellation_fee_applied, cleaning_claim_submitted.');
    const gps = ceSection('GPS points', ceTable('gps_telemetry', d.gps_telemetry || [], CE_LISTS.gps_telemetry, 'Add GPS point'));
    const rules = ceSection("This trip's rules", ceTable('rules', ce.rules, CE_LISTS.rules, 'Add rule'),
        'Pick a known key to fill in what it covers. Values: numbers, true/false, or text.');
    const photos = ceSection('Photos', cePhotosHtml(),
        'Each photo is saved again on the server with the time and place you choose, so you can show a genuine photo or a doubtful one (taken before the trip, far away, edited).');
    rrEl('ceBody').innerHTML = `
        <datalist id="ceTypes">${types.map(t => `<option value="${rrEsc(t)}">`).join('')}</datalist>
        <datalist id="ceRuleKeys">${Object.keys(ce.texts || {}).sort().map(k => `<option value="${rrEsc(k)}">`).join('')}</datalist>
        ${ticket}${trip}${people}${chat}${events}${gps}${rules}${photos}`;
    // Picking a known rule key fills in what it covers, unless that box already has text
    rrEl('ceBody').querySelectorAll('[data-list="rules"][data-f="key"]').forEach(el => el.addEventListener('change', () => {
        const box = rrEl('ceBody').querySelector(`[data-list="rules"][data-i="${el.dataset.i}"][data-f="text"]`);
        if (box && !box.value.trim() && ce.texts?.[el.value.trim()]) box.value = ce.texts[el.value.trim()];
    }));
}

function cePhotosHtml() {
    const rows = ce.photos.map((p, i) => {
        const src = p.preview || null;
        const modes = Object.entries(CE_TIME_MODES).filter(([k]) => k !== 'copy' || !p.file)
            .map(([k, label]) => `<option value="${k}" ${p.time_mode === k ? 'selected' : ''}>${rrEsc(label)}</option>`).join('');
        return `<div class="ce-photo">
            <div class="ce-thumb">${src ? `<img src="${src}" alt="Photo ${i + 1}">` : `<img data-ev="${rrEsc(p.url)}" alt="Photo ${i + 1}">`}</div>
            <div class="ce-grid">
                <label class="ce-field"><span>Uploaded by</span><select class="rr-select" data-photo="${i}" data-f="uploaded_by">
                    ${['driver', 'rider'].map(o => `<option ${p.uploaded_by === o ? 'selected' : ''}>${o}</option>`).join('')}</select></label>
                <label class="ce-field"><span>Uploaded at</span><input class="rr-input" type="datetime-local" step="1" data-photo="${i}" data-f="uploaded_at" value="${rrEsc(p.uploaded_at)}"></label>
                <label class="ce-field wide"><span>Caption</span><input class="rr-input" data-photo="${i}" data-f="description" value="${rrEsc(p.description)}"></label>
                <label class="ce-field wide"><span>Photo time and place</span><select class="rr-select" data-photo="${i}" data-f="time_mode" onchange="ceSyncAll(); ceRender()">${modes}</select></label>
                ${p.time_mode === 'set' ? `
                <label class="ce-field"><span>Taken at</span><input class="rr-input" type="datetime-local" step="1" data-photo="${i}" data-f="taken_at" value="${rrEsc(p.taken_at)}"></label>
                <label class="ce-field"><span>Lat</span><input class="rr-input" type="number" step="any" data-photo="${i}" data-f="lat" value="${rrEsc(p.lat)}"></label>
                <label class="ce-field"><span>Lng</span><input class="rr-input" type="number" step="any" data-photo="${i}" data-f="lng" value="${rrEsc(p.lng)}"></label>
                <label class="ce-field wide"><span>Editing software tag (optional)</span><input class="rr-input" data-photo="${i}" data-f="software" value="${rrEsc(p.software)}" placeholder="e.g. Adobe Photoshop"></label>` : ''}
            </div>
            <button type="button" class="rr-btn ghost ce-x" onclick="ceRemovePhoto(${i})" aria-label="Remove photo">×</button>
        </div>`;
    }).join('');
    return `<div id="cePhotos">${rows || '<div class="rr-empty">No photos.</div>'}</div>
        <label class="rr-btn ghost ce-upload">+ Add photos<input type="file" accept="image/jpeg,image/png,image/webp" multiple hidden onchange="ceAddPhotos(this)"></label>
        <span class="rr-hint">JPG, PNG or WebP, up to 10 MB each, 5 new photos per save, 8 in all.</span>`;
}

// ---- read the form back

function ceSyncFields() {
    rrEl('ceBody').querySelectorAll('[data-path]').forEach(el => {
        const kind = el.dataset.kind, raw = el.value;
        let v;
        if (kind === 'time') v = ceFromLocal(raw);
        else if (kind === 'num') v = raw === '' ? undefined : Number(raw);
        else v = raw.trim() === '' ? undefined : raw;
        // An empty field that was null in the case stays null ("never arrived" is a record, not a gap)
        if (v === undefined && ceGet(ce.data, el.dataset.path) === null) return;
        ceSet(ce.data, el.dataset.path, v);
    });
}

function ceSyncLists() {
    rrEl('ceBody').querySelectorAll('[data-list]').forEach(el => {
        const row = ceRows(el.dataset.list)[Number(el.dataset.i)];
        if (!row) return;
        const kind = el.dataset.kind, raw = el.value;
        let v = kind === 'time' ? ceFromLocal(raw) : kind === 'num' ? (raw === '' ? undefined : Number(raw)) : raw;
        if (v === undefined) delete row[el.dataset.f]; else row[el.dataset.f] = v;
    });
}

function ceSyncPhotos() {
    rrEl('ceBody').querySelectorAll('[data-photo]').forEach(el => {
        const p = ce.photos[Number(el.dataset.photo)];
        if (p) p[el.dataset.f] = el.value;
    });
}

function ceSyncAll() { ceSyncFields(); ceSyncLists(); ceSyncPhotos(); }

// ---- row and photo actions (sync first so typed values survive the re-render)

function ceAddRow(name) {
    ceSyncAll();
    const rows = ceRows(name);
    const last = rows[rows.length - 1];
    const t = ce.data.trip_data || {};
    const ts = last?.timestamp || t.pickup_time || t.driver_arrival_time || t.cancellation_time || t.scheduled_time || ceFromLocal(ceNow());
    rows.push(name === 'rules' ? { key: '', value: '', text: '' }
        : name === 'chat_logs' ? { timestamp: ts, sender: 'rider', type: 'message', content: '' }
        : name === 'app_events' ? { timestamp: ts, event_type: '', details: '' }
        : { timestamp: ts, lat: last?.lat ?? '', lng: last?.lng ?? '', speed_kmh: 0, status: 'on_trip' });
    ceRender();
}

function ceRemoveRow(name, i) { ceSyncAll(); ceRows(name).splice(i, 1); ceRender(); }

function ceAddPhotos(input) {
    ceSyncAll();
    const drop = ce.data.trip_data?.dropoff_location || ce.data.trip_data?.pickup_location || {};
    const when = ce.data.trip_data?.dropoff_time || ce.data.trip_data?.cancellation_time;
    for (const file of input.files) {
        if (ce.photos.length >= 8) { showToast('A case can have at most 8 photos.', 'error'); break; }
        ce.photos.push({
            source: null, file, preview: URL.createObjectURL(file), uploaded_by: ce.data.dispute_ticket?.filed_by === 'driver' ? 'driver' : 'rider',
            uploaded_at: ceToLocal(when ? new Date(new Date(when).getTime() + 20 * 60000).toISOString() : new Date().toISOString()),
            description: '', time_mode: 'set',
            taken_at: ceToLocal(when ? new Date(new Date(when).getTime() + 10 * 60000).toISOString() : new Date().toISOString()),
            lat: drop.lat ?? '', lng: drop.lng ?? '', software: '',
        });
    }
    input.value = '';
    ceRender();
}

function ceRemovePhoto(i) {
    ceSyncAll();
    const [p] = ce.photos.splice(i, 1);
    if (p?.preview) URL.revokeObjectURL(p.preview);
    ceRender();
}

// ---- save

function ceDataset() {
    ceSyncAll();
    const data = JSON.parse(JSON.stringify(ce.data));
    const policy = {};
    for (const r of ce.rules) {
        const key = String(r.key || '').trim();
        if (!key) continue;
        const rule = { value: ceValue(r.value) };
        if (String(r.text || '').trim()) rule.text = String(r.text).trim();
        if (r.check !== undefined) rule.check = r.check;
        policy[key] = rule;
    }
    delete data.platform_policy; delete data.cancellation_policy;
    data[ce.policyKey] = policy;
    for (const k of ['chat_logs', 'app_events', 'gps_telemetry']) {
        data[k] = (data[k] || []).filter(r => Object.entries(r).some(([f, v]) => f !== 'timestamp' && v !== '' && v != null));
    }
    data.trip_data = data.trip_data || {};
    data.trip_data.rider_id = data.rider_profile?.rider_id ?? data.trip_data.rider_id;
    data.trip_data.driver_id = data.driver_profile?.driver_id ?? data.trip_data.driver_id;
    return data;
}

async function ceSave() {
    if (ce.saving) return;
    const data = ceDataset();
    if (!String(data.dispute_ticket?.description || '').trim()) { showToast('Write the complaint first.', 'error'); return; }
    const form = new FormData();
    const meta = [];
    let n = 0;
    for (const p of ce.photos) {
        const m = { uploaded_by: p.uploaded_by, uploaded_at: ceFromLocal(p.uploaded_at) || null, description: p.description,
                    time_mode: p.time_mode, taken_at: ceFromLocal(p.taken_at) || null,
                    gps: p.lat !== '' && p.lng !== '' ? [Number(p.lat), Number(p.lng)] : null, software: p.software || null };
        if (p.file) { form.append('files', p.file, p.file.name); m.source = `upload:${n++}`; }
        else m.source = p.source;
        meta.push(m);
    }
    if (n > 5) { showToast('Add at most 5 new photos per save.', 'error'); return; }
    form.append('case', JSON.stringify(data));
    form.append('photos', JSON.stringify(meta));
    ce.saving = true;
    rrEl('ceSaveBtn').disabled = true; rrEl('ceSaveBtn').textContent = 'Saving…';
    try {
        const resp = await apiFetch(`${API_BASE}/api/custom-cases`, { method: 'POST', body: form });
        const out = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(out.detail || `HTTP ${resp.status}`);
        ceClose();
        showToast(`Saved as ${out.dispute_id}. Press Run agents to resolve it.`, 'success');
        await rrLoadCases();
        rrSelectCase(out.order_id);
    } catch (e) {
        showToast(`Could not save: ${e.message}`, 'error');
    } finally {
        ce.saving = false;
        rrEl('ceSaveBtn').disabled = false; rrEl('ceSaveBtn').textContent = 'Save case';
    }
}
