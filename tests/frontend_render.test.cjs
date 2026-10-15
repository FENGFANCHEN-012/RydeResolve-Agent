// Run with: node --test tests/frontend_render.test.cjs (no dependencies).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function page(extra = {}) {
    const elements = new Map();
    const element = id => {
        if (!elements.has(id)) elements.set(id, {
            innerHTML: '', textContent: '', hidden: false, dataset: {},
            querySelector: () => null,
            addEventListener() {}, scrollIntoView() {},
        });
        return elements.get(id);
    };
    const context = vm.createContext({
        document: { getElementById: element, querySelectorAll: selector => [...elements.values()].filter(el =>
            selector === '[data-rr-node-time]' ? el.dataset?.rrNodeTime : el.dataset?.rrStepTime) },
        window: { addEventListener() {} },
        requestAnimationFrame() {},
        showToast() {},
        API_BASE: 'http://127.0.0.1:8000',
        apiFetch: async () => ({ok: true, json: async () => ({})}),
        setTimeout, clearTimeout, TextDecoder, AbortSignal, performance,
        setInterval: () => 1, clearInterval() {},
        ...extra,
    });
    const source = fs.readFileSync(path.join(__dirname, '../frontend/dispute.js'), 'utf8');
    // Bootstrap is browser-only; exercise the actual render functions below.
    vm.runInContext(source.slice(0, source.indexOf("window.addEventListener('resize'")), context);
    return { element, run: code => vm.runInContext(code, context) };
}

test('live stream renders history objects and continues through completion', async () => {
    const events = [
        {type:'step_start', id:'s4', agent:'Fraud', title:'Fraud screening', input:{}},
        {type:'tool_call', step_id:'s4', tool:'get_user_history', args:{user_id:'test-rider'},
            findings:{user_id:'test-rider', role:'rider', source:'profile', fraud_confirmed:0,
                recent_disputes:[{reason:'<unsafe>'}]}},
        {type:'step_end', id:'s4', output:{level:'low', summary:'No risk signals'}, duration_ms:2},
        {type:'result', result:{status:'resolved', verdict:{verdict:'dismissed', confidence:.9}}},
        {type:'done', trace_saved:true, trace_name:'test.json'},
    ];
    let i = 0;
    const p = page({apiFetch: async () => ({ok:true, body:{getReader:() => ({
        read:async () => i < events.length
            ? {done:false, value:Buffer.from(`data: ${JSON.stringify(events[i++])}\n\n`)}
            : {done:true},
        cancel:async () => {},
    })}})});
    // Keep every renderer active: a display exception used to cancel the stream.
    p.run("rr.current='test'; rr.detail={dataset:{}}; rrLoadTraces=()=>{}");
    await p.run('rrRun()');
    assert.equal(p.run('rr.failure'), null);
    assert.equal(p.run('rr.finished'), true);
    assert.equal(p.element('rrStatus').textContent, 'Resolved');
    const html = p.element('rrInspector').innerHTML;
    assert.match(html, /test-rider/);
    assert.match(html, /fraud_confirmed/);
    assert.match(html, /&lt;unsafe&gt;/);
    assert.doesNotMatch(html, /<unsafe>|undefined result/);
});

test('running timers tick without rerendering and stop at the server duration', () => {
    let now = 1000, tick, cleared = 0, started = 0;
    const p = page({performance:{now:()=>now},
        setInterval:fn=>{tick=fn; started++; return 7;},
        clearInterval:id=>{assert.equal(id,7); cleared++;}});
    p.run(`rrSetRunning(true); rrHandle({type:'step_start',id:'f',agent:'Fairness',title:'Audit'});
        rrHandle({type:'step_start',id:'p',agent:'Policy',title:'Policy check'})`);
    const node = p.element('timer-node'); node.dataset={rrNodeTime:'fairness'};
    const step = p.element('timer-step'); step.dataset={rrStepTime:'p'};
    const before = p.element('rrInspector').innerHTML;
    assert.match(before, /Full chain/);
    assert.match(before, /data-rr-step-time="p"/);
    now = 6350; tick();
    assert.equal(node.textContent,'5.3s');
    assert.equal(step.textContent,'5.3s');
    assert.equal(p.element('rrInspector').innerHTML,before);
    p.run('rrRenderDebate()');
    assert.match(p.element('rrDebate').innerHTML,/Thinking… · .*5\.3s/);
    assert.match(p.element('rrDebate').innerHTML, /class="rr-party">Policy check/);
    assert.match(p.element('rrDebate').innerHTML, /class="rr-turn">neutral/);
    p.run(`rrHandle({type:'step_end',id:'f',duration_ms:5432,output:{}})`);
    now=11000; tick();
    assert.equal(p.run("rrNodeMeta('fairness')"),'5.4s');
    assert.equal(step.textContent,'10.0s');
    p.run('rrSetRunning(false)');
    now=20000;
    assert.equal(p.run("rrNodeMeta('policy')"),'10.0s');
    assert.equal(started,1);
    assert.equal(cleared,1);
    assert.equal(p.run('rr.clock'),null);
});

