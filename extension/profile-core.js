/** Small DOM adapter shared by the content script and browser fixture tests. */
(() => {
  const format = new Intl.NumberFormat('en-US');
  const countryNames = new Intl.DisplayNames(['en'], { type: 'region' });

  function profileIdentity(url) {
    const parsed = new URL(url);
    if (!/^(www\.)?leetcode\.(com|cn)$/.test(parsed.hostname)) return null;
    const match = /^\/u\/([^/]+)\/?$/.exec(parsed.pathname);
    if (!match) return null;
    let username;
    try { username = decodeURIComponent(match[1]); } catch { return null; }
    if (!username || username.length > 100 || /[\s/\\\x00-\x1f]/u.test(username)) return null;
    return { username, region: parsed.hostname.endsWith('.cn') ? 'CN' : 'US' };
  }

  function locateGlobalRank(document) {
    const root = document.querySelector('#main-content') || document.querySelector('main') || document.body;
    if (!root) return null;
    const walker = document.createTreeWalker(root, 4); // SHOW_TEXT
    let text;
    while ((text = walker.nextNode())) {
      if (!/^Global Rank(?:ing)?$/.test(text.textContent.trim())) continue;
      const label = text.parentElement;
      if (!label || label.closest('[data-local-leet]')) continue;
      const block = label.parentElement;
      const value = label.nextElementSibling;
      if (!block || !value || !/\d/.test(value.textContent)) continue;
      const row = block.parentElement;
      if (!row?.textContent.includes('Contest Rating')) continue;
      return { label, block, value, row };
    }
    return null;
  }

  function readGlobalRank(anchor) {
    const match = /^\s*([\d,]+)/.exec(anchor.value.textContent);
    return match ? Number(match[1].replaceAll(',', '')) : null;
  }

  function describe(result, currentGlobal) {
    const date = result?.collectedAt ? new Date(result.collectedAt).toLocaleDateString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
    }) : null;
    const user = result?.user;
    const state = !result ? 'loading' : !user ? 'missing' : !user.country ? 'unknown' : 'ready';
    const stale = state === 'ready' && currentGlobal != null && currentGlobal !== user.globalRank;
    return {
      state, stale, date,
      country: user?.country ? countryNames.of(user.country) : null,
      number: state === 'loading' ? '…' : state === 'ready' ? format.format(user.localRank) : '—',
      total: state === 'ready' ? format.format(user.countryTotal) : '',
      code: state === 'ready' ? user.country : '',
      summary: state === 'loading' ? 'Loading country rank.' : state === 'missing'
        ? 'This profile is not in the collected contest standings.' : state === 'unknown'
          ? 'No country was declared in this snapshot. A local rank cannot be calculated.'
          : `Rank ${format.format(user.localRank)} of ${format.format(user.countryTotal)} in ${countryNames.of(user.country)}, among accounts declaring that country.`,
      notice: stale ? 'The profile’s global rank has changed. This is the saved local rank, not a live recalculation.'
        : 'Based on a saved snapshot, not live standings.',
    };
  }

  function createRank(document, anchor, onToggle) {
    const host = document.createElement('div');
    host.dataset.localLeet = 'rank';
    host.className = `${anchor.block.className} ll-rank`;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'll-rank-button';
    button.setAttribute('aria-expanded', 'false');
    button.setAttribute('aria-controls', 'local-leet-details');
    const label = document.createElement('div');
    label.className = `${anchor.label.className} ll-rank-label`;
    const labelText = document.createElement('span');
    labelText.textContent = 'Local Rank';
    const code = document.createElement('span');
    code.className = 'll-country-code';
    label.append(labelText, code);
    const value = document.createElement('div');
    value.className = `${anchor.value.className} ll-rank-value`;
    const number = document.createElement('span');
    number.dataset.llNumber = '';
    const total = document.createElement('span');
    total.className = anchor.value.querySelector('span')?.className || 'll-denominator';
    value.append(number, total);
    button.append(label, value);
    const status = document.createElement('span');
    status.className = 'll-sr-only';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-atomic', 'true');
    button.append(status);
    button.addEventListener('click', onToggle);
    host.append(button);
    anchor.block.after(host);
    anchor.row.dataset.localLeetRow = '';
    return { host, button, code, number, total, status };
  }

  function updateRank(view, description) {
    view.number.textContent = description.number;
    view.total.textContent = description.total ? `/${description.total}` : '';
    view.code.textContent = description.code;
    view.host.dataset.state = description.state;
    view.host.dataset.stale = String(description.stale);
    view.button.title = `${description.summary}${description.date ? ` Snapshot: ${description.date}.` : ''}${description.stale ? ` ${description.notice}` : ''} Click for details.`;
    view.button.setAttribute('aria-label', `Local Rank. ${view.button.title}`);
    const status = description.state === 'loading' ? '' : `Local Rank. ${description.summary}`;
    if (view.status.textContent !== status) view.status.textContent = status;
  }

  globalThis.LocalLeetProfile = { profileIdentity, locateGlobalRank, readGlobalRank, describe,
    createRank, updateRank };
})();
