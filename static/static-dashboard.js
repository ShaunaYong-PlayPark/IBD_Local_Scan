document.addEventListener('DOMContentLoaded', () => {
  if (window.__ibdStaticDashboardReady) return;
  window.__ibdStaticDashboardReady = true;

  const headerHeight = () => parseInt(getComputedStyle(document.documentElement).getPropertyValue('--dashboard-header-height')) || 56;
  const secondaryHeight = () => parseInt(getComputedStyle(document.documentElement).getPropertyValue('--dashboard-secondary-height')) || 54;
  const scrollToTarget = (id) => {
    const target = document.getElementById(id);
    if (!target) return;
    window.scrollTo({top: Math.max(0, target.getBoundingClientRect().top + window.scrollY - headerHeight() - secondaryHeight() - 14), behavior: 'smooth'});
  };

  const tabs = [...document.querySelectorAll('[data-sea-target]')];
  const panels = [...document.querySelectorAll('.sea-view-panel')];
  const sectionNav = document.getElementById('global-section-nav');
  const sectionItems = [
    ['market-snapshot', 'Market Snapshot'],
    ['mobile-pc-games', 'Mobile + PC/Console Games'],
    ['mobile-only-games', 'Mobile-only Games'],
    ['pc-only-games', 'PC/Console-only Games'],
    ['game-announcements', 'Game Announcements'],
    ['industry-trends', 'Industry Trends'],
  ];
  let sectionObserver = null;

  const closeSectionMenu = () => {
    if (!sectionNav) return;
    sectionNav.setAttribute('aria-expanded', 'false');
    sectionNav.querySelector('.on-page-toggle')?.setAttribute('aria-expanded', 'false');
  };
  const refreshSectionMenu = (scope = 'sea6') => {
    if (!sectionNav) return;
    const prefix = scope === 'sea6' ? 'sea6' : scope.replace(/^sea-/, '');
    const links = sectionItems.map(([suffix, label]) => {
      const id = `${prefix}-${suffix}`;
      return document.getElementById(id) ? `<a href="#${id}" data-section-target="${id}">${label}</a>` : '';
    }).join('');
    const linkBox = sectionNav.querySelector('.on-page-links');
    if (!linkBox) return;
    linkBox.innerHTML = links;
    linkBox.id = `${prefix}-on-page-links`;
    sectionNav.querySelector('.on-page-toggle')?.setAttribute('aria-controls', linkBox.id);
    sectionNav.dataset.bookmarkScope = prefix;
    linkBox.querySelectorAll('a').forEach((link) => link.addEventListener('click', (event) => {
      event.preventDefault();
      const id = link.dataset.sectionTarget;
      history.replaceState(null, '', `#${id}`);
      scrollToTarget(id);
      closeSectionMenu();
    }));
    sectionObserver?.disconnect();
    const targets = [...linkBox.querySelectorAll('[data-section-target]')]
      .map((link) => document.getElementById(link.dataset.sectionTarget)).filter(Boolean);
    if ('IntersectionObserver' in window) {
      sectionObserver = new IntersectionObserver((entries) => {
        entries.filter((entry) => entry.isIntersecting).forEach((entry) => {
          linkBox.querySelectorAll('a').forEach((link) => {
            const active = link.dataset.sectionTarget === entry.target.id;
            link.classList.toggle('is-current', active);
            link.setAttribute('aria-current', active ? 'location' : 'false');
          });
        });
      }, {rootMargin: `-${headerHeight() + secondaryHeight() + 12}px 0px -62% 0px`, threshold: 0});
      targets.forEach((target) => sectionObserver.observe(target));
    }
  };
  if (sectionNav) {
    const toggle = sectionNav.querySelector('.on-page-toggle');
    toggle?.addEventListener('click', (event) => {
      event.stopPropagation();
      const open = sectionNav.getAttribute('aria-expanded') === 'true';
      sectionNav.setAttribute('aria-expanded', String(!open));
      toggle.setAttribute('aria-expanded', String(!open));
    });
    document.addEventListener('click', (event) => {
      if (!sectionNav.contains(event.target)) closeSectionMenu();
    });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeSectionMenu(); });
    refreshSectionMenu('sea6');
  }

  const selectSea = (target, updateHash = true) => {
    tabs.forEach((tab) => {
      const active = tab.dataset.seaTarget === target;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    panels.forEach((panel) => { panel.hidden = panel.id !== target; panel.classList.toggle('active', panel.id === target); });
    refreshSectionMenu(target === 'sea6-summary-panel' ? 'sea6' : target);
    if (updateHash) history.replaceState(null, '', `#${target === 'sea6-summary-panel' ? 'sea6-summary' : target}`);
  };
  if (tabs.length) {
    const hash = location.hash.replace('#', '');
    const initial = hash === 'sea6-summary' ? 'sea6-summary-panel' : (panels.some((panel) => panel.id === hash) ? hash : 'sea6-summary-panel');
    selectSea(initial, false);
    tabs.forEach((tab) => tab.addEventListener('click', (event) => { event.preventDefault(); selectSea(tab.dataset.seaTarget); }));
  }

  const populateYears = (select, rows, key) => {
    if (!select) return;
    [...new Set(rows.map((row) => row.dataset[key]).filter(Boolean))].sort().reverse().forEach((year) => {
      select.insertAdjacentHTML('beforeend', `<option value="${year}">${year}</option>`);
    });
  };
  const archiveCards = [...document.querySelectorAll('.archive-card[data-archive-year]')];
  const archiveYear = document.getElementById('archiveYear');
  const archiveMonth = document.getElementById('archiveMonth');
  const archiveSearch = document.getElementById('archiveSearch');
  const filterArchive = () => archiveCards.forEach((card) => {
    card.hidden = !((archiveYear?.value || 'all') === 'all' || card.dataset.archiveYear === archiveYear.value)
      || !((archiveMonth?.value || 'all') === 'all' || card.dataset.archiveMonth === archiveMonth.value)
      || Boolean(archiveSearch?.value) && !card.textContent.toLowerCase().includes(archiveSearch.value.toLowerCase());
  });
  populateYears(archiveYear, archiveCards, 'archiveYear');
  [archiveYear, archiveMonth, archiveSearch].filter(Boolean).forEach((control) => control.addEventListener('input', filterArchive));

  const trackerRows = [...document.querySelectorAll('.tracker-row')];
  const trackerBody = document.querySelector('.data-table tbody');
  const trackerYear = document.getElementById('trackerYear');
  const trackerMonth = document.getElementById('trackerMonth');
  const trackerSearch = document.getElementById('trackerSearch');
  const trackerSuggestions = document.getElementById('trackerSuggestions');
  let suggestionIndex = -1;
  const suggestionValues = [...new Set(trackerRows.flatMap((row) => {
    const cells = row.querySelectorAll('td');
    return [cells[1]?.innerText.trim(), cells[2]?.innerText.trim()].filter(Boolean);
  }))].sort((a, b) => a.localeCompare(b, undefined, {sensitivity: 'base'}));
  const closeSuggestions = () => { if (trackerSuggestions) { trackerSuggestions.hidden = true; trackerSuggestions.innerHTML = ''; } suggestionIndex = -1; };
  const applySuggestion = (value) => { if (!trackerSearch) return; trackerSearch.value = value; closeSuggestions(); sortTracker(); trackerSearch.focus(); };
  const renderSuggestions = () => {
    if (!trackerSuggestions || !trackerSearch) return;
    const query = trackerSearch.value.trim().toLowerCase();
    if (!query) return closeSuggestions();
    const matches = suggestionValues.filter((value) => value.toLowerCase().includes(query)).slice(0, 8);
    if (!matches.length) return closeSuggestions();
    trackerSuggestions.innerHTML = matches.map((value, index) => `<button type="button" role="option" aria-selected="${index === suggestionIndex}" data-suggestion-index="${index}">${value}</button>`).join('');
    trackerSuggestions.hidden = false;
    trackerSuggestions.querySelectorAll('button').forEach((button) => button.addEventListener('mousedown', (event) => { event.preventDefault(); applySuggestion(button.textContent); }));
  };
  const levels = ['Primary', 'Secondary', 'Tertiary'];
  const sortValue = (row, field) => row.dataset[`sort${field.charAt(0).toUpperCase()}${field.slice(1)}`] || '';
  const setOrderButton = (button, direction) => {
    if (!button) return;
    const descending = direction === 'desc';
    button.dataset.direction = direction;
    button.textContent = descending ? 'Z-A ↓' : 'A-Z ↑';
    button.title = descending ? 'Current order: Z-A / high-to-low. Activate to switch to A-Z / low-to-high.' : 'Current order: A-Z / low-to-high. Activate to switch to Z-A / high-to-low.';
    button.setAttribute('aria-label', button.title);
  };
  const matchesTracker = (row) => (!trackerYear?.value || trackerYear.value === 'all' || row.dataset.sortYear === trackerYear.value)
    && (!trackerMonth?.value || trackerMonth.value === 'all' || row.dataset.sortMonth === trackerMonth.value)
    && (!trackerSearch?.value || row.textContent.toLowerCase().includes(trackerSearch.value.toLowerCase()));
  const sortTracker = () => {
    const criteria = levels.map((level) => {
      const select = document.getElementById(`tracker${level}Sort`);
      const button = document.getElementById(`tracker${level}Direction`);
      return select?.value ? {field: select.value, direction: button?.dataset.direction === 'desc' ? -1 : 1} : null;
    }).filter(Boolean);
    trackerRows.sort((a, b) => {
      for (const criterion of criteria) {
        const av = sortValue(a, criterion.field); const bv = sortValue(b, criterion.field);
        if (!av && !bv) continue; if (!av) return 1; if (!bv) return -1;
        const an = Number(av); const bn = Number(bv);
        const result = Number.isFinite(an) && Number.isFinite(bn) ? an - bn : av.localeCompare(bv, undefined, {numeric: true, sensitivity: 'base'});
        if (result) return result * criterion.direction;
      }
      return 0;
    });
    trackerRows.forEach((row) => { trackerBody?.appendChild(row); row.hidden = !matchesTracker(row); });
  };
  populateYears(trackerYear, trackerRows, 'sortYear');
  levels.forEach((level) => {
    const button = document.getElementById(`tracker${level}Direction`);
    setOrderButton(button, button?.dataset.direction || 'asc');
    document.getElementById(`tracker${level}Sort`)?.addEventListener('input', sortTracker);
    button?.addEventListener('click', () => { setOrderButton(button, button.dataset.direction === 'desc' ? 'asc' : 'desc'); sortTracker(); });
  });
  [trackerYear, trackerMonth].filter(Boolean).forEach((control) => control.addEventListener('input', sortTracker));
  trackerSearch?.addEventListener('input', () => { renderSuggestions(); sortTracker(); });
  trackerSearch?.addEventListener('keydown', (event) => {
    if (!trackerSuggestions || trackerSuggestions.hidden) return;
    const options = [...trackerSuggestions.querySelectorAll('button')];
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); suggestionIndex = (suggestionIndex + (event.key === 'ArrowDown' ? 1 : options.length - 1)) % options.length;
      options.forEach((button, index) => button.setAttribute('aria-selected', index === suggestionIndex ? 'true' : 'false'));
    } else if (event.key === 'Enter' && suggestionIndex >= 0) { event.preventDefault(); applySuggestion(options[suggestionIndex].textContent); }
    else if (event.key === 'Escape') { closeSuggestions(); }
  });
  trackerSearch?.addEventListener('blur', () => setTimeout(closeSuggestions, 120));
  document.getElementById('clearTrackerFilters')?.addEventListener('click', () => {
    [trackerYear, trackerMonth].forEach((control) => { if (control) control.value = 'all'; });
    if (trackerSearch) trackerSearch.value = '';
    closeSuggestions();
    document.getElementById('trackerPrimarySort')?.setAttribute('value', 'date');
    const primary = document.getElementById('trackerPrimarySort'); if (primary) primary.value = 'date';
    ['Secondary', 'Tertiary'].forEach((level) => { const select = document.getElementById(`tracker${level}Sort`); if (select) select.value = ''; });
    levels.forEach((level) => setOrderButton(document.getElementById(`tracker${level}Direction`), 'asc'));
    sortTracker();
  });
  document.getElementById('downloadTrackerCsv')?.addEventListener('click', () => {
    const table = document.querySelector('.data-table table');
    const rows = [...document.querySelectorAll('.tracker-row:not([hidden])')];
    const csv = (value) => `"${String(value ?? '').replace(/"/g, '""').replace(/\r?\n/g, ' ')}"`;
    const escapeCsv = (value) => csv(value);
    const lines = [[...table.querySelectorAll('thead th')].map((cell) => escapeCsv(cell.innerText.trim())).join(',')];
    rows.forEach((row) => lines.push([...row.querySelectorAll('td')].map((cell) => escapeCsv(cell.innerText.trim())).join(',')));
    const url = URL.createObjectURL(new Blob([lines.join('\n')], {type: 'text/csv;charset=utf-8'}));
    const link = document.createElement('a'); link.href = url; link.download = `game-tracker-${new Date().toISOString().slice(0, 10)}.csv`; link.click(); URL.revokeObjectURL(url);
  });
  sortTracker();
  const current = new URLSearchParams(location.search).get('view') === 'table' ? 'table' : 'cards';
  if (current === 'table') document.body.classList.add('table-mode');
  document.querySelectorAll('.view-toggle a').forEach((link) => {
    const active = (new URL(link.href, location.href).searchParams.get('view') === 'table' ? 'table' : 'cards') === current;
    link.classList.toggle('active', active); link.setAttribute('aria-current', active ? 'true' : 'false');
  });
});