test('replay uses saved timestamps instead of the local clock and needs no timer', async () => {
    const events = [
        {type:'run_start',ts:100,request:{}},
        {type:'step_start',id:'f',agent:'Fairness',title:'Audit',ts:101},
        {type:'llm_call',step_id:'f',ts:106.5,duration_ms:4000},
        {type:'step_end',id:'f',ts:108,duration_ms:6990,output:{}},
        {type:'result',result:{status:'resolved',verdict:{verdict:'dismissed'}},ts:109},
    ];
    const observed=[];
    const p = page({performance:{now:()=>999999999},
        setInterval:()=>{throw new Error('Replay must not use a live timer');},
        apiFetch:async()=>({ok:true,json:async()=>({events})}),
        capture:()=>observed.push(p.run("rrNodeMeta('fairness')")),
    });
    p.run('const originalRender = rrRenderAll; rrRenderAll=()=>{originalRender();capture()}');
    await p.run("rrReplay('saved.json')");
    assert.ok(observed.includes('5.5s · 1 LLM'));
    assert.equal(p.run("rrNodeMeta('fairness')"),'7.0s · 1 LLM');
    assert.equal(p.run('rr.clock'),null);
    assert.equal(p.run('rr.failure'),null);
});

test('error and reset clear the timer and freeze unfinished steps', () => {
    let now=0, clears=0;
    const p=page({performance:{now:()=>now},clearInterval:()=>clears++});
    p.run(`rrSetRunning(true);rrHandle({type:'step_start',id:'f',agent:'Fairness',title:'Audit'})`);
    now=4000;
    p.run("rrHandle({type:'error',message:'Connection lost'})");
    now=9000;
    assert.equal(p.run("rrNodeMeta('fairness')"),'4.0s');
    assert.equal(clears,1);
    p.run('rrResetRun();rrSetRunning(true);rrResetRun()');
    assert.equal(clears,2);
    assert.equal(p.run('rr.order.length'),0);
    assert.equal(p.run('rr.clock'),null);
});

test('tool inspector preserves lists, objects, scalars and missing lookup results', () => {
    for (const [findings, expected] of [
        [[{kind:'fact',statement:'Evidence <confirmed>'}], /Evidence &lt;confirmed&gt;/],
        [[{code:'repeat_claim', severity:'medium', detail:'Review history'}], /repeat_claim/],
        [{user_id:'test-rider'}, /test-rider/],
        [null, /No result was returned/],
        [undefined, /No result was returned/],
        [[], /Nothing to report/],
        ['Lookup <unavailable>', /Lookup &lt;unavailable&gt;/],
    ]) {
        const p = page();
        p.run(`rrHandle({type:'step_start',id:'s4',agent:'Fraud',title:'Fraud screening',input:{}});
            rrHandle({type:'tool_call',step_id:'s4',tool:'lookup',args:{},findings:${JSON.stringify(findings)}})`);
        assert.match(p.element('rrInspector').innerHTML, expected);
    }
});

test('resolution remains visible while idle and during review', () => {
    const p = page();
    p.run('rrRenderVerdict()');
    assert.match(p.element('rrVerdict').innerHTML, /Awaiting review/);
    p.run('rr.running = true; rrRenderVerdict()');
    assert.match(p.element('rrVerdict').innerHTML, /Review in progress/);
});

test('resolved verdict shows refund, confidence and a collapsed comparison', () => {
    const p = page();
    p.run(`rr.result = {status:'resolved', verdict:{verdict:'upheld', refund_amount:8, confidence:.94, rationale:'Evidence <confirmed>'}}; rrRenderVerdict()`);
    const html = p.element('rrVerdict').innerHTML;
    assert.match(html, /S\$8\.00/);
    assert.match(html, /94%/);
    assert.match(html, /Evidence &lt;confirmed&gt;/);
    assert.match(html, /<details class="rr-key-details" >/);
    p.element('rrVerdict').querySelector = () => ({ open: true });
    p.run('rrRenderVerdict()');
    assert.match(p.element('rrVerdict').innerHTML, /class="rr-key-details" open/);
});

