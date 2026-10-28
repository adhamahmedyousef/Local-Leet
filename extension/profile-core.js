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

  function nativePanels(row) {
    for (let panel = row.parentElement, depth = 0; panel && depth < 5; panel = panel.parentElement, depth++) {
      const card = panel.parentElement;
      const children = card ? [...card.children] : [];
      if (children.length === 3 && children[0] === panel
        && panel.querySelector('.rating-contest-graph') && children[2].textContent.includes('Top'))
        return { card, panel, divider: children[1], distribution: children[2] };
    }
    return null;
  }

  function resetPanelLayout(view) {
    if (!view.panels) return;
    delete view.panels.card.dataset.localLeetCard;
    delete view.panels.panel.dataset.localLeetPane;
    view.panels.card.style.removeProperty('--ll-stats-width');
  }

  function layoutRank(view) {
    if (!view.host.isConnected) return;
    const { anchor } = view;
    const win = view.host.ownerDocument.defaultView;
    resetPanelLayout(view);
    delete anchor.row.dataset.localLeetLayout;
    // Only our node is moved. React-owned badge, level and graph nodes stay intact.
    if (view.host.parentElement !== anchor.row) anchor.block.after(view.host);
    view.host.dataset.llPlacement = 'inline';
    const outerWidth = node => {
      const style = win.getComputedStyle(node);
      return node.getBoundingClientRect().width + (parseFloat(style.marginLeft) || 0)
        + (parseFloat(style.marginRight) || 0);
    };
    const available = anchor.row.getBoundingClientRect().width;
    if (!available) return; // Hidden responsive cards or a non-layout test environment.
    const required = [...anchor.row.children].reduce((sum, node) => sum + outerWidth(node), 0);
    if (required <= available + 1) return;
    if (view.panels) {
      const { card, panel, divider, distribution } = view.panels;
      const cardStyle = win.getComputedStyle(card);
      const rightStyle = win.getComputedStyle(distribution);
      const space = card.clientWidth - (parseFloat(cardStyle.paddingLeft) || 0)
        - (parseFloat(cardStyle.paddingRight) || 0) - outerWidth(divider)
        - (rightStyle.display === 'none' ? 0 : parseFloat(rightStyle.minWidth) || 200);
      if (rightStyle.display !== 'none' && Math.ceil(required) <= space) {
        card.dataset.localLeetCard = '';
        panel.dataset.localLeetPane = 'rating';
        card.style.setProperty('--ll-stats-width', `${Math.ceil(required)}px`);
        return;
      }
    }
    // At narrow widths, share the native Global Ranking column's reserved 53px header.
    view.host.dataset.llPlacement = 'compact';
    anchor.row.dataset.localLeetLayout = 'compact';
    anchor.block.append(view.host);
    if (view.panels) {
      const { card, panel, divider, distribution } = view.panels;
      const cardStyle = win.getComputedStyle(card);
      const rightStyle = win.getComputedStyle(distribution);
      const compactWidth = [...anchor.row.children].reduce((sum, node) => sum + outerWidth(node), 0);
      const remaining = card.clientWidth - (parseFloat(cardStyle.paddingLeft) || 0)
        - (parseFloat(cardStyle.paddingRight) || 0) - outerWidth(divider)
        - (parseFloat(rightStyle.minWidth) || 200);
      if (rightStyle.display !== 'none' && Math.ceil(compactWidth) <= remaining) {
        card.dataset.localLeetCard = ''; panel.dataset.localLeetPane = 'rating';
        card.style.setProperty('--ll-stats-width', `${Math.ceil(compactWidth)}px`);
      }
    }
  }

  function destroyRank(view) {
    if (!view) return;
    view.resizeObserver?.disconnect();
    resetPanelLayout(view);
    delete view.anchor.row.dataset.localLeetRow;
    delete view.anchor.row.dataset.localLeetLayout;
    view.host.remove();
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
      cadence: 'Ranking data is updated every two days. The extension checks for new data every hour.',
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
    const view = { host, button, code, number, total, status, anchor, panels: nativePanels(anchor.row) };
    const Resize = document.defaultView.ResizeObserver;
    if (Resize) {
      let lastWidth = -1;
      view.resizeObserver = new Resize(entries => {
        const width = entries[0]?.contentRect.width;
        if (width != null && Math.abs(width - lastWidth) > .5) { lastWidth = width; layoutRank(view); }
      });
      view.resizeObserver.observe(view.panels?.card || anchor.row.parentElement);
    }
    return view;
  }

  function updateRank(view, description) {
    view.number.textContent = description.number;
    view.total.textContent = description.total ? `/${description.total}` : '';
    view.code.textContent = description.code;
    view.host.dataset.state = description.state;
    view.host.dataset.stale = String(description.stale);
    view.button.title = `${description.summary}${description.date ? ` Snapshot: ${description.date}.` : ''} ${description.cadence}${description.stale ? ` ${description.notice}` : ''} Click for details.`;
    view.button.setAttribute('aria-label', `Local Rank. ${view.button.title}`);
    const status = description.state === 'loading' ? '' : `Local Rank. ${description.summary}`;
    if (view.status.textContent !== status) view.status.textContent = status;
    layoutRank(view);
  }

  globalThis.LocalLeetProfile = { profileIdentity, locateGlobalRank, readGlobalRank, describe,
    createRank, updateRank, destroyRank, layoutRank };
})();
