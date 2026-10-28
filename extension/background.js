import { RankStore } from './rank-store.js';
import { UpdateManager } from './update-manager.js';

const updates = new UpdateManager({ storage: chrome.storage.local,
  cache: caches.open('local-leet-verified-shards-v1') });
const store = new RankStore(chrome.runtime.getURL('data/'), { updates });

async function start() {
  if (!await chrome.alarms.get('local-leet-check'))
    await chrome.alarms.create('local-leet-check', { periodInMinutes: 60 });
  await updates.check();
}
chrome.runtime.onInstalled.addListener(() => { void start().catch(() => {}); });
chrome.runtime.onStartup.addListener(() => { void start().catch(() => {}); });
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === 'local-leet-check') void updates.check().catch(() => {});
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return;
  const page = /^https:\/\/(www\.)?leetcode\.(com|cn)\//.test(sender.url || '');
  const popup = sender.url === chrome.runtime.getURL('popup.html');
  let operation;
  if (message?.type === 'LOCAL_LEET_LOOKUP' && page) {
    operation = store.lookup(message.username, message.region);
    void updates.check().catch(() => {});
  } else if (message?.type === 'LOCAL_LEET_STATUS' && popup) {
    operation = updates.ready.then(async () => ({ ...updates.state, bundled: await store.metadata() }));
  } else if (message?.type === 'LOCAL_LEET_CHECK' && popup) {
    operation = updates.check({ force: true });
  } else return;
  operation.then(result => sendResponse({ ok: true, result }))
    .catch(() => sendResponse({ ok: false, error: 'Ranking data is unavailable. Saved data was preserved.' }));
  return true;
});
void start().catch(() => {});
