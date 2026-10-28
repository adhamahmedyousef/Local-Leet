export const DATA_ROOT = 'https://adhamahmedyousef.github.io/Local-Leet/';
export const STATE_KEY = 'localLeetUpdates';
export const HASH = /^[a-f0-9]{64}$/;
export const SHARD = /^[a-f0-9]{2}$/;

export async function sha256(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    n => n.toString(16).padStart(2, '0')).join('');
}

export function timestamp(value) {
  if (typeof value !== 'string' || value.length > 50) throw new Error('Invalid snapshot date.');
  const time = Date.parse(value);
  if (!Number.isFinite(time) || time > Date.now() + 300_000) throw new Error('Invalid snapshot date.');
  return time;
}

export function validateMetadata(meta, remote = false) {
  if (!meta || meta.schemaVersion !== 1 || typeof meta.snapshotId !== 'string'
    || (remote && !HASH.test(meta.snapshotId))) throw new Error('Invalid snapshot version.');
  timestamp(meta.collectedAt);
  for (const field of ['sourceRows', 'indexedUsers', 'unknownCountryRows']) {
    if (!Number.isSafeInteger(meta[field]) || meta[field] < 0 || meta[field] > 20_000_000)
      throw new Error('Invalid snapshot counts.');
  }
  if (meta.indexedUsers > meta.sourceRows || meta.unknownCountryRows > meta.sourceRows)
    throw new Error('Inconsistent snapshot counts.');
  if (!meta.countries || !meta.shards || Array.isArray(meta.countries) || Array.isArray(meta.shards))
    throw new Error('Invalid snapshot tables.');
  let countries = 0;
  for (const [code, count] of Object.entries(meta.countries)) {
    if (!/^[A-Z]{2}$/.test(code) || !Number.isSafeInteger(count) || count < 1 || count > meta.sourceRows)
      throw new Error('Invalid country total.');
    countries += count;
  }
  if (countries + meta.unknownCountryRows !== meta.sourceRows) throw new Error('Country coverage mismatch.');
  const descriptors = Object.entries(meta.shards);
  if (!descriptors.length || descriptors.length > 256) throw new Error('Invalid shard count.');
  let entries = 0;
  for (const [key, descriptor] of descriptors) {
    if (!SHARD.test(key) || !HASH.test(descriptor?.sha256)
      || !Number.isSafeInteger(descriptor.bytes) || descriptor.bytes < 1 || descriptor.bytes > 200_000
      || !Number.isSafeInteger(descriptor.entries) || descriptor.entries < 0 || descriptor.entries > 30_000)
      throw new Error('Invalid shard descriptor.');
    entries += descriptor.entries;
  }
  if (entries !== meta.indexedUsers) throw new Error('Indexed profile count mismatch.');
  return meta;
}

export async function readBounded(response, limit) {
  if (!response.ok) throw new Error(`Data request failed: HTTP ${response.status}`);
  if (Number(response.headers?.get('content-length')) > limit) throw new Error('Oversized data response.');
  if (!response.body) throw new Error('Empty data response.');
  const reader = response.body.getReader();
  const chunks = [];
  let length = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > limit) throw new Error('Oversized data response.');
      chunks.push(value);
    }
  } catch (error) { await reader.cancel().catch(() => {}); throw error; }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return bytes;
}

export async function validateShard(bytes, descriptor, meta) {
  if (bytes.byteLength !== descriptor.bytes || await sha256(bytes) !== descriptor.sha256)
    throw new Error('Ranking data integrity check failed.');
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  const plain = await readBounded(new Response(stream), 3_000_000);
  const entries = JSON.parse(new TextDecoder().decode(plain));
  if (!entries || Array.isArray(entries) || typeof entries !== 'object'
    || Object.keys(entries).length !== descriptor.entries) throw new Error('Invalid shard contents.');
  for (const [key, row] of Object.entries(entries)) {
    if (!/^(US:|CN-SLUG:)[^\s/\\\x00-\x1f]{1,100}$/u.test(key) || !Array.isArray(row) || row.length !== 4
      || !Number.isSafeInteger(row[0]) || row[0] < 1 || row[0] > meta.sourceRows
      || typeof row[3] !== 'string' || row[3].length > 50 || !Number.isFinite(Number(row[3])))
      throw new Error('Invalid profile row.');
    if (row[2] === null) {
      if (row[1] !== null) throw new Error('Unknown-country rank was fabricated.');
    } else if (typeof row[2] !== 'string' || !Object.hasOwn(meta.countries, row[2]) || !Number.isSafeInteger(row[1])
      || row[1] < 1 || row[1] > meta.countries[row[2]]) throw new Error('Invalid country rank.');
  }
  return entries;
}
