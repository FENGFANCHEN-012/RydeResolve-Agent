const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function page(fetchImpl = async () => ({ok:true, json:async () => ({})}), origin = 'http://127.0.0.1:8000') {
    const elements = new Map();
    const create = () => ({innerHTML:'', textContent:'', style:{}, children:[],
        classList:{add(){}, remove(){}, toggle(){}}, addEventListener(){},
        appendChild(child){this.children.push(child);}, remove(){}, focus(){}, value:'',
        scrollHeight:0, scrollTop:0});
    const element = id => {if (!elements.has(id)) elements.set(id, create()); return elements.get(id);};
    const context = vm.createContext({document:{getElementById:element,createElement:create},
        window:{prompt:() => null}, location:{protocol:'http:', origin,search:''},
        URLSearchParams, AbortSignal, fetch:fetchImpl, setTimeout(){}, console});
    const html = fs.readFileSync(path.join(__dirname,'../frontend/index.html'),'utf8');
    const script = html.slice(html.indexOf('<script>')+8,html.indexOf('</script>'));
    vm.runInContext(script.slice(0,script.lastIndexOf('\ncheckServerStatus();')),context);
    return {element, run:code => vm.runInContext(code,context)};
}

test('chat preserves user and model markup as plain text and escapes sources',() => {
    const p = page();
    for (const role of ['user','assistant']) p.run(`addMessage('<img src=x onerror=alert(1)>\nsecond line','${role}',
        [{source:'<svg onload=alert(2)>',similarity:.02,clause:'<script>x</script>'}])`.replace(/\nsecond/, '\\nsecond'));
    const messages = p.element('chatContainer').children;
    assert.equal(messages.length,2);
    for (const msg of messages) {
        assert.equal(msg.children[0].textContent,'<img src=x onerror=alert(1)>\nsecond line');
        assert.equal(msg.children[0].innerHTML,'');
        const sourceHeader=msg.children[1].children[1].children[0].innerHTML;
        assert.match(sourceHeader,/&lt;svg/);
        assert.doesNotMatch(sourceHeader,/<svg|2\.0%/);
        assert.match(sourceHeader,/Relevance 0\.0200/);
    }
});

test('failed delete does not announce success or erase the file list',async () => {
    const p = page(async () => ({ok:false,status:403,json:async () => ({detail:'Admin access required'})}));
    p.run(`confirm=()=>true; uploadedFiles=[{name:'keep.txt',status:'ok'}]; lastToast=null; showToast=(message)=>{lastToast=message}`);
    await p.run('clearCollection()');
    assert.equal(p.run('uploadedFiles.length'),1);
    assert.equal(p.run('lastToast'),'Error: Admin access required');
});

test('source metadata and search errors cannot inject markup',async () => {
    const p = page(async () => ({ok:true,json:async () => ({results:[{source:'<img src=x>',file_type:'<svg>',clause:'<tag>',similarity:.016}]})}));
    p.element('searchInput').value='query';
    await p.run('searchChunks()');
    assert.match(p.element('searchResults').innerHTML,/&lt;img/);
    assert.match(p.element('searchResults').innerHTML,/&lt;svg/);
    assert.doesNotMatch(p.element('searchResults').innerHTML,/<img|<svg|1\.6%/);
});

test('same-origin serving avoids asking visitors to connect to their own localhost',() => {
    assert.equal(page().run('API_BASE'),'http://127.0.0.1:8000');
    assert.equal(page(undefined,'https://demo.example').run('API_BASE'),'https://demo.example');
});

test('a late 401 from a request sent before the code was entered keeps the code',async () => {
    // Live 2026-10-13: the case list kept failing with 401 after a correct code, because a
    // page-load request answered 401 after the code was set and cleared it
    let releaseSlow;
    const slow = new Promise(r => { releaseSlow = r; });
    const fetchImpl = async (url, opts) => {
        const auth = (opts.headers || {}).Authorization;
        if (url === '/api/slow' && !auth) await slow;
        return auth === 'Bearer good' ? {ok:true,status:200,json:async () => ({})}
            : {ok:false,status:401,json:async () => ({})};
    };
    const p = page(fetchImpl);
    p.run(`window.prompt=()=>'good'`);
    const slowReq = p.run("apiFetch('/api/slow')");
    assert.equal((await p.run("apiFetch('/api/fast')")).status, 200);
    releaseSlow();
    assert.equal((await slowReq).status, 200);
    assert.equal(p.run('apiToken'), 'good');
});

test('cancelled access-code prompt does not repeat during background retries',async () => {
    const p = page(async () => ({ok:false,status:401,json:async () => ({detail:'Access required'})}));
    p.run(`prompts=0; window.prompt=()=>{prompts++;return null}`);
    await p.run("Promise.all([apiFetch('/api/a'),apiFetch('/api/b')])");
    await p.run("apiFetch('/api/a')");
    assert.equal(p.run('prompts'),1);
});
