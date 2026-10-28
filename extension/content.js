(() => {
  if (globalThis.__localLeetInstalled) return;
  globalThis.__localLeetInstalled = true;
  const core = globalThis.LocalLeetProfile;
  let anchor, view, details, identity, result, error, timer, revision = 0;
  let href = location.href;

  function closeDetails() {
    if (details) details.hidden = true;
    view?.button.setAttribute('aria-expanded', 'false');
  }

  function toggleDetails() {
    if (!view) return;
    if (details && !details.hidden) { closeDetails(); return; }
    if (!details) {
      details = document.createElement('section');
      details.id = 'local-leet-details';
      details.className = 'll-details';
      details.dataset.localLeet = 'details';
      details.setAttribute('role', 'region');
      details.setAttribute('aria-label', 'Local Rank details');
      document.body.append(details);
    }
    details.replaceChildren();
    const heading = document.createElement('h2');
    heading.textContent = 'Local Rank';
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'll-details-close'; close.textContent = '×';
    close.setAttribute('aria-label', 'Close rank details');
    close.addEventListener('click', () => { closeDetails(); view?.button.focus(); });
    details.append(heading, close);
    const description = core.describe(result, core.readGlobalRank(anchor));
    const lines = error ? [error, 'Reload this profile to try again.'] : [description.summary,
      description.date ? `Snapshot: ${description.date} (UTC).` : 'Reading the bundled ranking data.',
      description.cadence,
      ...(result ? [description.notice,
        'Accounts without a declared country are excluded from country counts. Local Leet is independent of LeetCode.'] : [])];
    for (const [index, text] of lines.entries()) {
      const p = document.createElement('p'); p.textContent = text;
      if (index) p.className = 'll-detail-secondary';
      details.append(p);
    }
    const credit = document.createElement('p');
    credit.className = 'll-detail-secondary';
    credit.append(document.createTextNode('Built By '));
    const brand = document.createElement('a');
    brand.href = 'https://voidhub.co'; brand.target = '_blank'; brand.rel = 'noopener noreferrer';
    brand.textContent = 'VoidHub'; credit.append(brand); details.append(credit);
    details.hidden = false;
    const box = view.host.getBoundingClientRect();
    details.style.left = `${Math.max(12, Math.min(box.left, innerWidth - details.offsetWidth - 12))}px`;
    details.style.top = `${Math.max(12, Math.min(box.bottom + 8, innerHeight - details.offsetHeight - 12))}px`;
    view.button.setAttribute('aria-expanded', 'true');
  }

  function render() {
    if (!view) return;
    const description = core.describe(result, core.readGlobalRank(anchor));
    if (error) { description.state = 'error'; description.number = '—'; description.summary = error; }
    core.updateRank(view, description);
  }

  function clear() {
    core.destroyRank(view); details?.remove();
    if (anchor?.row.isConnected) delete anchor.row.dataset.localLeetRow;
    anchor = view = details = identity = result = error = null;
    revision++;
  }

  async function sync() {
    timer = null;
    const next = core.profileIdentity(location.href);
    href = location.href;
    if (!next) { clear(); return; }
    if (identity && (identity.username !== next.username || identity.region !== next.region)) clear();
    const found = core.locateGlobalRank(document);
    if (!found) { if (view && !view.host.isConnected) clear(); return; }
    if (anchor?.block !== found.block || !view?.host.isConnected || !view.host.contains(view.button)
      || !view.button.contains(view.number)) {
      core.destroyRank(view); closeDetails();
      anchor = found;
      view = core.createRank(document, anchor, toggleDetails);
    }
    if (identity) { render(); return; }
    identity = next; result = null; error = null; render();
    const token = ++revision;
    try {
      const response = await chrome.runtime.sendMessage({ type: 'LOCAL_LEET_LOOKUP', ...identity });
      if (token !== revision || core.profileIdentity(location.href)?.username !== identity.username) return;
      if (!response?.ok) throw new Error(response?.error || 'Could not read the local ranking data.');
      result = response.result;
    } catch {
      if (token !== revision) return;
      error = 'Local rank is unavailable. Reload the profile after checking that Local Leet is enabled.';
      result = { user: null };
    }
    render();
  }

  function schedule() { if (!timer) timer = setTimeout(sync, 60); }
  chrome.storage?.onChanged?.addListener((changes, area) => {
    const change = changes.localLeetUpdates;
    if (area === 'local' && change?.newValue?.active?.snapshotId
      && change.newValue.active.snapshotId !== change.oldValue?.active?.snapshotId
      && core.profileIdentity(location.href)) {
      revision++; identity = null; closeDetails(); schedule();
    }
  });
  const observer = new MutationObserver(records => {
    if (location.href !== href) { schedule(); return; }
    if (records.some(r => r.type === 'attributes' && r.target !== view?.panels?.card
      && !r.target.closest('[data-local-leet]')
      && (r.target.contains(anchor?.row) || anchor?.row.parentElement?.parentElement?.contains(r.target)))) {
      schedule(); return;
    }
    const ownMutation = record => {
      const target = record.target.nodeType === 1 ? record.target : record.target.parentElement;
      if (target?.closest('[data-local-leet]')) return true;
      const changed = [...record.addedNodes, ...record.removedNodes];
      return changed.length > 0 && changed.every(node => node.nodeType === 1 && node.matches('[data-local-leet]'));
    };
    if (view?.host.isConnected && view.host.dataset.llPlacement === 'inline'
      && anchor.block.nextElementSibling !== view.host) { schedule(); return; }
    if (view?.host.isConnected && view.host.contains(view.button) && view.button.contains(view.number)
      && records.every(ownMutation)) return;
    if (!core.profileIdentity(location.href)) return;
    if (!view?.host.isConnected) {
      if (records.some(r => !r.target.parentElement?.closest('[data-local-leet]'))) schedule();
      return;
    }
    if (records.some(r => anchor.row.contains(r.target) || r.target.contains?.(anchor.row))) schedule();
  });
  const observe = () => observer.observe(document.body, { childList: true, subtree: true, characterData: true,
    attributes: true, attributeFilter: ['class', 'style', 'hidden'] });
  observe();
  addEventListener('popstate', schedule);
  addEventListener('pageshow', () => { observe(); schedule(); });
  addEventListener('pagehide', () => { observer.disconnect(); clearTimeout(timer); timer = null; closeDetails(); });
  addEventListener('scroll', closeDetails, { passive: true });
  addEventListener('resize', closeDetails, { passive: true });
  document.addEventListener('click', event => {
    if (!view?.host.contains(event.target) && !details?.contains(event.target)) closeDetails();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && details && !details.hidden) { closeDetails(); view?.button.focus(); }
  });
  schedule();
})();
