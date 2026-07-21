from html import escape
from pathlib import Path

def esc(value):
    return escape(str(value or ''), quote=True)

def render_template(path, **context):
    html = Path(path).read_text(encoding='utf-8')
    for key, value in context.items():
        html = html.replace('{{ ' + key + ' }}', str(value))
    return html

def status_badge(text):
    value = str(text or 'Draft')
    klass = 'published' if value.lower() in ('published','finalised','archived','ready') else 'draft'
    return f'<span class="status-badge {klass}">{esc(value)}</span>'

def meta_item(label, value):
    return f'<div class="meta-item"><span>{esc(label)}</span><b>{esc(value or "Unavailable")}</b></div>'

def page_header(eyebrow, title, desc='', actions=''):
    desc_html = f'<p>{esc(desc)}</p>' if desc else ''
    actions_html = f'<div class="page-actions">{actions}</div>' if actions else ''
    return f'<section class="page-header"><div><em>{esc(eyebrow)}</em><h1>{esc(title)}</h1>{desc_html}</div>{actions_html}</section>'

def empty_state(title, desc, action=''):
    return f'<article class="empty-state polished-empty"><h3>{esc(title)}</h3><p>{esc(desc)}</p>{action}</article>'

def nav_link(href, label, desc, active=False):
    active_attr = ' aria-current="page"' if active else ''
    classes = []
    if active:
        classes.append('on')
    if href == '/admin':
        classes.append('admin-nav-link')
    class_attr = ' '.join(classes)
    return f'<a class="{class_attr}" href="{esc(href)}" data-tooltip="{esc(desc)}" title="{esc(desc)}" aria-label="{esc(label + ": " + desc)}"{active_attr}><span>{esc(label)}</span></a>'




