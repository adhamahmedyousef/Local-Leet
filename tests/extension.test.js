import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import { JSDOM } from 'jsdom';
import { RankStore } from '../extension/rank-store.js';

const core = await readFile(new URL('../extension/profile-core.js', import.meta.url), 'utf8');
const content = await readFile(new URL('../extension/content.js', import.meta.url), 'utf8');
const version = JSON.parse(await readFile(new URL('../extension/manifest.json', import.meta.url))).version;
const packageRoot = resolve(`dist/local-leet-${version}`);
const hasPackage = existsSync(resolve(packageRoot, 'data/metadata.json'));
async function expectedProfile(name) {
  const key = `US:${name}`;
  const shard = createHash('sha256').update(key).digest('hex').slice(0, 2);
  return JSON.parse(gunzipSync(await readFile(resolve(packageRoot, `data/${shard}.json.gz`))))[key];
}
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const user = { username: 'Adham0X1Star', region: 'US', country: 'EG', globalRank: 108215,
  localRank: 230, countryTotal: 1461, rating: '1724.845' };
const result = { user, collectedAt: '2026-10-28T08:56:44Z' };
const header = () => `<main id="main-content"><aside>Rank <b>4,439</b></aside><section>
  <div class="align-start flex w-full"><div class="mr-4"><div>Contest Rating</div><div>1,725</div></div>
  <div class="mr-4"><div class="label">Global Ranking</div><div class="value">108,215<span class="muted">/889,290</span></div></div>
  <div><div>Attended</div><div>45</div></div></div><div id="chart"></div></section></main>`;

function fixture(t, { response = async () => ({ ok: true, result }), url } = {}) {
  const dom = new JSDOM(header(), { url: url || 'https://leetcode.com/u/Adham0X1Star/',
    runScripts: 'outside-only', pretendToBeVisual: true });
  const calls = [];
  const storageListeners = [];
  dom.window.chrome = { storage: { onChanged: { addListener: callback => storageListeners.push(callback) } } };
  dom.window.chrome.runtime = { sendMessage: message => { calls.push(message); return response(message); } };
  dom.window.eval(core);
  dom.window.eval(content);
  t.after(() => { dom.window.dispatchEvent(new dom.window.Event('pagehide')); dom.window.close(); });
  return { dom, window: dom.window, document: dom.window.document, calls, storageListeners };
}

test('inserts one native-style rank beside Global Ranking without changing sidebar rank', async t => {
  const { document, calls } = fixture(t);
  await wait(100);
  const badge = document.querySelector('[data-local-leet="rank"]');
  assert.equal(badge.previousElementSibling.firstElementChild.textContent, 'Global Ranking');
  assert.equal(badge.nextElementSibling.firstElementChild.textContent, 'Attended');
  assert.equal(badge.querySelector('[data-ll-number]').textContent, '230');
  assert.equal(badge.querySelector('.muted').textContent, '/1,461');
  assert.equal(document.querySelector('aside b').textContent, '4,439');
  assert.equal(calls.length, 1);
});

test('details are clickable, keyboard dismissible, and explain the snapshot scope', async t => {
  const { document, window } = fixture(t);
  await wait(100);
  const button = document.querySelector('.ll-rank-button');
  button.click();
  const details = document.querySelector('.ll-details');
  assert.equal(details.hidden, false);
  assert.match(details.textContent, /28 Oct 2026/);
  assert.match(details.textContent, /declaring that country/);
  assert.match(button.title, /updated daily/);
  assert.match(details.textContent, /updated daily/);
  assert.equal(button.getAttribute('aria-expanded'), 'true');
  document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }));
  assert.equal(details.hidden, true);
  assert.equal(document.activeElement, button);
});

