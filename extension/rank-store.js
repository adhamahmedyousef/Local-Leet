import { readBounded, sha256, validateMetadata, validateShard } from './data-validation.js';

/** Pinned snapshots, bounded worker caches, and a bundled offline fallback. */
export class RankStore {
  constructor(baseUrl, { fetcher = fetch, cacheSize = 4, updates = null } = {}) {
    this.baseUrl = baseUrl;
    this.fetcher = fetcher.bind(globalThis);
    this.cacheSize = cacheSize;
    this.updates = updates;
    this.shards = new Map();
  }

  async metadata() {
    if (!this.meta) {
      this.meta = this.fetcher(new URL('metadata.json', this.baseUrl)).then(async response =>
        validateMetadata(JSON.parse(new TextDecoder().decode(await readBounded(response, 200_000)))))
        .catch(error => { this.meta = null; throw error; });
    }
    return this.meta;
  }

  async lookup(username, region) {
    if (typeof username !== 'string' || !username || username.length > 100
      || /[\s/\\\x00-\x1f]/u.test(username) || !['US', 'CN'].includes(region))
      throw new Error('Invalid profile.');
    const key = `${region === 'CN' ? 'CN-SLUG' : 'US'}:${username}`;
    const shard = (await sha256(new TextEncoder().encode(key))).slice(0, 2);
    const bundled = await this.metadata();
    const remote = this.updates ? await this.updates.getSnapshots() : [];
    const snapshots = remote.filter(s => Date.parse(s.meta.collectedAt) >= Date.parse(bundled.collectedAt));
    snapshots.push({ meta: bundled, baseUrl: this.baseUrl, remote: false });
    let lastError;
    for (const snapshot of snapshots) {
      try { return await this.lookupSnapshot(username, region, key, shard, snapshot); }
      catch (error) { lastError = error; }
    }
    throw lastError;
  }

  async lookupSnapshot(username, region, key, shard, snapshot) {
    const meta = snapshot.meta;
    const descriptor = meta.shards[shard];
    const envelope = { snapshotId: meta.snapshotId, collectedAt: meta.collectedAt,
      sourceRows: meta.sourceRows, unknownCountryRows: meta.unknownCountryRows,
      dataSource: snapshot.remote ? 'updated' : 'bundled' };
    if (!descriptor) return { ...envelope, user: null };
    const cacheKey = `${meta.snapshotId}:${shard}`;
    let pending = this.shards.get(cacheKey);
    if (pending) {
      this.shards.delete(cacheKey);
      this.shards.set(cacheKey, pending);
    } else {
      pending = (async () => {
        const bytes = snapshot.remote ? await this.updates.readShard(snapshot, shard)
          : await readBounded(await this.fetcher(new URL(`${shard}.json.gz`, snapshot.baseUrl)), descriptor.bytes);
        return validateShard(bytes, descriptor, meta);
      })();
      this.shards.set(cacheKey, pending);
      if (this.shards.size > this.cacheSize) this.shards.delete(this.shards.keys().next().value);
    }
    let entries;
    try { entries = await pending; }
    catch (error) { this.shards.delete(cacheKey); throw error; }
    const row = Object.hasOwn(entries, key) ? entries[key] : null;
    return { ...envelope, user: row ? { username, region, globalRank: row[0],
      localRank: row[1], country: row[2], rating: row[3],
      countryTotal: row[2] ? meta.countries[row[2]] : null } : null };
  }
}
