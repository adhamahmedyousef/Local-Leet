import test from 'node:test';
import assert from 'node:assert/strict';
import { gzipSync } from 'node:zlib';
import { UpdateManager } from '../extension/update-manager.js';
import { DATA_ROOT, STATE_KEY, sha256, validateMetadata } from '../extension/data-validation.js';
import { RankStore } from '../extension/rank-store.js';

async function snapshot(letter, localRank = 10, date = '2026-10-28T10:00:00Z') {
  const key = 'US:alice';
  const shard = (await sha256(new TextEncoder().encode(key))).slice(0, 2);
  const gz = gzipSync(JSON.stringify({ [key]: [20, localRank, 'EG', '1700'] }));
  const meta = { schemaVersion: 1, snapshotId: letter.repeat(64), collectedAt: date,
    sourceRows: 100, indexedUsers: 1, unknownCountryRows: 0, countries: { EG: 100 },
    shards: { [shard]: { bytes: gz.length, entries: 1, sha256: await sha256(gz) } } };
  const raw = new TextEncoder().encode(JSON.stringify(meta));
  const pointer = { schemaVersion: 1, snapshotId: meta.snapshotId,
    metadataBytes: raw.length, metadataSha256: await sha256(raw) };
  return { shard, gz, meta, raw, pointer };
}

function platform(initial = {}) {
  let saved = structuredClone(initial);
  const entries = new Map();
  const storage = { get: async () => structuredClone(saved), set: async value => { saved = structuredClone(value); } };
  const cache = { match: async key => entries.has(String(key)) ? new Response(entries.get(String(key))) : undefined,
    put: async (key, response) => { entries.set(String(key), await response.arrayBuffer()); },
    delete: async key => entries.delete(String(key)), keys: async () => [...entries.keys()] };
  return { storage, cache, saved: () => saved, entries };
}

function network(state) {
  const calls = [];
  const fetcher = async (url, options) => {
    calls.push({ url: String(url), options });
    if (state.offline) throw new Error('Offline');
    if (String(url) === DATA_ROOT + 'current.json') return Response.json(state.pointer || state.current.pointer);
    const item = state.versions.find(s => String(url).includes(s.meta.snapshotId));
    if (!item) return new Response('', { status: 404 });
    if (String(url).endsWith('metadata.json')) return new Response(state.badMetadata || item.raw);
    return new Response(state.badShard || item.gz);
  };
  return { fetcher, calls };
}

test('first update verifies metadata and a second version replaces it atomically', async () => {
  const a = await snapshot('a'), b = await snapshot('b', 9, '2026-10-28T10:01:00Z');
  const state = { current: a, versions: [a, b] }, p = platform(), n = network(state);
  const manager = new UpdateManager({ ...p, fetcher: n.fetcher });
  await manager.check({ force: true });
  assert.equal(p.saved()[STATE_KEY].active.snapshotId, a.meta.snapshotId);
  state.current = b;
  await manager.check({ force: true });
  assert.equal(p.saved()[STATE_KEY].active.snapshotId, b.meta.snapshotId);
  assert.equal(p.saved()[STATE_KEY].previous.snapshotId, a.meta.snapshotId);
  assert.ok(n.calls.every(c => c.url.startsWith(DATA_ROOT) && !c.url.includes('alice')));
  assert.ok(n.calls.every(c => c.options.credentials === 'omit' && c.options.redirect === 'error'));
});

test('same-version checks download only the small pointer and honor the one-hour cooldown', async () => {
  const a = await snapshot('a'), p = platform(), n = network({ current: a, versions: [a] });
  const manager = new UpdateManager({ ...p, fetcher: n.fetcher });
  await manager.check({ force: true });
  const reads = n.calls.length;
  await manager.check();
  assert.equal(n.calls.length, reads);
  await manager.check({ force: true });
  assert.equal(n.calls.length, reads + 1);
});

