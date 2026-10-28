import { DATA_ROOT, STATE_KEY, HASH, readBounded, sha256, timestamp, validateMetadata } from './data-validation.js';

export class UpdateManager {
  constructor({ storage, cache, fetcher = fetch, now = Date.now } = {}) {
    this.storage = storage;
    this.cache = cache;
    this.fetcher = fetcher.bind(globalThis);
    this.now = now;
    this.state = {};
    this.ready = this.restore();
  }

  async restore() {
    try {
      const saved = (await this.storage.get(STATE_KEY))[STATE_KEY];
      if (saved && Number.isFinite(saved.lastChecked) && saved.lastChecked <= this.now() + 300_000) {
        if (saved.active) validateMetadata(saved.active, true);
        if (saved.previous) validateMetadata(saved.previous, true);
        this.state = saved;
      }
    } catch { this.state = {}; }
  }

  async getSnapshots() {
    await this.ready;
    return [this.state.active, this.state.previous].filter(Boolean).map(meta => ({
      meta, remote: true, baseUrl: `${DATA_ROOT}snapshots/${meta.snapshotId}/`,
    }));
  }

  async request(path, limit) {
    const url = new URL(path, DATA_ROOT);
    if (!url.href.startsWith(DATA_ROOT) || url.origin !== new URL(DATA_ROOT).origin)
      throw new Error('Untrusted data URL.');
    return readBounded(await this.fetcher(url, {
      credentials: 'omit', cache: 'no-store', redirect: 'error', referrerPolicy: 'no-referrer',
      signal: AbortSignal.timeout(20_000),
    }), limit);
  }

  async check({ force = false } = {}) {
    await this.ready;
    if (this.checking) return this.checking;
    if (!force && this.now() - (this.state.lastChecked || 0) < 3_600_000) return this.state;
    this.checking = this.performCheck().finally(() => { this.checking = null; });
    return this.checking;
  }

  async performCheck() {
    const next = { ...this.state, lastChecked: this.now() };
    try {
      const pointer = JSON.parse(new TextDecoder().decode(await this.request('current.json', 2048)));
      if (pointer.schemaVersion !== 1 || !HASH.test(pointer.snapshotId) || !HASH.test(pointer.metadataSha256)
        || !Number.isSafeInteger(pointer.metadataBytes) || pointer.metadataBytes < 1 || pointer.metadataBytes > 200_000)
        throw new Error('Invalid data pointer.');
      if (pointer.snapshotId !== this.state.active?.snapshotId) {
        const raw = await this.request(`snapshots/${pointer.snapshotId}/metadata.json`, pointer.metadataBytes);
        if (raw.byteLength !== pointer.metadataBytes || await sha256(raw) !== pointer.metadataSha256)
          throw new Error('Metadata integrity check failed.');
        const meta = validateMetadata(JSON.parse(new TextDecoder().decode(raw)), true);
        if (meta.snapshotId !== pointer.snapshotId || (this.state.active
          && timestamp(meta.collectedAt) < timestamp(this.state.active.collectedAt)))
          throw new Error('Stale or mismatched snapshot.');
        next.previous = this.state.active;
        next.active = meta;
      }
      next.lastSuccess = this.now();
      next.error = null;
    } catch {
      next.error = 'Update unavailable. Keeping saved data.';
    }
    // Persist atomically before announcing the new version through storage.onChanged.
    const clean = JSON.parse(JSON.stringify(next));
    await this.storage.set({ [STATE_KEY]: clean });
    this.state = clean;
    return clean;
  }

  async readShard(snapshot, shard) {
    const url = `${snapshot.baseUrl}${shard}.json.gz`;
    const descriptor = snapshot.meta.shards[shard];
    const cache = await this.cache;
    const saved = await cache.match(url);
    if (saved) {
      const bytes = await readBounded(saved, descriptor.bytes);
      if (bytes.byteLength === descriptor.bytes && await sha256(bytes) === descriptor.sha256) return bytes;
      await cache.delete(url);
    }
    const bytes = await this.request(`snapshots/${snapshot.meta.snapshotId}/${shard}.json.gz`, descriptor.bytes);
    if (bytes.byteLength !== descriptor.bytes || await sha256(bytes) !== descriptor.sha256)
      throw new Error('Downloaded shard integrity check failed.');
    await cache.put(url, new Response(bytes));
    const keys = await cache.keys();
    for (const key of keys.slice(0, Math.max(0, keys.length - 8))) await cache.delete(key);
    return bytes;
  }
}