for (const level of ['Knight', 'Guardian']) test(`${level} layout preserves native nodes and restores inline placement after resize`, t => {
  const dom = new JSDOM(`<main><section id="card"><div id="pane"><div><div><div id="row">
    <div>Contest Rating</div><div id="badge"><img alt="contest badge"></div><div id="level">Level ${level}</div>
    <div id="global"><div>Global Ranking</div><div>2<span>/889,290</span></div></div><div>Attended</div>
    </div></div><div class="rating-contest-graph"></div></div></div><div id="divider"></div>
    <div id="top" style="min-width:200px">Top 0.01%</div></section></main>`, { runScripts: 'outside-only' });
  t.after(() => dom.window.close());
  const { document } = dom.window;
  dom.window.eval(core);
  const api = dom.window.LocalLeetProfile;
  const anchor = api.locateGlobalRank(document);
  const native = ['badge', 'level'].map(id => document.getElementById(id));
  const graph = document.querySelector('.rating-contest-graph');
  const graphParent = graph.parentElement;
  let rowWidth = 380;
  anchor.row.getBoundingClientRect = () => ({ width: rowWidth });
  for (const node of anchor.row.children) node.getBoundingClientRect = () => ({ width: 70 });
  document.getElementById('divider').getBoundingClientRect = () => ({ width: 33 });
  const card = document.getElementById('card');
  Object.defineProperty(card, 'clientWidth', { configurable: true, value: 836 });
  const view = api.createRank(document, anchor, () => {});
  view.host.getBoundingClientRect = () => ({ width: 100 });
  api.updateRank(view, api.describe(result, 108215));
  assert.equal(view.host.dataset.llPlacement, 'inline');
  assert.equal(card.style.getPropertyValue('--ll-stats-width'), '450px');
  Object.defineProperty(card, 'clientWidth', { configurable: true, value: 500 });
  api.layoutRank(view);
  assert.equal(view.host.dataset.llPlacement, 'compact');
  assert.equal(view.host.parentElement, anchor.block);
  assert.equal(api.readGlobalRank(anchor), 2);
  rowWidth = 700;
  api.layoutRank(view);
  assert.equal(view.host.parentElement, anchor.row);
  for (const node of native) assert.equal(node.parentElement, anchor.row);
  assert.equal(graph.parentElement, graphParent);
  api.destroyRank(view);
  assert.equal(document.querySelector('[data-local-leet]'), null);
  assert.equal(anchor.row.hasAttribute('data-local-leet-row'), false);
  assert.equal(card.style.getPropertyValue('--ll-stats-width'), '');
});

test('unknown country and missing user never fabricate a rank', async t => {
  const { document, window } = fixture(t);
  const api = window.LocalLeetProfile;
  assert.equal(api.describe({ ...result, user: { ...user, country: null } }, 108215).number, '—');
  assert.equal(api.describe({ ...result, user: { ...user, country: null } }, 1).stale, false);
  assert.equal(api.describe({ ...result, user: null }, 108215).state, 'missing');
  assert.equal(api.describe(null, 108215).state, 'loading');
  assert.equal(api.profileIdentity('https://leetcode.com/problems/two-sum/'), null);
  assert.equal(api.profileIdentity('https://evil.test/u/name/'), null);
  assert.equal(document.querySelectorAll('[data-local-leet]').length, 0);
});

test('source-rank changes mark the saved rank without re-querying or pretending to recalculate', async t => {
  const { document, calls } = fixture(t);
  await wait(100);
  document.querySelector('.value').firstChild.textContent = '108,214';
  await wait(100);
  const badge = document.querySelector('.ll-rank');
  assert.equal(badge.dataset.stale, 'true');
  assert.equal(badge.querySelector('[data-ll-number]').textContent, '230');
  badge.querySelector('button').click();
  assert.match(document.querySelector('.ll-details').textContent, /global rank has changed/);
  assert.equal(calls.length, 1);
});