test('corrupt metadata, oversized metadata and rollback pointers preserve the last valid version', async () => {
  const a = await snapshot('a'), b = await snapshot('b', 9, '2026-10-27T10:00:00Z');
  const state = { current: a, versions: [a, b] }, p = platform(), n = network(state);
  const manager = new UpdateManager({ ...p, fetcher: n.fetcher });
  await manager.check({ force: true });
  state.current = b;
  for (const mode of ['rollback', 'corrupt', 'oversized']) {
    state.badMetadata = mode === 'corrupt' ? new TextEncoder().encode('bad') : undefined;
    state.pointer = mode === 'oversized' ? { ...b.pointer, metadataBytes: 1_000_000 } : undefined;
    await manager.check({ force: true });
    assert.equal(manager.state.active.snapshotId, a.meta.snapshotId);
    assert.ok(manager.state.error);
  }
});

test('verified shard cache survives worker restart and supports offline reads', async () => {
  const a = await snapshot('a'), p = platform(), state = { current: a, versions: [a] }, n = network(state);
  let manager = new UpdateManager({ ...p, fetcher: n.fetcher });
  await manager.check({ force: true });
  const [version] = await manager.getSnapshots();
  await manager.readShard(version, a.shard);
  const requests = n.calls.length;
  state.offline = true;
  manager = new UpdateManager({ ...p, fetcher: n.fetcher });
  const [restored] = await manager.getSnapshots();
  assert.deepEqual(Buffer.from(await manager.readShard(restored, a.shard)), Buffer.from(a.gz));
  assert.equal(n.calls.length, requests);
});

test('offline checks without an active version retain their cooldown across restart', async () => {
  const p = platform(), state = { offline: true }, n = network(state);
  let manager = new UpdateManager({ ...p, fetcher: n.fetcher });
  await manager.check();
  manager = new UpdateManager({ ...p, fetcher: n.fetcher });
  await manager.check();
  assert.equal(n.calls.length, 1);
});

test('remote data updates the result, then network failure falls back to the bundled snapshot', async () => {
  const local = await snapshot('a', 10), remote = await snapshot('b', 9, '2026-10-28T10:01:00Z');
  const state = { current: remote, versions: [remote] }, p = platform(), n = network(state);
  const manager = new UpdateManager({ ...p, fetcher: n.fetcher });
  const bundled = async url => new Response(String(url).endsWith('metadata.json') ? local.raw : local.gz);
  const store = new RankStore('https://bundled.invalid/', { fetcher: bundled, updates: manager });
  assert.equal((await store.lookup('alice', 'US')).user.localRank, 10);
  await manager.check({ force: true });
  assert.equal((await store.lookup('alice', 'US')).user.localRank, 9);
  assert.equal((await store.lookup('alice', 'US')).snapshotId, remote.meta.snapshotId);
  state.offline = true;
  p.entries.clear(); store.shards.clear();
  const fallback = await store.lookup('alice', 'US');
  assert.equal(fallback.user.localRank, 10);
  assert.equal(fallback.dataSource, 'bundled');
  assert.equal(fallback.snapshotId, local.meta.snapshotId);
});

test('remote shard corruption never renders the unverified rank', async () => {
  const local = await snapshot('a', 10), remote = await snapshot('b', 9);
  const p = platform(), state = { current: remote, versions: [remote], badShard: new Uint8Array([1,2,3]) }, n = network(state);
  const manager = new UpdateManager({ ...p, fetcher: n.fetcher });
  await manager.check({ force: true });
  const store = new RankStore('https://bundled.invalid/', { updates: manager,
    fetcher: async url => new Response(String(url).endsWith('metadata.json') ? local.raw : local.gz) });
  assert.equal((await store.lookup('alice', 'US')).user.localRank, 10);
  assert.equal(p.entries.size, 0);
});

test('metadata rejects invented unknown-country totals and non-hash remote versions', async () => {
  const a = await snapshot('a');
  assert.throws(() => validateMetadata({ ...a.meta, unknownCountryRows: 1 }, true), /coverage/);
  assert.throws(() => validateMetadata({ ...a.meta, snapshotId: '../evil' }, true), /version/);
});
