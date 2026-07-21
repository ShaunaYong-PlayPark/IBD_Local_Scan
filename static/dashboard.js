// Browser behaviours for the local dashboard.
// Internal GET navigation is upgraded progressively: links still work normally
// without JavaScript, but same-site page changes can update without the visual
// full-page reload + scroll-jump.

function tog(source){
  document.querySelectorAll('input[name=selected]').forEach((item) => { item.checked = source.checked; });
}

(function smoothInternalNavigation(){
  const appShellSelector = '.workspace';

  function isPlainLeftClick(event){
    return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
  }

  function shouldHandleLink(link, event){
    if (!isPlainLeftClick(event)) return false;
    if (!link || link.target === '_blank' || link.hasAttribute('download')) return false;
    const rawHref = link.getAttribute('href') || '';
    if (!rawHref || rawHref.startsWith('#') || rawHref.startsWith('javascript:') || rawHref.startsWith('mailto:')) return false;
    let url;
    try { url = new URL(rawHref, window.location.href); } catch (error) { return false; }
    if (url.origin !== window.location.origin) return false;
    if (url.pathname.startsWith('/export/') || url.pathname.startsWith('/static/')) return false;
    return true;
  }

  async function fetchDocument(url){
    const response = await fetch(url, { headers: { 'X-Requested-With': 'fetch' } });
    if (!response.ok) throw new Error(`Navigation failed: ${response.status}`);
    const html = await response.text();
    return new DOMParser().parseFromString(html, 'text/html');
  }

  function replaceWorkspace(nextDocument, url, preserveScroll){
    const currentWorkspace = document.querySelector(appShellSelector);
    const nextWorkspace = nextDocument.querySelector(appShellSelector);
    if (!currentWorkspace || !nextWorkspace) {
      window.location.href = url;
      return;
    }
    const previousScroll = window.scrollY || 0;
    document.title = nextDocument.title || document.title;
    currentWorkspace.replaceWith(nextWorkspace);
    if (preserveScroll) {
      requestAnimationFrame(() => window.scrollTo({ top: previousScroll, left: 0, behavior: 'auto' }));
    } else {
      requestAnimationFrame(() => window.scrollTo({ top: 0, left: 0, behavior: 'auto' }));
    }
  }

  async function navigate(url, options = {}){
    const previous = new URL(window.location.href);
    const next = new URL(url, window.location.href);
    const preserveScroll = options.preserveScroll ?? (previous.pathname === next.pathname);
    document.documentElement.classList.add('is-navigating');
    try {
      const nextDocument = await fetchDocument(next.href);
      replaceWorkspace(nextDocument, next.href, preserveScroll);
      if (options.push !== false) {
        history.pushState({ smooth: true }, '', next.href);
      }
    } catch (error) {
      window.location.href = next.href;
    } finally {
      document.documentElement.classList.remove('is-navigating');
    }
  }

  document.addEventListener('click', (event) => {
    const link = event.target.closest && event.target.closest('a');
    if (!shouldHandleLink(link, event)) return;
    event.preventDefault();
    navigate(link.href);
  });

  window.addEventListener('popstate', () => {
    navigate(window.location.href, { push: false, preserveScroll: false });
  });
})();



