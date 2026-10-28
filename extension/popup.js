const date = value => value ? new Date(value).toLocaleDateString('en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
}) : 'Not yet';
async function render() {
  const response = await chrome.runtime.sendMessage({ type: 'LOCAL_LEET_STATUS' });
  if (!response?.ok) throw new Error('Status unavailable');
  const state = response.result;
  const meta = state.active || state.bundled;
  document.querySelector('#snapshot').textContent = date(meta.collectedAt);
  document.querySelector('#accounts').textContent = new Intl.NumberFormat('en-US').format(meta.indexedUsers);
  document.querySelector('#last-check').textContent = state.lastChecked
    ? new Date(state.lastChecked).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : 'Not yet';
  document.querySelector('#update-status').textContent = state.error || 'Automatic checks every hour. Offline fallback ready.';
}
document.querySelector('#check').addEventListener('click', async event => {
  event.target.disabled = true;
  document.querySelector('#update-status').textContent = 'Checking…';
  try { await chrome.runtime.sendMessage({ type: 'LOCAL_LEET_CHECK' }); await render(); }
  catch { document.querySelector('#update-status').textContent = 'Could not check. Saved data is still available.'; }
  finally { event.target.disabled = false; }
});
render().catch(() => { document.querySelector('#snapshot').textContent = 'Unavailable'; });
