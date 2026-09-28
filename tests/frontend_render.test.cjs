// Run with: node --test tests/frontend_render.test.cjs (no dependencies).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function page() {
    const elements = new Map();
    const element = id => {
        if (!elements.has(id)) elements.set(id, {
            innerHTML: '', textContent: '', hidden: false,
            querySelector: () => null,
            addEventListener() {}, scrollIntoView() {},
        });
        return elements.get(id);
    };
    const context = vm.createContext({
        document: { getElementById: element },
        window: { addEventListener() {} },
        requestAnimationFrame() {},
        showToast() {},
    });
    const source = fs.readFileSync(path.join(__dirname, '../frontend/dispute.js'), 'utf8');
    // Bootstrap is browser-only; exercise the actual render functions below.
    vm.runInContext(source.slice(0, source.indexOf("window.addEventListener('resize'")), context);
    return { element, run: code => vm.runInContext(code, context) };
}

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
    p.run(`rr.detail = {dispute_ticket:{filed_by:'rider'}, trip_data:{cancellation_fee:5}};
        rr.result = {status:'resolved', verdict:{verdict:'dismissed', refund_amount:0, confidence:.9}}; rrRenderVerdict()`);
    const html = p.element('rrVerdict').innerHTML;
    assert.match(html, /Rider(&#39;|')s complaint dismissed/);
    assert.match(html, /S\$5\.00 cancellation fee stands/);
});

test('an upheld driver claim is labelled as the driver claim', () => {
    const p = page();
    p.run(`rr.detail = {dispute_ticket:{filed_by:'driver'}, trip_data:{cleaning_fee_claimed:120}};
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

test('daily quota failure overrides an otherwise resolved result and header', () => {
    const p = page();
    p.run(`rr.order = ['p']; rr.steps.p = {status:'done', llm:[{error:'429 rate_limit_exceeded tokens per day TPD'}]};
        rr.result = {status:'resolved', verdict:{verdict:'upheld'}}; rrRenderVerdict(); rrRenderHeader()`);
    assert.match(p.element('rrVerdict').innerHTML, /Incomplete/);
    assert.doesNotMatch(p.element('rrVerdict').innerHTML, /class="rr-conf"/);
    assert.equal(p.element('rrStatus').textContent, 'Incomplete · quota reached');
});

test('debate renders the full escaped transcript and selected state', () => {
    const p = page();
    p.run(`rr.order = ['p']; rr.selected = 'p'; rr.follow = false;
        rr.steps.p = {id:'p', agent:'Passenger', title:'Passenger opening', status:'done', duration:1200,
        output:{reasoning:'a'.repeat(1200) + '<tail>'}, llm:[]}; rrRenderDebate()`);
    assert.match(p.element('rrDebate').innerHTML, /a{1200}&lt;tail&gt;/);
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