test('a dismissed rider complaint says the charge stands', () => {
    const p = page();
    p.run(`rr.detail = {dataset:{dispute_ticket:{filed_by:'rider'}, trip_data:{cancellation_fee:5}}};
        rr.result = {status:'resolved', verdict:{verdict:'dismissed', refund_amount:0, confidence:.9}}; rrRenderVerdict()`);
    const html = p.element('rrVerdict').innerHTML;
    assert.match(html, /Rider(&#39;|')s complaint dismissed/);
    assert.match(html, /S\$5\.00 cancellation fee stands/);
});

test('an upheld driver claim is labelled as the driver claim', () => {
    const p = page();
    p.run(`rr.detail = {dataset:{dispute_ticket:{filed_by:'driver'}, trip_data:{cleaning_fee_claimed:120}}};
        rr.result = {status:'resolved', verdict:{verdict:'upheld', refund_amount:null, confidence:.9}}; rrRenderVerdict()`);
    const html = p.element('rrVerdict').innerHTML;
    assert.match(html, /Driver(&#39;|')s claim upheld/);
    assert.doesNotMatch(html, /stands/);
});

test('failed and escalated runs do not display a completed ruling', () => {
    for (const status of ['failed', 'escalated_to_human']) {
        const p = page();
        p.run(`rr.result = {status:'${status}', reason:'Needs review'}; rrRenderVerdict()`);
        assert.match(p.element('rrVerdict').innerHTML, /human review/);
        assert.doesNotMatch(p.element('rrVerdict').innerHTML, /confidence/);
    }
});

test('unrecovered daily quota failure blocks a misleading resolved result', () => {
    const p = page();
    p.run(`rr.order = ['p']; rr.steps.p = {status:'done', llm:[{error:'429 rate_limit_exceeded tokens per day TPD'}]};
        rr.result = {status:'resolved', verdict:{verdict:'upheld'}}; rrRenderVerdict(); rrRenderHeader()`);
    assert.match(p.element('rrVerdict').innerHTML, /Incomplete/);
    assert.doesNotMatch(p.element('rrVerdict').innerHTML, /class="rr-conf"/);
    assert.equal(p.element('rrStatus').textContent, 'Incomplete · quota reached');
});

test('successful fallback preserves the completed verdict and debate text', () => {
    const p = page();
    p.run(`rr.order = ['p']; rr.steps.p = {id:'p', agent:'Passenger', title:'Passenger opening', status:'done',
        output:{reasoning:'Recovered analysis'}, llm:[{error:'429 rate_limit_exceeded tokens per day TPD'},
        {error:null, response:'{"reasoning":"Recovered analysis"}', provider:'groq'}]};
        rr.result = {status:'resolved', verdict:{verdict:'upheld', confidence:.9}};
        rrRenderVerdict(); rrRenderHeader(); rrRenderDebate()`);
    assert.equal(p.element('rrStatus').textContent, 'Resolved');
    assert.match(p.element('rrVerdict').innerHTML, /90%/);
    assert.match(p.element('rrDebate').innerHTML, /Recovered analysis/);
    assert.doesNotMatch(p.element('rrDebate').innerHTML, /daily token limit/);
});

test('provider capacity failure is visible even when the pipeline routes to human review', () => {
    const p = page();
    p.run(`rr.order=['j']; rr.steps.j={status:'done',output:{confidence:0},llm:[
        {error:'Error code: 413 Request too large on tokens per minute'}]};
        rr.result={status:'escalated_to_human',reason:'Arbitrator requested review'};
        rrRenderHeader(); rrRenderVerdict()`);
    assert.equal(p.element('rrStatus').textContent,'Incomplete · review error');
    assert.match(p.element('rrVerdict').innerHTML,/could not accept the full case/);
    assert.doesNotMatch(p.element('rrVerdict').innerHTML,/confidence/);
});

test('rapid selection discards the older response even when it arrives last', async () => {
    const requests = new Map();
    const p = page({apiFetch: url => new Promise(resolve => requests.set(url.split('/').pop(), resolve))});
    p.run('rrRenderAll = () => {}; rrRenderBrief = () => {}');
    const a = p.run("rrSelectCase('A')"), b = p.run("rrSelectCase('B')");
    assert.equal(p.element('rrRunBtn').disabled, true);
    requests.get('B')({ok:true, json:async () => ({dataset:{id:'B'}})});
    await b;
    requests.get('A')({ok:true, json:async () => ({dataset:{id:'A'}})});
    await a;
    assert.equal(p.run('rr.current'), 'B');
    assert.equal(p.run('rr.detail.dataset.id'), 'B');
    assert.equal(p.element('rrRunBtn').disabled, false);
});

test('a failed case load keeps the run button disabled', async () => {
    const p = page({apiFetch: async () => ({ok:false, status:404})});
    p.run('rrRenderAll = rrRenderHeader');
    await p.run("rrSelectCase('missing')");
    assert.equal(p.element('rrRunBtn').disabled, true);
    assert.equal(p.element('rrStatus').textContent, 'Case unavailable');
});

test('pipeline error persists in both status and resolution after the stream stops', () => {
    const p = page();
    p.run(`rrRenderAll = () => {}; rrHandle({type:'error', message:'Connection <lost>'});
        rrHandle({type:'done', trace_name:null}); rrSetRunning(false); rrRenderVerdict()`);
    assert.equal(p.element('rrStatus').textContent, 'Incomplete · retry required');
    assert.match(p.element('rrVerdict').innerHTML, /Connection &lt;lost&gt;/);
    assert.doesNotMatch(p.element('rrVerdict').innerHTML, /Awaiting review/);
});

test('EOF without terminal completion cannot display a completed review', async () => {
    const p = page({apiFetch: async () => ({ok:true, body:{getReader:() => ({read:async () => ({done:true}),cancel:async () => {}})}})});
    p.run(`rr.current='A'; rr.detail={dataset:{}}; rrRenderAll=rrRenderHeader; rrLoadTraces=()=>{}`);
    await p.run('rrRun()');
    assert.equal(p.element('rrStatus').textContent, 'Incomplete · retry required');
    assert.match(p.run('rr.failure'), /before the review completed/);
});

test('reporter override and replay request determine verdict labels', () => {
    const p = page();
    p.run(`rr.detail={dataset:{dispute_ticket:{filed_by:'rider'},trip_data:{cancellation_fee:5}}};
        rrRenderAll=()=>{}; rrHandle({type:'run_start',request:{reporter:'driver'}})`);
    assert.equal(p.run("rrVerdictLabel('upheld')"), "Driver's claim upheld");
    assert.equal(p.run("rrChargeStands('dismissed')"), null);
});

test('successful result still warns if saving failed', () => {
    const p = page();
    p.run(`rrRenderAll=()=>{}; rr.result={status:'resolved',verdict:{verdict:'upheld'}};
        rrHandle({type:'done',trace_name:null,trace_saved:false}); rrRenderVerdict()`);
    assert.match(p.element('rrVerdict').innerHTML, /Replay is unavailable/);
    assert.match(p.element('rrVerdict').innerHTML, /Complaint upheld/);
});

test('debate renders the full escaped transcript and selected state', () => {
    const p = page();
    p.run(`rr.order = ['p']; rr.selected = 'p'; rr.follow = false;
        rr.steps.p = {id:'p', agent:'Passenger', title:'Passenger opening', status:'done', duration:1200,
        output:{reasoning:'a'.repeat(1200) + '<tail> **Important**'}, llm:[]}; rrRenderDebate()`);
    assert.match(p.element('rrDebate').innerHTML, /a{1200}&lt;tail&gt;/);
    assert.match(p.element('rrDebate').innerHTML, /<strong>Important<\/strong>/);
    assert.match(p.element('rrDebate').innerHTML, /class="rr-party">Passenger advocate/);
    assert.match(p.element('rrDebate').innerHTML, /class="rr-turn">Opening/);
    assert.match(p.element('rrDebate').innerHTML, /aria-pressed="true"/);
});

test('completion reveals the resolution only when following the run', () => {
    for (const follow of [true, false]) {
        const p = page();
        let scrolled = false;
        p.element('rrCaseTitle').scrollIntoView = () => { scrolled = true; };
        p.run(`rrRenderAll = () => {}; rr.follow = ${follow}; rrHandle({type:'result', result:{status:'resolved'}})`);
        assert.equal(scrolled, follow);
    }
});

test('notices can be switched to another official language without a new run', async () => {
    let sent = null;
    const p = page({ apiFetch: async (url, opts) => { sent = { url, body: JSON.parse(opts.body) };
        return { ok: true, json: async () => ({ notifications: [{ recipient: 'passenger', subject: 's', message: '将向您退款 SGD 3.44。' }] }) }; } });
    p.run(`rr.current = 'DISP-001'; rr.result = {status:'resolved', verdict:{verdict:'partially_upheld', refund_amount:3.44, confidence:.9},
        execution:{notifications:[{recipient:'passenger', subject:'s', message:'SGD 3.44 will be refunded to you.'}]}}; rrRenderVerdict()`);
    assert.match(p.element('rrVerdict').innerHTML, /data-notice-lang="zh"/);
    assert.match(p.element('rrVerdict').innerHTML, /will be refunded to you/);
    await p.run(`rrNoticeLang('zh')`);
    assert.equal(sent.url, 'http://127.0.0.1:8000/api/notices');
    assert.equal(sent.body.language, 'zh');
    assert.equal(sent.body.dispute_id, 'DISP-001');
    assert.match(p.element('rrVerdict').innerHTML, /将向您退款/);
    assert.match(p.element('rrVerdict').innerHTML, /class="rr-lang on"[^>]*data-notice-lang="zh"/);
});