test('React-style badge removal restores it without duplicate requests', async t => {
  const { document, calls } = fixture(t);
  await wait(100);
  document.querySelector('.ll-rank').remove();
  await wait(100);
  assert.equal(document.querySelectorAll('.ll-rank').length, 1);
  assert.equal(calls.length, 1);
});

test('native graph updates cannot swap the global and local rank', async t => {
  const { document, calls } = fixture(t);
  await wait(100);
  const global = document.querySelector('.label').parentElement;
  const local = document.querySelector('.ll-rank');
  global.before(local);
  document.querySelector('#chart').textContent = 'hover';
  await wait(150);
  assert.equal(global.nextElementSibling, local);
  assert.equal(calls.length, 1);
});

test('React can clear the injected host without permanently hiding the rank', async t => {
  const { document, calls } = fixture(t);
  await wait(100);
  document.querySelector('.ll-rank').replaceChildren();
  await wait(150);
  assert.equal(document.querySelector('[data-ll-number]').textContent, '230');
  assert.equal(document.querySelectorAll('.ll-rank').length, 1);
  assert.equal(calls.length, 1);
});

test('hover switches rank to the visible duplicate header and restores it on leave', async t => {
  const { document, calls } = fixture(t);
  await wait(100);
  const original = document.querySelector('[data-local-leet-row]');
  const alternate = original.cloneNode(true);
  alternate.querySelector('.ll-rank').remove();
  alternate.style.display = 'none';
  original.after(alternate);
  original.style.display = 'none';
  alternate.style.display = 'flex';
  await wait(150);
  assert.ok(alternate.querySelector('.ll-rank'));
  original.style.display = 'flex';
  alternate.style.display = 'none';
  await wait(150);
  assert.ok(original.querySelector('.ll-rank'));
  assert.equal(document.querySelectorAll('.ll-rank').length, 1);
  assert.equal(calls.length, 1);
});

test('unrelated chart mutations do not scan the profile or fetch new data', async t => {
  const { document, calls } = fixture(t);
  await wait(100);
  let scans = 0;
  const original = document.createTreeWalker.bind(document);
  document.createTreeWalker = (...args) => { scans++; return original(...args); };
  for (let i = 0; i < 200; i++) document.querySelector('#chart').textContent = String(i);
  await wait(100);
  assert.equal(scans, 0);
  assert.equal(calls.length, 1);
});

test('SPA navigation discards old responses and requests the new profile once', async t => {
  let resolveOld;
  const { dom, document, calls } = fixture(t, { response: message => message.username === 'Adham0X1Star'
    ? new Promise(resolve => { resolveOld = resolve; })
    : Promise.resolve({ ok: true, result: { ...result, user: { ...user, localRank: 7 } } }) });
  await wait(100);
  dom.reconfigure({ url: 'https://leetcode.com/u/another/' });
  document.body.innerHTML = header();
  await wait(100);
  resolveOld({ ok: true, result });
  await wait(30);
  assert.equal(document.querySelector('[data-ll-number]').textContent, '7');
  assert.equal(calls.length, 2);
});

test('non-profile pages make no lookup request', async t => {
  const { document, calls } = fixture(t, { url: 'https://leetcode.com/problems/two-sum/' });
  await wait(100);
  assert.equal(calls.length, 0);
  assert.equal(document.querySelector('.ll-rank'), null);
});

test('worker failures render a clear unavailable state', async t => {
  const { document } = fixture(t, { response: async () => { throw new Error('Worker stopped'); } });
  await wait(100);
  assert.equal(document.querySelector('.ll-rank').dataset.state, 'error');
  assert.equal(document.querySelector('[data-ll-number]').textContent, '—');
});

test('real packaged dataset supports offline US/CN lookups and stays in a four-shard memory budget', { skip: !hasPackage }, async () => {
  let reads = 0;
  const base = pathToFileURL(resolve(packageRoot, 'data') + '/');
  const fetcher = async url => { reads++; return new Response(await readFile(url)); };
  const store = new RankStore(base, { fetcher });
  const egypt = await store.lookup('Adham0X1Star', 'US');
  assert.equal(egypt.user.localRank, (await expectedProfile('Adham0X1Star'))[1]);
  assert.equal(egypt.user.country, 'EG');
  assert.equal(reads, 2);
  await store.lookup('Adham0X1Star', 'US');
  assert.equal(reads, 2);
  assert.ok((await store.lookup('Yawn_Sean', 'CN')).user);
  for (const name of ['neal_wu', 'fjzzq2002', 'numb3r5', 'fmota', 'lev_mark']) await store.lookup(name, 'US');
  assert.ok(store.shards.size <= 4);
  await assert.rejects(store.lookup('../secret', 'US'), /Invalid/);
});

test('worker messages validate sender/action and native fetch receives the correct global receiver', { skip: !hasPackage }, async () => {
  const oldChrome = globalThis.chrome;
  const oldFetch = globalThis.fetch;
  const oldCaches = globalThis.caches;
  let listener;
  globalThis.chrome = { runtime: { id: 'local-leet-test',
    getURL: path => pathToFileURL(resolve(packageRoot, path) + (path.endsWith('/') ? '/' : '')).href,
    onInstalled: { addListener() {} }, onStartup: { addListener() {} },
    onMessage: { addListener: callback => { listener = callback; } } },
    alarms: { get: async () => ({}), create: async () => {}, onAlarm: { addListener() {} } },
    storage: { local: { get: async () => ({ localLeetUpdates: { lastChecked: Date.now() } }), set: async () => {} } } };
  globalThis.caches = { open: async () => ({ match: async () => undefined }) };
  globalThis.fetch = async function (url) {
    assert.equal(this, globalThis, 'Browser native fetch must not be called with the store as receiver');
    return new Response(await readFile(url));
  };
  try {
    await import('../extension/background.js');
    const message = { type: 'LOCAL_LEET_LOOKUP', username: 'Adham0X1Star', region: 'US' };
    const sender = { id: 'local-leet-test', url: 'https://leetcode.com/u/Adham0X1Star/' };
    const response = await new Promise(resolve => {
      assert.equal(listener(message, sender, resolve), true);
    });
    assert.equal(response.ok, true, response.error);
    assert.equal(response.result.user.localRank, (await expectedProfile('Adham0X1Star'))[1]);
    assert.equal(listener(message, { ...sender, id: 'other-extension' }, () => {}), undefined);
    assert.equal(listener(message, { ...sender, url: 'https://evil.test/' }, () => {}), undefined);
    assert.equal(listener({ type: 'OTHER' }, sender, () => {}), undefined);
    const invalid = await new Promise(resolve => listener({ ...message, username: '../x' }, sender, resolve));
    assert.equal(invalid.ok, false);
  } finally {
    globalThis.chrome = oldChrome;
    globalThis.fetch = oldFetch;
    globalThis.caches = oldCaches;
  }
});

test('a newly published storage version updates an open profile without reloading the document', async t => {
  let localRank = 230;
  const { document, calls, storageListeners, window } = fixture(t, {
    response: async () => ({ ok: true, result: { ...result, user: { ...user, localRank } } }),
  });
  await wait(100);
  const originalDocument = document;
  localRank = 229;
  storageListeners[0]({ localLeetUpdates: { oldValue: { active: { snapshotId: 'old' } },
    newValue: { active: { snapshotId: 'new' } } } }, 'local');
  await wait(100);
  assert.equal(window.document, originalDocument);
  assert.equal(document.querySelector('[data-ll-number]').textContent, '229');
  assert.equal(calls.length, 2);
  storageListeners[0]({ localLeetUpdates: { oldValue: { active: { snapshotId: 'new' } },
    newValue: { active: { snapshotId: 'new' }, lastChecked: Date.now() } } }, 'local');
  await wait(80);
  assert.equal(calls.length, 2);
});
