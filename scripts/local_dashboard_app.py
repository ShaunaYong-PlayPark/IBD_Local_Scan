
import csv, html, io, json, os, re, secrets, subprocess, urllib.parse
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; APP=ROOT/'data'/'local_app'; OUT=ROOT/'data'/'output'
CONFIG=ROOT/'config'/'settings.json'; STATE=APP/'state.json'; ST_META=APP/'extraction_metadata.json'; WATCH=APP/'watchlist.csv'; OVR=APP/'signal_overrides.csv'; HIST=APP/'change_history.csv'; SNAP=APP/'report_snapshots'
FINAL=OUT/'final_sg_market_scan_current_workflow.csv'; DECISIONS=OUT/'current_workflow_decisions.csv'; PORT=int(os.environ.get('IBD_DASHBOARD_PORT','8787')); LAG=1
SESSION_COOKIE='ibd_poc_session'; SESSIONS={}
VIEWER_ROUTES={'/latest-brief','/historical-briefs','/game-tracker','/market-brief','/data-export','/calendar','/launches','/reports','/market-timeline'}
ADMIN_ROUTES={'/admin','/review','/operations'}
ADMIN_EXPORTS={'admin.csv','review.csv','workflow-decisions.csv'}
WATCH_FIELDS=['unified_app_id','game_title','publisher','platform','sg_release_date','release_report_start','release_report_end','watch_until_meeting_date','status','first_top_grossing_seen_date','reported_date','notes']
OVR_FIELDS=['unified_app_id','game_title','override_signal_type','starred','deleted','notes','approved_report_note','review_status','selected_for_report','manual_english_title','translation_review_status','translation_note','include_in_market_brief','pinned_position','featured_slot','market_brief_card_size','market_brief_order','admin_hide_from_brief','curation_updated_at','curation_updated_by','updated_at']
HIST_FIELDS=['timestamp','user','action','unified_app_id','game_title','field','previous_value','new_value','reason']
ADMINS={'Shauna','Daryl'}; ROLES={'Viewer':{'read','export'},'Contributor':{'read','export','annotate','classify','exclude'},'Admin':{'read','export','annotate','classify','exclude','run','dates','finalise','diagnostics'}}
SIGDEF={'Strong Market Signal':'SG gross revenue exceeded $1K during the report period while appearing in SG Top Grossing.','Early Market Signal':'SG Top Grossing watchlist item below the Strong threshold.','Watchlist':'SG Top Grossing watchlist item below the Strong threshold.'}
SIGDIS={'Strong Market Signal':'Strong Market Signal','Early Market Signal':'Emerging Market Signal','Emerging Market Signal':'Emerging Market Signal','Watchlist':'Watchlist'}; DISP_BACK={'Strong Market Signal':'Strong Market Signal','Emerging Market Signal':'Early Market Signal','Early Market Signal':'Early Market Signal','Watchlist':'Watchlist'}

def esc(x): return html.escape(str(x or ''),quote=True)
def env_password(name): return os.environ.get(name,'')
def cookie_parts(header):
    out={}
    for part in str(header or '').split(';'):
        if '=' in part:
            k,v=part.split('=',1); out[k.strip()]=urllib.parse.unquote(v.strip())
    return out
def auth_role_from_cookie(header):
    sid=cookie_parts(header).get(SESSION_COOKIE,'')
    return SESSIONS.get(sid,'')
def new_session(role):
    sid=secrets.token_urlsafe(32); SESSIONS[sid]=role; return sid
def login_page(msg='',next_url='/latest-brief'):
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IBD Login</title><style>
    body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#f6f7f9;color:#17202a;font-family:Arial,sans-serif}}
    main{{width:min(420px,calc(100vw - 32px));background:white;border:1px solid #d9dee5;border-radius:8px;padding:28px;box-shadow:0 12px 32px rgba(20,30,40,.08)}}
    h1{{margin:0 0 6px;font-size:24px}} p{{color:#596575;line-height:1.5}} label{{display:block;margin:18px 0 8px;font-weight:700}}
    input{{width:100%;box-sizing:border-box;padding:12px;border:1px solid #c8d0da;border-radius:6px;font-size:16px}}
    button{{margin-top:16px;width:100%;padding:12px;border:0;border-radius:6px;background:#1f5eff;color:white;font-weight:700;cursor:pointer}}
    .error{{background:#fff0f0;color:#9b1c1c;border:1px solid #f0b9b9;padding:10px;border-radius:6px}}
    </style></head><body><main><h1>IBD Market Intelligence</h1><p>Private proof-of-concept dashboard.</p>{f'<div class="error">{esc(msg)}</div>' if msg else ''}<form method="post" action="/login"><input type="hidden" name="next" value="{esc(next_url)}"><label>Password</label><input type="password" name="password" autofocus autocomplete="current-password"><button>Sign in</button></form></main></body></html>'''
def safe_next(value):
    value=str(value or '/latest-brief')
    return value if value.startswith('/') and not value.startswith('//') else '/latest-brief'
def now(): return datetime.now().isoformat(timespec='seconds')
def todaystamp(): return datetime.now(timezone.utc).astimezone().strftime('%d %b %Y %H:%M')
def pdate(x):
    if not x: return None
    s=str(x).strip()
    for f in ('%Y-%m-%d','%d-%b-%Y','%d %b %Y','%d/%m/%Y'):
        try: return datetime.strptime(s[:11],f).date()
        except ValueError: pass
    try: return date.fromisoformat(s[:10])
    except ValueError: return None
def nd(x):
    d=pdate(x); return d.strftime('%d %b %Y') if d else ''
def sf(x):
    try: return float(str(x or 0).replace(',','').replace('$',''))
    except ValueError: return 0.0
def money(x): return f'${sf(x):,.0f}'
def rj(path,default):
    if not path.exists(): return default
    return json.load(path.open(encoding='utf-8-sig'))
def wj(path,obj): path.parent.mkdir(parents=True,exist_ok=True); json.dump(obj,path.open('w',encoding='utf-8'),indent=2,ensure_ascii=False)
def rc(path):
    if not path.exists(): return []
    return list(csv.DictReader(path.open(encoding='utf-8-sig',newline='')))
def wc(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True); f=path.open('w',encoding='utf-8-sig',newline=''); w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows); f.close()
def csvbytes(rows,fields=None):
    if fields is None:
        fields=[]
        for r in rows:
            for k in r:
                if k not in fields: fields.append(k)
    s=io.StringIO(); w=csv.DictWriter(s,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows); return s.getvalue().encode('utf-8-sig')
def public_config(): return {k:v for k,v in rj(CONFIG,{}).items() if all(t not in k.lower() for t in ('token','auth','key'))}
def sg_today():
    simulated=os.environ.get('IBD_SIMULATED_SG_DATE','').strip()
    parsed=pdate(simulated)
    if parsed: return parsed
    return datetime.now(timezone(timedelta(hours=8))).date()
def init_state():
    return {'last_completed_meeting_date':'2026-07-14','upcoming_meeting_date':'2026-07-28','meeting_time':'16:00','meeting_date':'2026-07-28','active_report_start_date':'2026-07-14','last_saved_at':now(),'last_scan_at':'','last_scan_period_key':'','report_status':'Draft' if FINAL.exists() else 'Not Generated','current_user':'Shauna','current_role':'Admin','scan_running':False,'watch_periods_after_release':2}
def ensure():
    APP.mkdir(parents=True,exist_ok=True); SNAP.mkdir(parents=True,exist_ok=True)
    if not STATE.exists(): wj(STATE,init_state())
    if not WATCH.exists(): wc(WATCH,[],WATCH_FIELDS)
    if not OVR.exists(): wc(OVR,[],OVR_FIELDS)
    else: wc(OVR,rc(OVR),OVR_FIELDS)
    if not HIST.exists(): wc(HIST,[],HIST_FIELDS)
def state():
    ensure(); s=rj(STATE,init_state())
    for k,v in init_state().items(): s.setdefault(k,v)
    if not s.get('last_completed_meeting_date'):
        s['last_completed_meeting_date']=s.get('active_report_start_date') or '2026-07-14'
    if not s.get('upcoming_meeting_date'):
        s['upcoming_meeting_date']=s.get('meeting_date') or '2026-07-28'
    if not s.get('meeting_time'):
        s['meeting_time']='16:00'
    rollover_meeting_cycle(s)
    if s.get('current_role')=='Admin' and s.get('current_user') not in ADMINS: s['current_role']='Contributor'
    if s.get('current_role') not in ROLES: s['current_role']='Viewer'
    wj(STATE,s); return s
def save_state(s): s['last_saved_at']=now(); wj(STATE,s)
def can(s,a): return a in ROLES.get(s.get('current_role','Viewer'),set())
def rollover_meeting_cycle(s):
    today=sg_today()
    upcoming=pdate(s.get('upcoming_meeting_date') or s.get('meeting_date'))
    if not upcoming: upcoming=date(2026,7,28)
    changed=False
    while today>upcoming:
        s['last_completed_meeting_date']=upcoming.isoformat()
        upcoming=upcoming+timedelta(days=14)
        changed=True
    s['upcoming_meeting_date']=upcoming.isoformat()
    s['meeting_date']=s['upcoming_meeting_date']
    s['active_report_start_date']=s.get('last_completed_meeting_date') or '2026-07-14'
    if changed:
        s['report_status']='Stale'
    return changed
def period(s,off=0):
    rollover_meeting_cycle(s)
    st=pdate(s.get('last_completed_meeting_date') or s.get('active_report_start_date')); mt=pdate(s.get('upcoming_meeting_date') or s.get('meeting_date'))
    if off==0: start,meet=st,mt
    elif off>0: start,meet=mt+timedelta(days=14*(off-1)),mt+timedelta(days=14*off)
    else: start,meet=st+timedelta(days=14*off),st+timedelta(days=14*(off+1))
    end=meet-timedelta(days=1); eff=end-timedelta(days=LAG)
    return {'start':start.isoformat(),'end':end.isoformat(),'meeting':meet.isoformat(),'effective':eff.isoformat(),'key':f'{start.isoformat()}_{end.isoformat()}','days':(end-start).days+1,'off':off}
def sync_config(s):
    if not CONFIG.exists(): return
    c=rj(CONFIG,{}); p=period(s); c.update({'report_start_date':p['start'],'report_end_date':p['end'],'ranking_date':p['effective'],'sensor_tower_lag_days':LAG}); wj(CONFIG,c)
def stale(s): return s.get('report_status')=='Stale' or (s.get('last_scan_period_key') and s.get('last_scan_period_key')!=period(s)['key'])
def ovr(): return {r.get('unified_app_id'):r for r in rc(OVR) if r.get('unified_app_id')}
def save_ovr(o): wc(OVR,sorted(o.values(),key=lambda r:(r.get('deleted','No'),r.get('game_title',''))),OVR_FIELDS)
def log_change(s,action,uid,title,field,old,new,reason=''):
    a=rc(HIST); a.append({'timestamp':now(),'user':s.get('current_user','Local'),'action':action,'unified_app_id':uid,'game_title':title,'field':field,'previous_value':old,'new_value':new,'reason':reason}); wc(HIST,a,HIST_FIELDS)
def uid(r): return r.get('unified_app_id') or r.get('Unified App ID') or r.get('Game Title','')
def rows(include_deleted=False):
    o=ovr(); out=[]
    for r in rc(FINAL):
        x=dict(r); u=uid(x); y=o.get(u,{})
        if y.get('deleted')=='Yes' and not include_deleted: continue
        if y.get('override_signal_type'): x['Signal Type']=DISP_BACK.get(y['override_signal_type'],y['override_signal_type'])
        x['_uid']=u; x['Signal Display']=SIGDIS.get(x.get('Signal Type'),x.get('Signal Type','Emerging Market Signal')); x['Signal Definition']=SIGDEF.get(x.get('Signal Type'),x.get('Signal Definition',''))
        x['Starred']=y.get('starred','No') or 'No'; x['Excluded']=y.get('deleted','No') or 'No'; x['Discussion Notes']=y.get('notes',''); x['Approved Report Note']=y.get('approved_report_note','')
        x['Review Status']=y.get('review_status','Needs Review' if x.get('Signal Type')=='Early Market Signal' else 'Unreviewed') or 'Unreviewed'; x['Selected For Report']=y.get('selected_for_report','Yes') or 'Yes'; out.append(x)
    return sorted(out,key=lambda r:({'Strong Market Signal':0,'Early Market Signal':1}.get(r.get('Signal Type'),9),-sf(r.get('SG Gross Revenue')),r.get('Game Title','')))
def counts(rs):
    strong=[r for r in rs if r.get('Signal Type')=='Strong Market Signal']; emerging=[r for r in rs if r.get('Signal Type')!='Strong Market Signal']; review=[r for r in emerging if r.get('Review Status') not in ('Reviewed','Reported')]
    return {'total':len(rs),'strong':len(strong),'emerging':len(emerging),'review':len(review),'excluded':len([r for r in rows(True) if r.get('Excluded')=='Yes'])}
def downloads(t):
    m=re.search(r'SG \(\$[0-9,]+ / ([0-9,]+) DL\)',t or ''); return int(m.group(1).replace(',','')) if m else 0
def topm(t):
    m=re.search(r'Top Mkts: ([A-Z]{2})',t or ''); return m.group(1) if m else ''
def bestrank(t):
    n=[int(x) for x in re.findall(r'#(\d+)',t or '')]; return min(n) if n else 9999
def brief(rs):
    c=counts(rs); return f"{c['total']} new mobile launches were detected this period. {c['strong']} show established commercial traction, while {c['emerging']} remain emerging signals. {c['review']} games require analyst review."
def parse_timestamp(value):
    if not value:
        return None
    raw=str(value).strip()
    try:
        dt=datetime.fromisoformat(raw.replace('Z','+00:00'))
        if dt.tzinfo:
            dt=dt.astimezone(timezone(timedelta(hours=8)))
        return dt
    except ValueError:
        d=pdate(raw)
        return datetime.combine(d, datetime.min.time()) if d else None
def format_asof(dt, fallback_label=''):
    if not dt:
        return ''
    text=dt.strftime('%d %b %Y %H:%M') if (dt.hour or dt.minute or dt.second) else dt.strftime('%d %b %Y')
    return f'{text}{fallback_label}'
def data_asof(rs=None,p=None):
    meta=rj(ST_META,{})
    dt=parse_timestamp(meta.get('sensor_tower_data_as_of_date') or meta.get('last_successful_sensor_tower_refresh_at'))
    return format_asof(dt) if dt else 'N/A'
def highlight(rs):
    pubs={}
    for r in rs: pubs[r.get('Publisher') or 'Unknown']=pubs.get(r.get('Publisher') or 'Unknown',0)+1
    leader=max(rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={}); rank=min(rs,key=lambda r:bestrank(r.get('SG App Store Ranks')),default={}); em=max([r for r in rs if r.get('Signal Type')!='Strong Market Signal'],key=lambda r:sf(r.get('SG Gross Revenue')),default={}); pub=max(pubs.items(),key=lambda x:x[1],default=('No data',0))
    return [('Commercial Leader',leader.get('Game Title','No data'),f"Estimated SG gross revenue {money(leader.get('SG Gross Revenue'))}."),('Highest Ranked New Launch',rank.get('Game Title','No data'),f"Best SG chart rank #{bestrank(rank.get('SG App Store Ranks')) if rank else 'NA'}."),('Notable Emerging Signal',em.get('Game Title','No data'),'Emerging launch selected by available evidence.'),('Major Publisher Activity',pub[0],f'{pub[1]} launch record(s).'),('Analyst Attention Required',f"{counts(rs)['review']} games",'Emerging signals still need review.')]
def filter_rows(rs,q):
    text=q.get('q',[''])[0].lower().strip(); sig=q.get('signal',[''])[0]; sort=q.get('sort',['signal'])[0]; out=rs
    if text: out=[r for r in out if text in ' '.join(str(v).lower() for v in r.values())]
    if sig: out=[r for r in out if r.get('Signal Display')==sig or r.get('Signal Type')==sig]
    if sort=='revenue_desc': out=sorted(out,key=lambda r:-sf(r.get('SG Gross Revenue')))
    elif sort=='release_desc': out=sorted(out,key=lambda r:pdate(r.get('Release Date')) or date.min,reverse=True)
    elif sort=='title': out=sorted(out,key=lambda r:r.get('Game Title',''))
    return out

def card(a,b,c=''):
    return f'<div class="card"><small>{esc(a)}</small><b>{esc(b)}</b><p>{esc(c)}</p></div>'

def exports():
    return '<div class="exports"><a href="/export/print.html"><b>Print-friendly HTML</b><span>Executive</span></a><a href="/export/executive.csv"><b>Executive CSV</b><span>App IDs excluded</span></a><a href="/export/strong.csv"><b>Strong only</b></a><a href="/export/emerging.csv"><b>Emerging only</b></a><a href="/export/launches.csv"><b>Full analyst dataset</b></a><a href="/export/evidence.csv"><b>Detailed evidence</b><span>Includes app IDs</span></a></div>'

def layout(path,s,content):
    rs=rows(); p=period(s); st='Stale' if stale(s) else s.get('report_status','Draft')
    banner='<div class="stale">This report is stale because the reporting dates changed after the last scan. Run the market scan again before finalising or exporting it.</div>' if stale(s) else ''
    nav=''.join(f'<a class="{"on" if path==u else ""}" href="{u}">{n}</a>' for u,n in [('/market-brief','Market Brief'),('/data-export','Data Export'),('/calendar','Calendar'),('/admin','Admin')])
    role=''.join(f'<option {"selected" if s.get("current_role")==r else ""}>{r}</option>' for r in ['Viewer','Contributor','Admin'])
    user=''.join(f'<option {"selected" if s.get("current_user")==u else ""}>{u}</option>' for u in ['Shauna','Daryl','Contributor','Viewer'])
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IBD Market Intelligence</title><style>{CSS}</style><script>{JS}</script></head><body><div class="shell"><aside><b>IBD Market Intelligence</b><h1>Singapore · Mobile Launch Discovery</h1><span>Proof of Concept</span><nav>{nav}</nav><p class="future">Future: PC & Console · Announcements · News · Events · Country Comparison · Evidence Library</p></aside><div><header><div><small>Selected period</small><b>{nd(p['start'])} to {nd(p['end'])}</b></div><div><small>Meeting date</small><b>{nd(p['meeting'])}</b></div><div><small>Data as of</small><b>{data_asof(rs,p)}</b></div><div><small>Last refreshed</small><b>{esc(s.get('last_scan_at') or 'Not recorded')}</b></div><div><small>Status</small><b class="pill">{esc(st)}</b></div><form method="post" action="/set-role"><select name="user">{user}</select><select name="role">{role}</select><button>Switch</button></form></header>{banner}<main>{content}</main></div></div></body></html>'''

def list_small(rs):
    if not rs: return '<p class="empty">No rows.</p>'
    return '<ul class="mini">'+''.join(f'<li><b>{esc(r.get("Game Title"))}</b><span>{esc(r.get("Publisher"))} · {money(r.get("SG Gross Revenue"))}</span></li>' for r in rs[:5])+'</ul>'

def market(s,q,msg=''):
    rs=rows(); c=counts(rs); hs=''.join(card(*h) for h in highlight(rs))
    ready=[('Scan complete',FINAL.exists(),'Final workflow output file is present.'),('Metrics available',any('SG Gross Revenue' in r for r in rs),'SEA6 / SG metrics loaded.'),('Strong signals reviewed',c['strong']>0,'Strong section available.'),('Emerging signals requiring review',c['review']==0,f"{c['review']} emerging game(s) still need review."),('Report note status',sum(1 for r in rs if r.get('Approved Report Note'))>0,'Approved notes are optional for executive output.')]
    rd=''.join(f'<li class="{"ok" if ok else "warn"}"><b>{esc(a)}</b><span>{esc(t)}</span></li>' for a,ok,t in ready)
    m=f'<div class="toast">{esc(msg)}</div>' if msg else ''
    return m+f'<section class="head"><div><em>Market Brief</em><h2>Singapore Mobile Launch Brief</h2><p>{esc(brief(rs))}</p></div><div><a class="btn blue" href="/export/print.html">Print-friendly HTML</a><a class="btn" href="/export/executive.csv">Executive CSV</a></div></section><section class="grid four">{card("Detected launches",c["total"])}{card("Strong signals",c["strong"],"SG gross revenue exceeded ,000 during the release/report period.")}{card("Emerging signals",c["emerging"],"Relevance still developing.")}{card("Needs review",c["review"])}</section><section class="panel"><h3>Important highlights</h3><div class="grid five">{hs}</div></section><section class="grid two"><div class="signal strong"><h3>Strong Market Signal</h3><p>SG gross revenue exceeded ,000 during the release/report period.</p>{list_small([r for r in rs if r.get("Signal Type")=="Strong Market Signal"])}</div><div class="signal emerging"><h3>Emerging Market Signal</h3><p>A new SG launch has been detected; commercial relevance is still developing.</p>{list_small([r for r in rs if r.get("Signal Type")!="Strong Market Signal"])}</div></section><section class="panel"><h3>Report readiness</h3><ul class="ready">{rd}</ul></section><section class="panel"><h3>Quick export</h3>{exports()}</section>'

def filters(q):
    return f'<form class="filters"><input name="q" value="{esc(q.get("q",[""])[0])}" placeholder="Search game, publisher, genre"><select name="signal"><option value="">All signals</option><option {"selected" if q.get("signal",[""])[0]=="Strong Market Signal" else ""}>Strong Market Signal</option><option {"selected" if q.get("signal",[""])[0]=="Emerging Market Signal" else ""}>Emerging Market Signal</option></select><select name="sort"><option value="signal">Signal then SG revenue</option><option value="revenue_desc">SG revenue high to low</option><option value="release_desc">Newest release date</option><option value="title">Game title A-Z</option></select><button>Apply</button><a class="btn" href="/launches">Reset</a></form>'

def bulk(s):
    if not can(s,'classify'): return ''
    return '<div class="bulk"><select name="action"><option value="star">Star</option><option value="unstar">Unstar</option><option value="strong">Mark Strong</option><option value="emerging">Mark Emerging</option><option value="reviewed">Mark Reviewed</option><option value="select_report">Include in Brief</option><option value="hide_report">Hide from Brief</option><option value="exclude">Exclude</option><option value="restore">Restore</option></select><input name="note" placeholder="Optional reason / discussion note"><button>Apply</button></div>'

def table(rs,s,select=True):
    if not rs: return '<p class="empty">No rows match.</p>'
    th='<th><input type="checkbox" onclick="tog(this)"></th>' if select and can(s,'classify') else ''
    body=''
    for r in rs:
        chk=f'<td><input type="checkbox" name="selected" value="{esc(r.get("_uid"))}"></td>' if select and can(s,'classify') else ''
        rank=bestrank(r.get('SG App Store Ranks'))
        body+=f'<tr>{chk}<td><a href="/launches?selected={esc(r.get("_uid"))}">{esc(r.get("Game Title"))}</a></td><td>{esc(r.get("Publisher"))}</td><td>{esc(r.get("Platform"))}</td><td>{esc(display_date(r.get("Release Date")) or "")}</td><td>{esc(r.get("Genre"))}</td><td><span class="sig {"strong" if r.get("Signal Type")=="Strong Market Signal" else "em"}">{esc(r.get("Signal Display"))}</span></td><td class="num">{money(r.get("SG Gross Revenue"))}</td><td class="num">{downloads(r.get("Top 3 Markets")):,}</td><td>{esc(topm(r.get("Top 3 Markets")))}</td><td class="num">{rank if rank!=9999 else "NA"}</td><td>{esc(r.get("Review Status"))}</td><td>{"★" if r.get("Starred")=="Yes" else "☆"}</td></tr>'
    return f'<div class="table"><table><thead><tr>{th}<th>Game Title</th><th>Publisher</th><th>Platform</th><th>SG Release Date</th><th>Genre</th><th>Signal</th><th class="num">Estimated SG Gross Revenue</th><th class="num">SG Downloads</th><th>Top Market</th><th class="num">SG Rank</th><th>Review Status</th><th>Starred</th></tr></thead><tbody>{body}</tbody></table></div>'

def drawer(u,s):
    if not u: return ''
    r=next((x for x in rows(True) if x.get('_uid')==u),None)
    if not r: return ''
    h=''.join(f'<li><b>{esc(x.get("field"))}</b>: {esc(x.get("previous_value"))} → {esc(x.get("new_value"))}<small>{esc(x.get("timestamp"))} · {esc(x.get("user"))}</small></li>' for x in reversed(rc(HIST)) if x.get('unified_app_id')==u) or '<li>No changes recorded.</li>'
    act=''
    if can(s,'annotate'):
        act=f'<form method="post" action="/single-action"><input type="hidden" name="selected" value="{esc(u)}"><select name="action"><option value="star">Star</option><option value="unstar">Unstar</option><option value="strong">Mark Strong</option><option value="emerging">Mark Emerging</option><option value="reviewed">Mark Reviewed</option><option value="select_report">Include in Brief</option><option value="hide_report">Hide from Brief</option><option value="exclude">Exclude</option><option value="restore">Restore</option></select><textarea name="note" placeholder="Discussion note"></textarea><textarea name="approved_report_note" placeholder="Approved report note — eligible for executive output">{esc(r.get("Approved Report Note"))}</textarea><button>Save</button></form>'
    return f'<aside class="drawer"><a href="/launches">Close</a><h3>{esc(r.get("Game Title"))}</h3><p class="tabs">Summary · Market Performance · Evidence · Notes · Change History</p><dl><dt>Publisher</dt><dd>{esc(r.get("Publisher"))}</dd><dt>Signal</dt><dd>{esc(r.get("Signal Display"))}</dd><dt>Top Markets</dt><dd>{esc(r.get("Top 3 Markets"))}</dd><dt>SG Ranks</dt><dd>{esc(r.get("SG App Store Ranks"))}</dd><dt>Exact app IDs</dt><dd>{esc(u)}</dd><dt>Release-date evidence</dt><dd>{esc(display_date(r.get("Release Date")) or "")}</dd><dt>Discovery date</dt><dd>{esc(r.get("run_timestamp_utc"))}</dd><dt>Unified-family warning</dt><dd>{"Check iOS / Android mapping if platform metadata conflicts." if " / " in r.get("Platform","") else "Single-platform record."}</dd><dt>Discussion Notes</dt><dd>{esc(r.get("Discussion Notes")) or "None"}</dd><dt>Approved Report Note</dt><dd>{esc(r.get("Approved Report Note")) or "None"}</dd></dl>{act}<h4>Change history</h4><ul class="hist">{h}</ul></aside>'

def launches(s,q):
    rs=filter_rows(rows(True),q); u=q.get('selected',[''])[0]
    return f'<section class="head"><div><em>Launch database</em><h2>Launches</h2><p>Search, filter, classify, annotate, and export SG mobile launch records.</p></div><div><a class="btn" href="/export/launches.csv">Export filtered rows</a><a class="btn" href="/export/evidence.csv">Detailed evidence</a></div></section><section class="panel">{filters(q)}<p class="muted">Full app IDs and evidence sit in the detail drawer or evidence export.</p></section><div class="split"><section class="panel"><form method="post" action="/bulk-action">{bulk(s)}{table(rs,s)}</form></section>{drawer(u,s)}</div>'

def report_cards(rs):
    out=''
    for sig in ['Strong Market Signal','Early Market Signal']:
        gr=[r for r in rs if r.get('Signal Type')==sig and r.get('Selected For Report')!='No']; cards=''
        for r in gr:
            note=f"<p class='note'>{esc(r.get('Approved Report Note'))}</p>" if r.get('Approved Report Note') else ''
            cards+=f'<article><h4>{esc(r.get("Game Title"))}</h4><p><b>Platform:</b> {esc(r.get("Platform"))}</p><p><b>Publisher:</b> {esc(r.get("Publisher"))}</p><p><b>Genre:</b> {esc(r.get("Genre"))}</p><p><b>SG Release Date:</b> {esc(display_date(r.get("Release Date")) or "")}</p><p>{esc(r.get("Top 3 Markets"))}</p><p>{esc(r.get("SG App Store Ranks"))}</p>{note}</article>'
        if gr: out+=f'<div class="report"><h3>{SIGDIS[sig]}</h3><p>{SIGDEF[sig]}</p><div class="grid two">{cards}</div></div>'
    return out or '<p class="empty">No selected report rows.</p>'

def history(s):
    rs=rows(); c=counts(rs); p=period(s)
    cards=f'<div class="history"><span>Portal Report</span><h3>{nd(p["start"])} to {nd(p["end"])}</h3><p>Status: {esc(s.get("report_status"))}</p><p>Strong {c["strong"]} · Emerging {c["emerging"]} · SG revenue {money(sum(sf(r.get("SG Gross Revenue")) for r in rs))}</p></div>'
    legacy=ROOT/'data'/'backtest_jan_to_jun_2026_discover_later_assign_back'/'combined_final_sg_market_scan_backfilled.csv'
    if legacy.exists(): cards+='<div class="history legacy"><span>Legacy Report</span><h3>Jan-Jun 2026 backtest</h3><p>Preserved in legacy structure; not forced into portal schema.</p></div>'
    for f in sorted(SNAP.glob('*.csv'),reverse=True)[:6]: cards+=f'<div class="history"><span>Portal Report Revision</span><h3>{esc(f.stem)}</h3><p>Immutable local snapshot.</p></div>'
    return f'<div class="grid three">{cards}</div>'

def compare(rs):
    leader=max(rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
    return f'<p class="briefline">Current period contains {counts(rs)["strong"]} strong signal(s) and {counts(rs)["emerging"]} emerging signal(s). Highest-performing release by SG gross revenue is {esc(leader.get("Game Title","No data"))}.</p><div class="grid four">{card("Estimated SG revenue",money(sum(sf(r.get("SG Gross Revenue")) for r in rs)))}{card("Highest performer",leader.get("Game Title","No data"),money(leader.get("SG Gross Revenue")))}{card("Rows",len(rs))}{card("Comparison","Select two saved periods after more snapshots exist.")}</div>'

def cal(s):
    tr=''.join(f'<tr><td>{"Current" if i==0 else i}</td><td>{nd(period(s,i)["start"])} to {nd(period(s,i)["end"])}</td><td>{nd(period(s,i)["meeting"])}</td><td>{nd(period(s,i)["effective"])}</td><td>{esc(s.get("report_status") if i==0 else "Planned")}</td></tr>' for i in range(-2,4))
    return f'<div class="table"><table><thead><tr><th>Cycle</th><th>Report window</th><th>Meeting</th><th>Data effective</th><th>Status</th></tr></thead><tbody>{tr}</tbody></table></div>'

def reports(s,q):
    rs=rows(); view=q.get('view',['current'])[0]; mode=q.get('mode',['brief'])[0]
    tabs=''.join(f'<a class="{"on" if view==k else ""}" href="/reports?view={k}">{n}</a>' for k,n in [('current','Current'),('history','History'),('compare','Compare'),('calendar','Calendar')])
    if view=='history': body=history(s)
    elif view=='compare': body=compare(rs)
    elif view=='calendar': body=cal(s)
    else:
        mt=''.join(f'<a class="{"on" if mode==k else ""}" href="/reports?view=current&mode={k}">{n}</a>' for k,n in [('brief','Brief'),('report','Report'),('data','Data')])
        if mode=='report': inner=report_cards(rs)
        elif mode=='data': inner=table(rs,s,False)
        else: inner=f'<p class="briefline">{esc(brief(rs))}</p><div class="grid four">{card("Strong",counts(rs)["strong"])}{card("Emerging",counts(rs)["emerging"])}{card("SG revenue",money(sum(sf(r.get("SG Gross Revenue")) for r in rs)))}{card("Status","Stale" if stale(s) else s.get("report_status"))}</div>'
        body=mt+inner
    return f'<section class="head"><div><em>Reports</em><h2>Reports</h2><p>Current output, history, comparison, and reporting calendar.</p></div><div><a class="btn blue" href="/export/print.html">Print report</a><a class="btn" href="/export/executive.csv">Executive CSV</a></div></section><section class="panel"><div class="tabs">{tabs}</div>{body}</section>'

def review(s,q):
    queues=[('needs','Needs Attention'),('emerging','Emerging'),('promoted','Manually Promoted'),('starred','Starred'),('excluded','Excluded'),('reported','Reported')]; active=q.get('queue',['needs'])[0]
    def qrows(k):
        rs=rows(True); o=ovr(); out=[]
        for r in rs:
            ok=(k=='needs' and r.get('Excluded')!='Yes' and r.get('Review Status') not in ('Reviewed','Reported')) or (k=='emerging' and r.get('Excluded')!='Yes' and r.get('Signal Type')!='Strong Market Signal') or (k=='promoted' and o.get(r.get('_uid'),{}).get('override_signal_type')=='Strong Market Signal') or (k=='starred' and r.get('Starred')=='Yes') or (k=='excluded' and r.get('Excluded')=='Yes') or (k=='reported' and r.get('Review Status')=='Reported')
            if ok: out.append(r)
        return out
    rs=qrows(active); sel=q.get('selected',[rs[0].get('_uid') if rs else ''])[0]
    left=''.join(f'<a class="{"on" if active==k else ""}" href="/review?queue={k}"><span>{n}</span><b>{len(qrows(k))}</b></a>' for k,n in queues)
    mid=''.join(f'<a class="item" href="/review?queue={active}&selected={esc(r.get("_uid"))}"><b>{esc(r.get("Game Title"))}</b><span>{esc(r.get("Signal Display"))} · {money(r.get("SG Gross Revenue"))}</span></a>' for r in rs) or '<p class="empty">Queue empty.</p>'
    return f'<section class="head"><div><em>Review</em><h2>Analyst triage inbox</h2><p>Separate discussion notes from approved report notes. Use Exclude, not Delete.</p></div><div><a class="btn" href="/export/review.csv">Internal review export</a><a class="btn" href="/export/admin.csv">Override history</a></div></section><section class="review"><aside>{left}</aside><div class="panel"><form method="post" action="/bulk-action">{bulk(s)}<div class="items">{mid}</div></form></div>{drawer(sel,s)}</section>'

def operations(s,q,msg=''):
    p=period(s); pv=q.get('preview_date',[''])[0]; preview=''
    if pv:
        m=pdate(pv); st=pdate(s['active_report_start_date'])
        if m and m>st:
            preview=f'<div class="confirm"><h3>Confirm reporting date change</h3><p><b>Old meeting:</b> {nd(p["meeting"])}<br><b>Proposed meeting:</b> {nd(pv)}<br><b>Old period:</b> {nd(p["start"])} to {nd(p["end"])}<br><b>New period:</b> {nd(st)} to {nd(m-timedelta(days=1))}<br><b>Future cadence:</b> next cycles continue every 14 days from {nd(pv)}.<br><b>Rerun:</b> report will be marked Stale.</p><form method="post" action="/confirm-date-change"><input type="hidden" name="meeting_date" value="{esc(pv)}"><button>Confirm and mark stale</button><a class="btn" href="/operations">Cancel</a></form></div>'
        else: preview='<p class="error">Invalid meeting date.</p>'
    if can(s,'run'):
        admin=f'<section class="panel"><h3>Run Market Scan</h3><p>Uses the current proof-of-concept Sensor Tower layer outputs and preserves overrides. Finalised snapshots are not silently changed.</p><div class="pipeline"><div>1. Retrieve SG ranking candidates</div><div>2. Resolve app identities</div><div>3. Fetch metadata</div><div>4. Fetch SEA6 performance</div><div>5. Build report and review queue</div></div><form method="post" action="/run-scan"><button class="blue">Run Market Scan</button></form><details><summary>View Technical Details</summary><p>Calls scripts/current_report_watchlist_workflow.py. Token values are never displayed.</p></details></section><section class="panel"><h3>Reporting dates</h3><form class="filters" method="post" action="/preview-date-change"><label>Upcoming Meeting Date <input type="date" name="meeting_date" value="{esc(p["meeting"])}"></label><button>Preview change</button></form>{preview}</section><section class="panel"><h3>Finalisation</h3><p>Scan completes → draft generated → contributors review → approved notes added → Ready → Admin finalises → immutable snapshot stored. Corrections create revisions.</p><form method="post" action="/set-report-status"><button name="status" value="Ready">Mark Ready</button><button name="status" value="Finalised">Finalise Snapshot</button><button name="status" value="Draft">Reopen Draft</button></form></section>'
    else: admin='<section class="panel"><p class="empty">Operational controls are hidden for this role.</p></section>'
    diag=''
    if can(s,'diagnostics'):
        files=''.join(f'<tr><td>{esc(f.name)}</td><td>{"Present" if f.exists() else "Missing"}</td></tr>' for f in [FINAL,WATCH,OVR,HIST,DECISIONS])
        cfg=''.join(f'<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>' for k,v in public_config().items())
        diag=f'<section class="panel"><h3>Diagnostics</h3><details><summary>View Technical Details</summary><table>{files}</table><table>{cfg}</table></details></section>'
    toast=f'<div class="toast">{esc(msg)}</div>' if msg else ''
    return f'<section class="head"><div><em>Operations</em><h2>Operations</h2><p>Scan controls, reporting dates, definitions, exports, and diagnostics.</p></div></section>{toast}{admin}<section class="panel"><h3>Definitions and thresholds</h3><div class="grid four">{card("Strong Market Signal","SG gross revenue exceeded ,000 during the release/report period.")}{card("Emerging Market Signal","New SG launch detected; relevance still developing.")}{card("Revenue","Gross dollars","Not store revenue cents.")}{card("Data lag",f"Report end -{LAG} day")}</div></section><section class="panel"><h3>Export centre</h3>{exports()}</section><section class="panel"><h3>Persistence boundary</h3><p>Current storage is local CSV/JSON. Migration boundary is local CSV → SQLite → shared PostgreSQL or equivalent database. CSV is not sufficient for real multi-user deployment.</p></section>{diag}'

def update(s,selected,action,note='',approved=''):
    if not selected: return 'No rows selected.'
    if action in ('strong','emerging') and not can(s,'classify'): return 'Role cannot classify.'
    if action in ('exclude','restore') and not can(s,'exclude'): return 'Role cannot exclude/restore.'
    o=ovr(); base={uid(r):r for r in rc(FINAL)}
    for u in selected:
        src=base.get(u,{}); r=o.get(u,{k:'' for k in OVR_FIELDS}); r['unified_app_id']=u; r['game_title']=src.get('Game Title',r.get('game_title',''))
        def setf(field,val,act=action):
            old=r.get(field,''); r[field]=val; log_change(s,act,u,r['game_title'],field,old,val,note)
        if action=='strong': setf('override_signal_type','Strong Market Signal')
        elif action=='emerging': setf('override_signal_type','Early Market Signal')
        elif action=='star': setf('starred','Yes')
        elif action=='unstar': setf('starred','No')
        elif action=='exclude': setf('deleted','Yes')
        elif action=='restore': setf('deleted','No')
        elif action=='reviewed': setf('review_status','Reviewed')
        elif action=='select_report': setf('selected_for_report','Yes')
        elif action=='hide_report': setf('selected_for_report','No')
        if note: r['notes']=(r.get('notes','')+'\n' if r.get('notes') else '')+f'[{s.get("current_user")}, {now()}] {note}'
        if approved: setf('approved_report_note',approved,'approved_note')
        r['updated_at']=now(); o[u]=r
    save_ovr(o); return f'Updated {len(selected)} row(s).'

def run_scan(s):
    if s.get('scan_running'): return 'A scan is already running.'
    s['scan_running']=True; s['report_status']='Scan Running'; save_state(s)
    try:
        res=subprocess.run(['py',str(ROOT/'scripts'/'current_report_watchlist_workflow.py')],cwd=str(ROOT),text=True,capture_output=True,timeout=180)
        if res.returncode:
            s['report_status']='Review Required'; raise RuntimeError(res.stderr.strip() or res.stdout.strip() or 'Workflow failed')
        s['last_scan_at']=now(); s['last_scan_period_key']=period(s)['key']; s['report_status']='Review Required' if counts(rows()).get('review') else 'Draft'; return 'Market scan build completed. Review before exporting.'
    finally:
        s['scan_running']=False; save_state(s)

def exec_rows(kind,q):
    rs=rows(kind in ('launches','evidence','review'))
    if kind=='strong': rs=[r for r in rs if r.get('Signal Type')=='Strong Market Signal']
    if kind in ('emerging','early'): rs=[r for r in rs if r.get('Signal Type')!='Strong Market Signal']
    if kind=='starred': rs=[r for r in rs if r.get('Starred')=='Yes']
    if kind=='launches': rs=filter_rows(rs,q)
    return rs

def print_html(s):
    return f"<html><head><meta charset='utf-8'><style>{PRINT}</style></head><body><h1>Singapore Mobile Launch Brief</h1><p>{nd(period(s)['start'])} to {nd(period(s)['end'])} · Generated {todaystamp()}</p><p>{esc(brief(rows()))}</p>{report_cards(rows())}</body></html>".encode()


# --- Product-quality refinement overrides ---
def display_name(r):
    return r.get('English Display Title') or r.get('display_title') or r.get('Game Title') or r.get('Original Title') or ''

def title_status(r):
    if r.get('manual_english_title') or r.get('Manual English Title'):
        return 'Manual Title'
    st=(r.get('Translation Review Status') or r.get('translation_review_status') or '').lower()
    src=(r.get('Translation Source') or r.get('translation_source') or '').lower()
    if st=='not_required': return 'Original English'
    if src in ('argos_local','alias_glossary','official','official_ip_root','franchise_mapping','latin_normalized','controlled_translation','official_evidence_cached','unified_id_mapping','title_mapping','already_latin'): return 'Canonicalized'
    if src=='failed_or_unavailable': return 'Unresolved'
    if st=='needs_review': return 'Needs Title Review'
    return 'Unknown'

def has_attention(r):
    if (r.get('Translation Review Status') or '').lower()=='needs_review': return True
    if not r.get('Release Date') or not r.get('SG App Store Ranks'): return True
    if not r.get('Top 3 Markets') or r.get('SG Gross Revenue','') in ('','NA'): return True
    if r.get('Review Status')=='Override Pending Approval': return True
    return False

def counts(rs):
    strong=[r for r in rs if r.get('Signal Type')=='Strong Market Signal']
    emerging=[r for r in rs if r.get('Signal Type')!='Strong Market Signal']
    attention=[r for r in rs if has_attention(r)]
    return {'total':len(rs),'strong':len(strong),'emerging':len(emerging),'review':len(attention),'attention':len(attention),'excluded':len([r for r in rows(True) if r.get('Excluded')=='Yes'])}

def rows(include_deleted=False):
    o=ovr(); out=[]
    for r in rc(FINAL):
        x=dict(r); u=uid(x); y=o.get(u,{})
        if y.get('deleted')=='Yes' and not include_deleted: continue
        if y.get('override_signal_type'): x['Signal Type']=DISP_BACK.get(y['override_signal_type'],y['override_signal_type'])
        if y.get('manual_english_title'):
            x['Manual English Title']=y.get('manual_english_title')
            x['English Display Title']=y.get('manual_english_title')
            x['Game Title']=y.get('manual_english_title')
        if y.get('translation_review_status'): x['Translation Review Status']=y.get('translation_review_status')
        if y.get('translation_note'): x['Translation Note']=y.get('translation_note')
        x['_uid']=u; x['Signal Display']=SIGDIS.get(x.get('Signal Type'),x.get('Signal Type','Emerging Market Signal'))
        x['Signal Definition']=SIGDEF.get(x.get('Signal Type'),x.get('Signal Definition',''))
        x['Starred']=y.get('starred','No') or 'No'; x['Excluded']=y.get('deleted','No') or 'No'; x['Discussion Notes']=y.get('notes',''); x['Approved Report Note']=y.get('approved_report_note','')
        x['Review Status']=y.get('review_status','Review Needed' if has_attention(x) else 'Unreviewed') or 'Unreviewed'; x['Selected For Report']=y.get('selected_for_report','Yes') or 'Yes'; x['Title Status']=title_status(x)
        out.append(x)
    return sorted(out,key=lambda r:({'Strong Market Signal':0,'Early Market Signal':1}.get(r.get('Signal Type'),9),-sf(r.get('SG Gross Revenue')),display_name(r)))

def hero_leader(rs):
    leader=max(rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
    if not leader: return '<div class="leader empty">No commercial leader yet.</div>'
    rank=bestrank(leader.get('SG App Store Ranks'))
    return f'<div class="leader"><div><span class="sig strong">Strong Market Signal</span><h3>{esc(display_name(leader))}</h3><p>{esc(leader.get("Publisher"))}</p></div><div class="leader-money">{money(leader.get("SG Gross Revenue"))}<small>Estimated SG gross revenue</small></div><dl><dt>SG Rank</dt><dd>#{rank if rank!=9999 else "NA"}</dd><dt>Top Markets</dt><dd>{esc(leader.get("Top 3 Markets"))}</dd></dl></div>'

def market(s,q,msg=''):
    rs=rows(); c=counts(rs); leader=max(rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
    statement=f"{c['total']} new mobile launches were detected this period. {c['strong']} show established commercial traction, while {c['emerging']} remain emerging signals."
    if leader: statement+=f" {display_name(leader)} leads the period with estimated SG gross revenue of {money(leader.get('SG Gross Revenue'))}."
    hs=''.join(card(*h) for h in highlight(rs)[1:])
    rd=''.join(f'<li class="{"ok" if ok else "warn"}"><b>{esc(a)}</b><span>{esc(t)}</span></li>' for a,ok,t in [('Scan complete',FINAL.exists(),'Final output file is present.'),('Metrics available',any('SG Gross Revenue' in r for r in rs),'SEA6 / SG metrics loaded.'),('Strong signals reviewed',c['strong']>0,'Strong section available.'),('Attention items',c['attention']==0,f"{c['attention']} item(s) require action."),('Report status',not stale(s),'Fresh unless dates changed after scan.')])
    m=f'<div class="toast">{esc(msg)}</div>' if msg else ''
    attention_card=card('Attention Items',c['attention'],'No attention items.' if c['attention']==0 else 'Items requiring analyst action.')
    return m+f'<section class="brief-hero"><div class="brief-copy"><em>Market Brief</em><h2>Singapore Mobile Launch Brief</h2><p>{esc(statement)}</p><div class="mix"><span><b>{c["strong"]}</b> Strong</span><span><b>{c["emerging"]}</b> Emerging</span><span><b>{c["attention"]}</b> Attention</span></div></div>{hero_leader(rs)}</section><section class="grid four kpis">{card("Detected Launches",c["total"],"New SG mobile launches in this period.")}{card("Strong Signals",c["strong"],"SG gross revenue exceeded ,000 during the release/report period.")}{card("Emerging Signals",c["emerging"],"Commercial relevance is still developing.")}{attention_card}</section><section class="panel highlight-panel"><h3>Supporting highlights</h3><div class="grid four">{hs}</div></section><section class="grid two"><div class="signal strong"><h3>Strong Market Signal</h3><p>SG gross revenue exceeded ,000 during the release/report period.</p>{list_small([r for r in rs if r.get("Signal Type")=="Strong Market Signal"])}</div><div class="signal emerging"><h3>Emerging Market Signal</h3><p>A new SG launch has been detected; commercial relevance is still developing.</p>{list_small([r for r in rs if r.get("Signal Type")!="Strong Market Signal"])}</div></section><section class="panel"><h3>Report readiness</h3><ul class="ready">{rd}</ul></section>'

def table(rs,s,select=True):
    if not rs: return '<p class="empty">No rows match.</p>'
    th='<th><input type="checkbox" onclick="tog(this)"></th>' if select and can(s,'classify') else ''
    body=''
    for r in rs:
        chk=f'<td><input type="checkbox" name="selected" value="{esc(r.get("_uid"))}"></td>' if select and can(s,'classify') else ''
        rank=bestrank(r.get('SG App Store Ranks')); tstat=title_status(r); att=' attention' if has_attention(r) else ''
        title=f'<b>{esc(display_name(r))}</b>' + (f'<small>Original: {esc(r.get("Original Title"))}</small>' if r.get('Original Title') and r.get('Original Title')!=display_name(r) else '')
        body+=f'<tr class="{att}">{chk}<td><a class="rowtitle" href="/launches?selected={esc(r.get("_uid"))}">{title}</a></td><td>{esc(r.get("Publisher"))}</td><td>{esc(r.get("Platform"))}</td><td>{esc(display_date(r.get("Release Date")) or "")}</td><td>{esc(r.get("Genre"))}</td><td><span class="sig {"strong" if r.get("Signal Type")=="Strong Market Signal" else "em"}">{esc(r.get("Signal Display"))}</span></td><td class="num">{money(r.get("SG Gross Revenue"))}</td><td class="num">{downloads(r.get("Top 3 Markets")):,}</td><td>{esc(topm(r.get("Top 3 Markets")))}</td><td class="num">{rank if rank!=9999 else "NA"}</td><td><span class="status {"warn" if has_attention(r) else "neutral"}">{esc(r.get("Review Status"))}</span></td><td><span class="titlebadge {"warn" if "Review" in tstat or "Failed" in tstat else "ok"}">{esc(tstat)}</span></td><td>{"★" if r.get("Starred")=="Yes" else "☆"}</td></tr>'
    return f'<div class="table"><table><thead><tr>{th}<th>Game Title / Display Title</th><th>Publisher</th><th>Platform</th><th>SG Release Date</th><th>Genre</th><th>Signal</th><th class="num">Estimated SG Gross Revenue</th><th class="num">SG Downloads</th><th>Top Market</th><th class="num">SG Rank</th><th>Review Status</th><th>Title Status</th><th>Starred</th></tr></thead><tbody>{body}</tbody></table></div>'

def title_stats():
    rs=rows(True)
    return {
        'total':len(rs),
        'english':len([r for r in rs if title_status(r)=='Original English']),
        'auto':len([r for r in rs if title_status(r)=='Canonicalized']),
        'manual':len([r for r in rs if title_status(r)=='Manual Title']),
        'needs':len([r for r in rs if 'Review' in title_status(r)]),
        'failed':len([r for r in rs if title_status(r)=='Unresolved']),
    }

def filters(q):
    return f'<form class="filters"><input name="q" value="{esc(q.get("q",[""])[0])}" placeholder="Search title, publisher, genre"><select name="signal"><option value="">All signals</option><option {"selected" if q.get("signal",[""])[0]=="Strong Market Signal" else ""}>Strong Market Signal</option><option {"selected" if q.get("signal",[""])[0]=="Emerging Market Signal" else ""}>Emerging Market Signal</option></select><select name="sort"><option value="signal">Signal then SG revenue</option><option value="revenue_desc">SG revenue high to low</option><option value="release_desc">Newest release date</option><option value="title">Game title A-Z</option></select><button>Apply</button><a class="btn" href="/launches">Reset</a></form>'

def launches(s,q):
    rs=filter_rows(rows(True),q); u=q.get('selected',[''])[0]; c=counts(rs)
    summary=f'<div class="summary-strip">{card("Total Launches",len(rs))}{card("Strong",c["strong"])}{card("Emerging",c["emerging"])}{card("Attention",c["attention"])}<div class="card selectcount"><small>Selection</small><b id="selectedCount">0</b><p>Rows selected</p></div></div>'
    return f'<section class="head"><div><em>Launch database</em><h2>Launches</h2><p>Search, filter, classify, annotate, and export SG mobile launch records.</p></div><div><a class="btn" href="/export/launches.csv">Export filtered rows</a><a class="btn" href="/export/evidence.csv">Detailed evidence</a></div></section>{summary}<section class="panel filter-panel">{filters(q)}<p class="muted">Executive views use English Display Title. Analyst views preserve Original Title and title-review status.</p></section><div class="split"><section class="panel"><form method="post" action="/bulk-action">{bulk(s)}{table(rs,s)}</form></section>{drawer(u,s)}</div>'

def drawer(u,s):
    if not u: return ''
    r=next((x for x in rows(True) if x.get('_uid')==u),None)
    if not r: return ''
    h=''.join(f'<li><b>{esc(x.get("field"))}</b>: {esc(x.get("previous_value"))} → {esc(x.get("new_value"))}<small>{esc(x.get("timestamp"))} · {esc(x.get("user"))}</small></li>' for x in reversed(rc(HIST)) if x.get('unified_app_id')==u) or '<li>No changes recorded.</li>'
    act=''
    if can(s,'annotate'):
        act=f'<form method="post" action="/single-action" class="drawerform"><input type="hidden" name="selected" value="{esc(u)}"><div class="action-row"><select name="action"><option value="star">Star</option><option value="unstar">Unstar</option><option value="strong">Mark Strong</option><option value="emerging">Mark Emerging</option><option value="reviewed">Mark Reviewed</option><option value="reported">Mark Reported</option><option value="exclude">Exclude</option><option value="restore">Restore</option></select><button>Save Action</button></div><label>Manual English Title<input name="manual_english_title" value="{esc(r.get("Manual English Title"))}" placeholder="Optional analyst title override"></label><label>Title Review Status<select name="translation_review_status"><option value="">Keep current</option><option value="not_required">Not required</option><option value="needs_review">Needs review</option><option value="reviewed">Reviewed</option></select></label><textarea name="translation_note" placeholder="Translation note">{esc(r.get("Translation Note"))}</textarea><textarea name="note" placeholder="Discussion note"></textarea><textarea name="approved_report_note" placeholder="Approved report note — eligible for executive output">{esc(r.get("Approved Report Note"))}</textarea></form>'
    return f'<aside class="drawer"><a href="/launches">Close</a><h3>{esc(display_name(r))}</h3><div class="drawer-tabs"><span>Overview</span><span>Evidence</span><span>Notes</span><span>History</span></div><section class="drawer-section"><h4>Overview</h4><dl><dt>Original Title</dt><dd>{esc(r.get("Original Title"))}</dd><dt>Publisher</dt><dd>{esc(r.get("Publisher"))}</dd><dt>Signal</dt><dd><span class="sig {"strong" if r.get("Signal Type")=="Strong Market Signal" else "em"}">{esc(r.get("Signal Display"))}</span></dd><dt>SG Revenue</dt><dd>{money(r.get("SG Gross Revenue"))}</dd><dt>SG Rank</dt><dd>#{bestrank(r.get("SG App Store Ranks")) if bestrank(r.get("SG App Store Ranks"))!=9999 else "NA"}</dd></dl></section><section class="drawer-section"><h4>Title & Language</h4><dl><dt>Display Title</dt><dd>{esc(display_name(r))}</dd><dt>Detected Language</dt><dd>{esc(r.get("Detected Language"))}</dd><dt>Machine English Title</dt><dd>{esc(r.get("Machine English Title")) or "None"}</dd><dt>Manual English Title</dt><dd>{esc(r.get("Manual English Title")) or "None"}</dd><dt>Translation Source</dt><dd>{esc(r.get("Translation Source"))}</dd><dt>Confidence</dt><dd>{esc(r.get("Translation Confidence"))}</dd><dt>Review Status</dt><dd>{esc(r.get("Translation Review Status"))}</dd></dl></section><section class="drawer-section"><h4>Evidence</h4><dl><dt>Exact app IDs</dt><dd>{esc(u)}</dd><dt>Release-date evidence</dt><dd>{esc(display_date(r.get("Release Date")) or "")}</dd><dt>Ranking evidence</dt><dd>{esc(r.get("SG App Store Ranks"))}</dd><dt>Top Markets</dt><dd>{esc(r.get("Top 3 Markets"))}</dd><dt>Unified warning</dt><dd>{"Check iOS / Android mapping if platform metadata conflicts." if " / " in r.get("Platform","") else "Single-platform record."}</dd></dl></section><section class="drawer-section"><h4>Notes</h4><p><b>Discussion:</b> {esc(r.get("Discussion Notes")) or "None"}</p><p><b>Approved Report Note:</b> {esc(r.get("Approved Report Note")) or "None"}</p>{act}</section><section class="drawer-section"><h4>History</h4><ul class="hist">{h}</ul></section></aside>'

def review(s,q):
    queues=[('needs','Needs Attention'),('title','Title Review Needed'),('emerging','Emerging'),('promoted','Manually Promoted'),('starred','Starred'),('excluded','Excluded'),('reported','Reported')]; active=q.get('queue',['needs'])[0]
    def qrows(k):
        rs=rows(True); o=ovr(); out=[]
        for r in rs:
            ok=(k=='needs' and r.get('Excluded')!='Yes' and has_attention(r)) or (k=='title' and 'Review' in title_status(r)) or (k=='emerging' and r.get('Excluded')!='Yes' and r.get('Signal Type')!='Strong Market Signal') or (k=='promoted' and o.get(r.get('_uid'),{}).get('override_signal_type')=='Strong Market Signal') or (k=='starred' and r.get('Starred')=='Yes') or (k=='excluded' and r.get('Excluded')=='Yes') or (k=='reported' and r.get('Review Status')=='Reported')
            if ok: out.append(r)
        return out
    rs=qrows(active); sel=q.get('selected',[rs[0].get('_uid') if rs else ''])[0]
    left=''.join(f'<a class="{"on" if active==k else ""}" href="/review?queue={k}"><span>{n}</span><b>{len(qrows(k))}</b></a>' for k,n in queues)
    mid=''.join(f'<a class="item" href="/review?queue={active}&selected={esc(r.get("_uid"))}"><b>{esc(display_name(r))}</b><span>{esc(r.get("Signal Display"))} · {money(r.get("SG Gross Revenue"))} · {esc(title_status(r))}</span></a>' for r in rs) or '<p class="empty">Queue empty.</p>'
    return f'<section class="head"><div><em>Review</em><h2>Analyst triage inbox</h2><p>Only true attention items enter Needs Attention. Emerging signals are not automatically treated as problems.</p></div><div><a class="btn" href="/export/review.csv">Internal review export</a><a class="btn" href="/export/admin.csv">Override history</a></div></section><section class="review"><aside>{left}</aside><div class="panel"><form method="post" action="/bulk-action">{bulk(s)}<div class="items">{mid}</div></form></div>{drawer(sel,s)}</section>'

def update(s,selected,action,note='',approved='',manual_title='',title_review='',title_note=''):
    if not selected: return 'No rows selected.'
    if action in ('strong','emerging') and not can(s,'classify'): return 'Role cannot classify.'
    if action in ('exclude','restore') and not can(s,'exclude'): return 'Role cannot exclude/restore.'
    o=ovr(); base={uid(r):r for r in rc(FINAL)}
    for u in selected:
        src=base.get(u,{}); r=o.get(u,{k:'' for k in OVR_FIELDS}); r['unified_app_id']=u; r['game_title']=src.get('Game Title',r.get('game_title',''))
        def setf(field,val,act=action):
            old=r.get(field,''); r[field]=val; log_change(s,act,u,r['game_title'],field,old,val,note or title_note)
        if action=='strong': setf('override_signal_type','Strong Market Signal')
        elif action=='emerging': setf('override_signal_type','Early Market Signal')
        elif action=='star': setf('starred','Yes')
        elif action=='unstar': setf('starred','No')
        elif action=='exclude': setf('deleted','Yes')
        elif action=='restore': setf('deleted','No')
        elif action=='reviewed': setf('review_status','Reviewed')
        elif action=='select_report': setf('selected_for_report','Yes')
        elif action=='hide_report': setf('selected_for_report','No')
        elif action=='reported': setf('review_status','Reported')
        if manual_title: setf('manual_english_title',manual_title,'manual_title')
        if title_review: setf('translation_review_status',title_review,'title_review')
        if title_note: setf('translation_note',title_note,'title_note')
        if note: r['notes']=(r.get('notes','')+'\n' if r.get('notes') else '')+f'[{s.get("current_user")}, {now()}] {note}'
        if approved: setf('approved_report_note',approved,'approved_note')
        r['updated_at']=now(); o[u]=r
    save_ovr(o); return f'Updated {len(selected)} row(s).'

def cal(s):
    p=period(s); prev=period(s,-1); nxt=period(s,1)
    steps=[('Previous Meeting',prev['meeting']),('Report Start',p['start']),('Report End',p['end']),('Current Meeting',p['meeting']),('Data as of',p['effective']),('Next Expected Meeting',nxt['meeting'])]
    timeline=''.join(f'<div class="time-step"><small>{esc(a)}</small><b>{nd(d)}</b></div>' for a,d in steps)
    tr=''.join(f'<tr><td>{"Current" if i==0 else i}</td><td>{nd(period(s,i)["start"])} to {nd(period(s,i)["end"])}</td><td>{nd(period(s,i)["meeting"])}</td><td>{nd(period(s,i)["effective"])}</td><td>{esc(s.get("report_status") if i==0 else "Planned")}</td></tr>' for i in range(-2,4))
    return f'<div class="timeline">{timeline}</div><p class="muted">The reporting period follows the meeting rhythm. If the meeting moves, the current report window stretches until the new meeting date and the report becomes stale until rerun.</p><div class="table"><table><thead><tr><th>Cycle</th><th>Report window</th><th>Meeting</th><th>Data effective</th><th>Status</th></tr></thead><tbody>{tr}</tbody></table></div>'

def compare(rs):
    leader=max(rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
    return f'<div class="coming"><h3>Compare is coming later</h3><p>This view will compare two finalised portal snapshots: signal counts, estimated SG revenue, top publishers, top genres, and highest-performing release. Current deterministic baseline: {counts(rs)["strong"]} strong signal(s), {counts(rs)["emerging"]} emerging signal(s), leader {esc(display_name(leader) or "No data")}.</p></div>'

def operations(s,q,msg=''):
    p=period(s); pv=q.get('preview_date',[''])[0]; preview=''
    ts=title_stats()
    if pv:
        m=pdate(pv); st=pdate(s['active_report_start_date'])
        if m and m>st:
            preview=f'<div class="confirm"><h3>Confirm reporting date change</h3><p><b>Current meeting date:</b> {nd(p["meeting"])}<br><b>New meeting date:</b> {nd(pv)}<br><b>Old report period:</b> {nd(p["start"])} to {nd(p["end"])}<br><b>New report period:</b> {nd(st)} to {nd(m-timedelta(days=1))}<br><b>Data-as-of date:</b> {nd(m-timedelta(days=2))}<br><b>Future cadence:</b> next cycles continue every 14 days from {nd(pv)}.<br><b>Warning:</b> existing report becomes stale until rerun.</p><form method="post" action="/confirm-date-change"><input type="hidden" name="meeting_date" value="{esc(pv)}"><a class="btn" href="/operations">Cancel</a><button>Save Date and Mark Report Stale</button></form></div>'
        else: preview='<p class="error">Invalid meeting date.</p>'
    if can(s,'run'):
        admin=f'<section class="panel ops-primary"><h3>Run Market Scan</h3><p><b>Selected period:</b> {nd(p["start"])} to {nd(p["end"])} · <b>Data effective:</b> {nd(p["effective"])}</p><div class="pipeline"><div>1. Retrieve SG ranking candidates</div><div>2. Resolve app identities</div><div>3. Fetch metadata</div><div>3.5 Normalise titles</div><div>4. Fetch SEA6 performance</div><div>5. Build report and review queue</div></div><form method="post" action="/run-scan"><button class="blue">Run Market Scan</button></form><details><summary>View Technical Details</summary><p>Calls scripts/current_report_watchlist_workflow.py. Title normalisation is handled by scripts/layer3_5_title_normalise.py. Token values are never displayed.</p></details></section><section class="panel"><h3>Reporting Schedule</h3>{cal(s)}<form class="filters" method="post" action="/preview-date-change"><label>Upcoming Meeting Date <input type="date" name="meeting_date" value="{esc(p["meeting"])}"></label><button>Preview change</button></form>{preview}</section><section class="panel"><h3>Finalisation</h3><p>Draft / Review Required / Ready / Finalised. Finalised reports are frozen local snapshots; corrections create revisions.</p><form method="post" action="/set-report-status"><button name="status" value="Ready">Mark Ready</button><button name="status" value="Finalised">Finalise Snapshot</button><button name="status" value="Draft">Reopen Draft</button></form></section>'
    else: admin='<section class="panel"><p class="empty">Operational controls are hidden for this role.</p></section>'
    diag=''
    if can(s,'diagnostics'):
        files=''.join(f'<tr><td>{esc(f.name)}</td><td>{"Present" if f.exists() else "Missing"}</td></tr>' for f in [FINAL,WATCH,OVR,HIST,DECISIONS,OUT/"layer3_5_title_normalised_metadata.csv"])
        cfg=''.join(f'<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>' for k,v in public_config().items())
        diag=f'<section class="panel"><details><summary><b>Diagnostics</b></summary><table>{files}</table><table>{cfg}</table></details></section>'
    rules=f'<section class="panel"><details><summary><b>Definitions and Rules</b></summary><div class="grid four">{card("Strong Market Signal","SG gross revenue exceeded ,000 during the release/report period.")}{card("Emerging Market Signal","New SG launch detected; relevance still developing.")}{card("Revenue","Gross dollars","Not store revenue cents.")}{card("Data lag",f"Report end -{LAG} day")}</div></details></section>' if can(s,'diagnostics') else ''
    title_panel=f'<section class="panel"><h3>Title Normalisation Status</h3><div class="grid six">{card("Total Titles",ts["total"])}{card("English",ts["english"])}{card("Canonicalized",ts["auto"])}{card("Manual Titles",ts["manual"])}{card("Needs Review",ts["needs"])}{card("Unresolved",ts["failed"])}</div><p class="muted">Normal operation uses the local title glossary and review queue. No online translation API is required.</p></section>'
    toast=f'<div class="toast">{esc(msg)}</div>' if msg else ''
    return f'<section class="head"><div><em>Operations</em><h2>Operations</h2><p>Operator controls are separated from admin definitions and diagnostics.</p></div></section>{toast}{admin}{title_panel}{rules}<section class="panel"><h3>Export centre</h3>{exports()}</section><section class="panel"><h3>Persistence boundary</h3><p>Current storage is local CSV/JSON. Migration boundary is local CSV → SQLite → shared PostgreSQL or equivalent database. CSV is not sufficient for real multi-user deployment.</p></section>{diag}'

def run_scan(s):
    if s.get('scan_running'): return 'A scan is already running.'
    s['scan_running']=True; s['report_status']='Scan Running'; save_state(s)
    try:
        res=subprocess.run(['py',str(ROOT/'scripts'/'current_report_watchlist_workflow.py')],cwd=str(ROOT),text=True,capture_output=True,timeout=180)
        if res.returncode:
            s['report_status']='Review Required'; raise RuntimeError(res.stderr.strip() or res.stdout.strip() or 'Workflow failed')
        s['last_scan_at']=now(); s['last_scan_period_key']=period(s)['key']; s['report_status']='Review Required' if counts(rows()).get('attention') else 'Draft'
        return 'Market scan build completed, including title normalisation. Review before exporting.'
    finally:
        s['scan_running']=False; save_state(s)

# --- Major UX restructure: reporting portal shell ---
def public_signal_summary(rs):
    c=counts(rs)
    total_rev=sum(sf(r.get('SG Gross Revenue')) for r in rs)
    return c,total_rev

def report_card(r,rank_no=None,kind='strong'):
    rank=bestrank(r.get('SG App Store Ranks'))
    rank_text=f'#{rank}' if rank!=9999 else 'NA'
    rev=money(r.get('SG Gross Revenue')) if r.get('SG Gross Revenue') not in ('','NA') else 'Not available'
    badge='Strong Market Signal' if kind=='strong' else 'Emerging Market Signal'
    return f'''<article class="brief-game {kind}">
      <div class="game-rank">{esc(rank_no if rank_no else '')}</div>
      <div class="game-main"><div class="game-title-row"><h3>{esc(display_name(r))}</h3><span class="sig {'strong' if kind=='strong' else 'em'}">{badge}</span></div>
      <p class="game-meta">{esc(r.get('Publisher'))} · {esc(r.get('Platform'))} · Released {esc(display_date(r.get('Release Date')) or '')}</p>
      <div class="game-fields"><span><b>Genre</b>{esc(r.get('Genre'))}</span><span><b>SG Gross Revenue</b>{rev}</span><span><b>SG Rank</b>{rank_text}</span></div>
      <p class="market-line">{esc(r.get('Top 3 Markets'))}</p><p class="rank-line">{esc(r.get('SG App Store Ranks'))}</p></div>
    </article>'''

def featured_leader(rs):
    leader=max([r for r in rs if r.get('Signal Type')=='Strong Market Signal'] or rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
    if not leader: return '<div class="feature-card empty">No featured title yet.</div>'
    rank=bestrank(leader.get('SG App Store Ranks'))
    return f'''<div class="feature-card"><div class="feature-kicker">Top Commercial Signal</div><h3>{esc(display_name(leader))}</h3><p>{esc(leader.get('Publisher'))}</p><div class="feature-money">{money(leader.get('SG Gross Revenue'))}</div><small>Estimated SG gross revenue</small><dl><dt>SG Rank</dt><dd>#{rank if rank!=9999 else 'NA'}</dd><dt>Top Markets</dt><dd>{esc(leader.get('Top 3 Markets'))}</dd></dl><span class="sig strong">Strong Market Signal</span></div>'''

def market(s,q,msg=''):
    rs=[r for r in rows() if r.get('Selected For Report')!='No']
    c,total_rev=public_signal_summary(rs)
    strong=sorted([r for r in rs if r.get('Signal Type')=='Strong Market Signal'],key=lambda r:-sf(r.get('SG Gross Revenue')))
    emerging=sorted([r for r in rs if r.get('Signal Type')!='Strong Market Signal'],key=lambda r:(-sf(r.get('SG Gross Revenue')),bestrank(r.get('SG App Store Ranks')),pdate(r.get('Release Date')) or date.min))
    summary=f"{c['total']} new mobile launches were detected this period. {c['strong']} show clear commercial traction, while {c['emerging']} are emerging launches to monitor."
    strong_html=''.join(report_card(r,i+1,'strong') for i,r in enumerate(strong)) or '<p class="empty">No strong market signals this period.</p>'
    emerging_html=''.join(report_card(r,i+1,'emerging') for i,r in enumerate(emerging)) or '<p class="empty">No emerging market signals this period.</p>'
    explore=explore_launches_section(s,q)
    p=period(s)
    return f'''<section class="portal-hero"><div class="portal-copy"><em>Market Brief</em><h2>Singapore Mobile Launch Brief</h2><p class="periodline">{nd(p['start'])} to {nd(p['end'])}</p><p class="summaryline">{esc(summary)}</p><div class="hero-actions"><a class="btn blue" href="/export/print.html">Print Report</a><a class="btn" href="/export/executive.csv">Export Executive CSV</a></div></div>{featured_leader(rs)}</section>
    <section class="signal-strip">{card('Detected Launches',c['total'],'Singapore mobile launches detected.')}{card('Strong Market Signals',c['strong'],'SG gross revenue exceeded ,000 during the release/report period.')}{card('Emerging Market Signals',c['emerging'],'New launches worth monitoring.')}{card('Estimated SG Gross Revenue',money(total_rev),'Gross revenue estimate across detected launches.')}</section>
    <section class="report-section strong-section"><div class="section-head"><h2>Strong Market Signals</h2><p>SG gross revenue exceeded ,000 during the release/report period.</p></div><div class="brief-list">{strong_html}</div></section>
    <section class="report-section emerging-section"><div class="section-head"><h2>Emerging Market Signals</h2><p>New SG launches detected this period; commercial relevance is still developing.</p></div><div class="brief-list">{emerging_html}</div></section>
    {explore}
    <details class="methodology"><summary>Methodology and data notes</summary><p>Source: Sensor Tower. Data as of {data_asof(rs,p)}. Launches use Singapore country release date where available. Strong Market Signal means commercial traction is visible through SG grossing/revenue evidence. Emerging Market Signal means a new SG launch was detected but commercial relevance is still developing. Revenue is shown as estimated gross dollars. This proof of concept covers Singapore mobile launch discovery only.</p></details>'''

def explore_launches_section(s,q):
    rs=filter_rows(rows(True),q)
    return f'''<details class="explore"><summary>Explore all detected launches</summary><section class="panel filter-panel">{filters(q)}<p class="muted">For full datasets and analyst exports, use Data Export.</p></section><section class="panel"><form method="post" action="/bulk-action">{table(rs,s,False)}</form></section></details>'''

def data_export(s,q,msg=''):
    rs=rows(); p=period(s); stamp=todaystamp()
    def ex(title,audience,count,fmt,url,desc=''):
        return f'<div class="export-card"><small>{esc(audience)} · {esc(fmt)}</small><h3>{esc(title)}</h3><p>{esc(desc)}</p><dl><dt>Period</dt><dd>{nd(p["start"])} to {nd(p["end"])}</dd><dt>Rows</dt><dd>{count}</dd><dt>Generated</dt><dd>{stamp}</dd></dl><a class="btn blue" href="{url}">Export</a></div>'
    report=ex('Executive CSV','Executive',len(rs),'CSV','/export/executive.csv','Clean report output using English Display Title.')+ex('Print-friendly HTML','Executive',len(rs),'HTML','/export/print.html','Presentation-ready report page.')+ex('Strong Market Signals CSV','Executive / Analyst',counts(rs)['strong'],'CSV','/export/strong.csv')+ex('Emerging Market Signals CSV','Executive / Analyst',counts(rs)['emerging'],'CSV','/export/emerging.csv')
    analysis=ex('Full launch dataset','Analyst',len(rows(True)),'CSV','/export/launches.csv','Includes analyst fields but avoids token/config data.')+ex('Filtered launch dataset','Analyst',len(filter_rows(rows(True),q)),'CSV','/export/launches.csv','Use filters in Market Brief exploration, then export.')+ex('Detailed evidence dataset','Analyst',len(rows(True)),'CSV','/export/evidence.csv','Includes app IDs and evidence fields.')+ex('SEA6 market metrics','Analyst','available','CSV','/export/sea6.csv','Local file path export source.')+ex('Title normalisation dataset','Analyst','available','CSV','/export/title-normalisation.csv','Language/title review dataset.')
    internal=''
    if can(s,'diagnostics'):
        internal=ex('Override history','Admin',len(rc(HIST) or rc(OVR)),'CSV','/export/admin.csv')+ex('Review queue','Admin',counts(rows(True))['attention'],'CSV','/export/review.csv')+ex('Raw workflow decisions','Admin','available','CSV','/export/workflow-decisions.csv')
    return f'<section class="head"><div><em>Data Export</em><h2>Download report and analysis datasets</h2><p>Exports are separated by audience so normal users do not see admin clutter.</p></div></section><section class="export-section"><h3>Report Exports</h3><div class="export-grid2">{report}</div></section><section class="export-section"><h3>Analysis Exports</h3><div class="export-grid2">{analysis}</div></section>{f"<section class=\"export-section admin-only\"><h3>Internal/Admin Exports</h3><div class=\"export-grid2\">{internal}</div></section>" if internal else ""}'

def calendar_page(s,q,msg=''):
    return f'<section class="head"><div><em>Calendar</em><h2>Reporting Calendar</h2><p>Understand the report window, meeting rhythm, and historical report snapshots.</p></div></section><section class="panel calendar-panel">{cal(s)}</section><section class="panel"><h3>Historical Reports</h3>{history(s)}</section>{calendar_admin_controls(s,q)}'

def calendar_admin_controls(s,q):
    if not can(s,'dates'): return ''
    p=period(s); pv=q.get('preview_date',[''])[0]; preview=''
    if pv:
        m=pdate(pv); st=pdate(s['active_report_start_date'])
        if m and m>st:
            preview=f'<div class="confirm"><h3>Preview date change</h3><p><b>Current meeting:</b> {nd(p["meeting"])}<br><b>New meeting:</b> {nd(pv)}<br><b>Old period:</b> {nd(p["start"])} to {nd(p["end"])}<br><b>New period:</b> {nd(st)} to {nd(m-timedelta(days=1))}<br><b>Data-as-of:</b> {nd(m-timedelta(days=2))}<br><b>Future cadence:</b> every 14 days from {nd(pv)}.</p><form method="post" action="/confirm-date-change"><input type="hidden" name="meeting_date" value="{esc(pv)}"><a class="btn" href="/calendar">Cancel</a><button>Save Date and Mark Report Stale</button></form></div>'
    return f'<section class="panel admin-only"><h3>Admin: Meeting Date Control</h3><form class="filters" method="post" action="/preview-date-change"><label>Upcoming Meeting Date <input type="date" name="meeting_date" value="{esc(p["meeting"])}"></label><button>Preview change</button></form>{preview}</section>'

def admin_page(s,q,msg=''):
    rs=rows(True); c=counts(rs); ts=title_stats(); p=period(s)
    msg_html=f'<div class="toast">{esc(msg)}</div>' if msg else ''
    admin_controls=''
    if can(s,'run'):
        admin_controls=f'<section class="panel ops-primary"><h3>Run Market Scan</h3><p><b>Selected period:</b> {nd(p["start"])} to {nd(p["end"])} · <b>Data as of:</b> {nd(p["effective"])}</p><div class="pipeline"><div>1. Retrieve SG ranking candidates</div><div>2. Resolve app identities</div><div>3. Fetch metadata</div><div>3.5 Normalise titles</div><div>4. Fetch SEA6 performance</div><div>5. Build brief and queues</div></div><form method="post" action="/run-scan"><button class="blue">Run Market Scan</button></form><details><summary>Technical details</summary><p>Uses local scripts and existing Sensor Tower outputs. Tokens are never displayed.</p></details></section>'
    controls=f'<section class="panel"><h3>Report Controls</h3><div class="grid four">{card("Report Status","Stale" if stale(s) else s.get("report_status"))}{card("Strong",c["strong"])}{card("Emerging",c["emerging"])}{card("Admin Checks",c["attention"])}</div><form method="post" action="/set-report-status"><button name="status" value="Ready">Mark Ready</button><button name="status" value="Finalised">Finalise Snapshot</button><button name="status" value="Draft">Reopen Draft</button></form></section>' if can(s,'finalise') else ''
    brief_controls=f'<section class="panel"><h3>Market Brief Controls</h3><p>Promote/demote signal, star, exclude/hide, edit approved note, and manage English display titles.</p><div class="admin-table">{table(rs,s,True)}</div></section>' if can(s,'classify') else ''
    title_panel=f'<section class="panel"><h3>Title Normalisation</h3><div class="grid six">{card("Total Titles",ts["total"])}{card("English",ts["english"])}{card("Canonicalized",ts["auto"])}{card("Manual Titles",ts["manual"])}{card("Needs Title Review",ts["needs"])}{card("Unresolved",ts["failed"])}</div><p class="muted">Title issues are internal and do not appear on Market Brief.</p></section>'
    rules=f'<section class="panel"><details><summary><b>Definitions and Rules</b></summary><div class="grid four">{card("Strong Market Signal","SG gross revenue exceeded ,000 during the release/report period.")}{card("Emerging Market Signal","New SG launch detected; relevance still developing.")}{card("Revenue","Gross dollars","Not store revenue cents.")}{card("Data lag",f"Report end -{LAG} day")}</div></details></section>' if can(s,'diagnostics') else ''
    diag=''
    if can(s,'diagnostics'):
        files=''.join(f'<tr><td>{esc(f.name)}</td><td>{"Present" if f.exists() else "Missing"}</td></tr>' for f in [FINAL,WATCH,OVR,HIST,DECISIONS,OUT/"layer3_5_title_normalised_metadata.csv"])
        diag=f'<section class="panel"><details><summary><b>Diagnostics</b></summary><table>{files}</table></details></section>'
    return f'<section class="head"><div><em>Admin</em><h2>Behind-the-scenes controls</h2><p>Workflow controls, quality checks, title normalisation, and Market Brief curation live here.</p></div></section>{msg_html}{admin_controls}{controls}{brief_controls}{title_panel}{rules}{diag}'

def featured_leader(rs):
    strong=[r for r in rs if r.get('Signal Type')=='Strong Market Signal']
    starred=[r for r in strong if r.get('Starred')=='Yes']
    pool=starred or strong or rs
    leader=max(pool,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
    if not leader: return '<div class="feature-card empty">No featured title yet.</div>'
    rank=bestrank(leader.get('SG App Store Ranks'))
    manual='<small class="manual-feature">Manually highlighted</small>' if leader.get('Starred')=='Yes' else ''
    return f'''<div class="feature-card"><div class="feature-kicker">Top Commercial Signal</div><h3>{esc(display_name(leader))}</h3>{manual}<p>{esc(leader.get('Publisher'))}</p><div class="feature-money">{money(leader.get('SG Gross Revenue'))}</div><small>Estimated SG gross revenue</small><dl><dt>SG Rank</dt><dd>#{rank if rank!=9999 else 'NA'}</dd><dt>Top Markets</dt><dd>{esc(leader.get('Top 3 Markets'))}</dd></dl><span class="sig strong">Strong Market Signal</span></div>'''

def admin_curation_table(rs,s):
    if not rs: return '<p class="empty">No launch rows available.</p>'
    body=''
    for r in rs:
        rank=bestrank(r.get('SG App Store Ranks'))
        body+=f'<tr><td><input type="checkbox" name="selected" value="{esc(r.get("_uid"))}"></td><td><a class="rowtitle" href="/admin?selected={esc(r.get("_uid"))}"><b>{esc(display_name(r))}</b><small>{esc(r.get("Original Title"))}</small></a></td><td><span class="sig {"strong" if r.get("Signal Type")=="Strong Market Signal" else "em"}">{esc(r.get("Signal Display"))}</span></td><td class="num">{money(r.get("SG Gross Revenue"))}</td><td class="num">{rank if rank!=9999 else "NA"}</td><td>{"★" if r.get("Starred")=="Yes" else "☆"}</td><td>{esc(title_status(r))}</td><td>{esc(r.get("Excluded"))}</td></tr>'
    return f'<form method="post" action="/bulk-action">{bulk(s)}<div class="table"><table><thead><tr><th><input type="checkbox" onclick="tog(this)"></th><th>Brief Title</th><th>Signal</th><th class="num">SG Revenue</th><th class="num">Best Rank</th><th>Highlight</th><th>Title Status</th><th>Hidden</th></tr></thead><tbody>{body}</tbody></table></div></form>'

def admin_page(s,q,msg=''):
    rs=rows(True); c=counts(rs); ts=title_stats(); p=period(s); sel=q.get('selected',[''])[0]
    msg_html=f'<div class="toast">{esc(msg)}</div>' if msg else ''
    admin_controls=''
    if can(s,'run'):
        admin_controls=f'<section class="panel ops-primary"><h3>Run Market Scan</h3><p><b>Selected period:</b> {nd(p["start"])} to {nd(p["end"])} · <b>Data as of:</b> {nd(p["effective"])}</p><div class="pipeline"><div>1. Retrieve SG ranking candidates</div><div>2. Resolve app identities</div><div>3. Fetch metadata</div><div>3.5 Normalise titles</div><div>4. Fetch SEA6 performance</div><div>5. Build brief and queues</div></div><form method="post" action="/run-scan"><button class="blue">Run Market Scan</button></form><details><summary>Technical details</summary><p>Uses local scripts and existing Sensor Tower outputs. Tokens are never displayed.</p></details></section>'
    controls=f'<section class="panel"><h3>Report Controls</h3><div class="grid four">{card("Report Status","Stale" if stale(s) else s.get("report_status"))}{card("Strong",c["strong"])}{card("Emerging",c["emerging"])}{card("Admin Checks",c["attention"])}</div><form method="post" action="/set-report-status"><button name="status" value="Ready">Mark Ready</button><button name="status" value="Finalised">Finalise Snapshot</button><button name="status" value="Draft">Reopen Draft</button></form></section>' if can(s,'finalise') else ''
    brief_controls=f'<section class="panel"><h3>Market Brief Controls</h3><p>Use Star to choose the featured commercial leader when manual override is needed. Use Exclude to hide irrelevant titles from the brief. Click a title for manual English title and approved note controls.</p>{admin_curation_table(rs,s)}</section>' if can(s,'classify') else ''
    selected_drawer=drawer(sel,s) if sel else ''
    title_panel=f'<section class="panel"><h3>Title Normalisation</h3><div class="grid six">{card("Total Titles",ts["total"])}{card("English",ts["english"])}{card("Canonicalized",ts["auto"])}{card("Manual Titles",ts["manual"])}{card("Needs Title Review",ts["needs"])}{card("Unresolved",ts["failed"])}</div><p class="muted">Title issues are internal and do not appear on Market Brief.</p><form method="post" action="/run-scan"><button>Rerun title normalisation with scan</button></form></section>'
    rules=f'<section class="panel"><details><summary><b>Definitions and Rules</b></summary><div class="grid four">{card("Strong Market Signal","SG gross revenue exceeded ,000 during the release/report period.")}{card("Emerging Market Signal","New SG launch detected; relevance still developing.")}{card("Revenue","Gross dollars","Not store revenue cents.")}{card("Data lag",f"Report end -{LAG} day")}</div></details></section>' if can(s,'diagnostics') else ''
    diag=''
    if can(s,'diagnostics'):
        files=''.join(f'<tr><td>{esc(f.name)}</td><td>{"Present" if f.exists() else "Missing"}</td></tr>' for f in [FINAL,WATCH,OVR,HIST,DECISIONS,OUT/"layer3_5_title_normalised_metadata.csv"])
        diag=f'<section class="panel"><details><summary><b>Diagnostics</b></summary><table>{files}</table></details></section>'
    return f'<section class="head"><div><em>Admin</em><h2>Behind-the-scenes controls</h2><p>Workflow controls, quality checks, title normalisation, and Market Brief curation live here.</p></div></section>{msg_html}{admin_controls}{controls}<div class="split"><div>{brief_controls}{title_panel}{rules}{diag}</div>{selected_drawer}</div>'

def public_explore_table(rs):
    if not rs: return '<p class="empty">No rows match.</p>'
    body=''
    for r in rs:
        rank=bestrank(r.get('SG App Store Ranks'))
        body+=f'<tr><td><b>{esc(display_name(r))}</b></td><td>{esc(r.get("Publisher"))}</td><td>{esc(r.get("Platform"))}</td><td><span class="sig {"strong" if r.get("Signal Type")=="Strong Market Signal" else "em"}">{esc(r.get("Signal Display"))}</span></td><td class="num">{money(r.get("SG Gross Revenue"))}</td><td class="num">{rank if rank!=9999 else "NA"}</td><td>{esc(topm(r.get("Top 3 Markets")))}</td></tr>'
    return f'<div class="table public-table"><table><thead><tr><th>Game Title</th><th>Publisher</th><th>Platform</th><th>Signal</th><th class="num">SG Revenue</th><th class="num">SG Rank</th><th>Top Market</th></tr></thead><tbody>{body}</tbody></table></div>'

def explore_launches_section(s,q):
    rec=selected_brief(q,s) if 'selected_brief' in globals() else brief_record_current(s)
    base=raw_rows_for_brief(rec) if 'raw_rows_for_brief' in globals() else rows()
    rs=filter_rows(base,q)
    return f'''<details class="explore"><summary>Explore all detected launches</summary><section class="panel filter-panel">{filters(q)}<p class="muted">This table follows the selected Market Brief. For downloadable datasets, use Data Export.</p></section><section class="panel">{public_explore_table(rs)}</section></details>'''

# --- Market Signal Cards + curation refinement ---
def brief_included(r):
    if r.get('Excluded')=='Yes': return False
    if r.get('admin_hide_from_brief')=='true': return False
    if r.get('include_in_market_brief')=='false': return False
    if r.get('Selected For Report')=='No': return False
    return True

def rows(include_deleted=False):
    o=ovr(); out=[]
    for r in rc(FINAL):
        x=dict(r); u=uid(x); y=o.get(u,{})
        if y.get('deleted')=='Yes' and not include_deleted: continue
        if y.get('override_signal_type'): x['Signal Type']=DISP_BACK.get(y['override_signal_type'],y['override_signal_type'])
        if y.get('manual_english_title'):
            x['Manual English Title']=y.get('manual_english_title'); x['English Display Title']=y.get('manual_english_title'); x['Game Title']=y.get('manual_english_title')
        if y.get('translation_review_status'): x['Translation Review Status']=y.get('translation_review_status')
        if y.get('translation_note'): x['Translation Note']=y.get('translation_note')
        for f in ['include_in_market_brief','pinned_position','featured_slot','market_brief_card_size','market_brief_order','admin_hide_from_brief','curation_updated_at','curation_updated_by']:
            x[f]=y.get(f,'')
        x['_uid']=u; x['Signal Display']=SIGDIS.get(x.get('Signal Type'),x.get('Signal Type','Emerging Market Signal'))
        x['Signal Definition']=SIGDEF.get(x.get('Signal Type'),x.get('Signal Definition',''))
        x['Starred']=y.get('starred','No') or 'No'; x['Excluded']=y.get('deleted','No') or 'No'; x['Discussion Notes']=y.get('notes',''); x['Approved Report Note']=y.get('approved_report_note','')
        x['Review Status']=y.get('review_status','Review Needed' if has_attention(x) else 'Unreviewed') or 'Unreviewed'; x['Selected For Report']=y.get('selected_for_report','Yes') or 'Yes'; x['Title Status']=title_status(x)
        out.append(x)
    return sorted(out,key=lambda r:({'Strong Market Signal':0,'Early Market Signal':1}.get(r.get('Signal Type'),9),curation_sort(r),-sf(r.get('SG Gross Revenue')),display_name(r)))

def curation_sort(r):
    pp=r.get('pinned_position','')
    if pp=='top': return -10
    if pp.startswith('top_'):
        try: return int(pp.split('_')[1])-20
        except Exception: return -9
    try: return int(r.get('market_brief_order') or 999)
    except Exception: return 999

def parse_market_entries(text):
    body=(text or '').replace('Top Mkts:','').strip().rstrip('.')
    out=[]
    for part in [p.strip() for p in body.split('||') if p.strip()]:
        m=re.search(r'([A-Z]{2}) \(\$([0-9,]+) / ([0-9,]+) DL\)',part)
        if m:
            out.append({'country':m.group(1),'revenue':int(m.group(2).replace(',','')),'downloads':int(m.group(3).replace(',',''))})
    total=sum(x['revenue'] for x in out) or 1
    for i,x in enumerate(out,1): x['rank']=i; x['share']=x['revenue']/total
    return out

def market_chips(r,full=False):
    entries=parse_market_entries(r.get('Top 3 Markets'))
    if not entries: return '<div class="market-chips empty-chip">No SEA6 market data</div>'
    chips=''
    for x in entries:
        sg=' sg' if x['country']=='SG' else ''
        chips+=f'<div class="market-chip{sg}"><small>#{x["rank"]} {x["country"]}</small><b>{money(x["revenue"])}</b><span>{x["downloads"]:,} DL</span></div>'
    return f'<div class="market-chips">{chips}</div>'

def sea6_table(r):
    entries=parse_market_entries(r.get('Top 3 Markets'))
    if not entries: return '<p class="empty">No SEA6 performance data available.</p>'
    trs=''.join(f'<tr class="{"sgrow" if x["country"]=="SG" else ""}"><td>#{x["rank"]}</td><td>{x["country"]}</td><td class="num">{money(x["revenue"])}</td><td class="num">{x["downloads"]:,}</td><td class="num">{x["share"]:.0%}</td></tr>' for x in entries)
    return f'<div class="table sea6"><table><thead><tr><th>Rank</th><th>Country</th><th class="num">Estimated Gross Revenue</th><th class="num">Downloads</th><th class="num">Share</th></tr></thead><tbody>{trs}</tbody></table></div>'

def sg_downloads_value(r): return downloads(r.get('Top 3 Markets'))
def sg_rank_value(r):
    rank=bestrank(r.get('SG App Store Ranks')); return f'#{rank}' if rank!=9999 else 'NA'

def market_signal_card(r,i,kind='strong',featured=False):
    accent='strong' if kind=='strong' else 'emerging'
    subtitle='SG revenue threshold met' if kind=='strong' else 'New launch to monitor'
    size=' featured-card' if featured or r.get('market_brief_card_size')=='featured' else ''
    pin='<span class="pin">Pinned</span>' if r.get('pinned_position') else ''
    return f'''<a class="signal-card {accent}{size}" href="/market-brief?selected={esc(r.get('_uid'))}&view=cards">
      <div class="card-top"><span class="sig {'strong' if kind=='strong' else 'em'}">{esc(r.get('Signal Display'))}</span>{pin}</div>
      <h3>{esc(display_name(r))}</h3><p class="publisher">{esc(r.get('Publisher'))}</p>
      <div class="revenue-metric"><b>{money(r.get('SG Gross Revenue'))}</b><span>Estimated SG gross revenue</span></div>
      <div class="support-metrics"><span><b>{sg_downloads_value(r):,}</b>SG Downloads</span><span><b>{sg_rank_value(r)}</b>Best SG Rank</span></div>
      {market_chips(r)}
      <div class="card-footer"><span>{subtitle}</span><strong>View Details →</strong></div>
    </a>'''

def compact_public_table(rs):
    if not rs: return '<p class="empty">No rows match.</p>'
    brief_id=globals().get('CURRENT_BRIEF_ID','current')
    body=''
    for r in rs:
        body+=f'<tr><td><a class="rowtitle" href="/market-brief?brief={esc(brief_id)}&selected={esc(r.get("_uid"))}&view=table"><b>{esc(display_name(r))}</b></a></td><td>{esc(r.get("Publisher"))}</td><td><span class="sig {"strong" if r.get("Signal Type")=="Strong Market Signal" else "em"}">{esc(r.get("Signal Display"))}</span></td><td class="num">{money(r.get("SG Gross Revenue"))}</td><td class="num">{sg_downloads_value(r):,}</td><td class="num">{sg_rank_value(r)}</td><td>{esc(topm(r.get("Top 3 Markets")))}</td></tr>'
    return f'<div class="table public-table"><table><thead><tr><th>Game</th><th>Publisher</th><th>Signal</th><th class="num">SG Revenue</th><th class="num">SG Downloads</th><th class="num">SG Rank</th><th>Top Market</th></tr></thead><tbody>{body}</tbody></table></div>'

def market_detail_drawer(uid_value,s):
    if not uid_value: return ''
    r=next((x for x in rows(True) if x.get('_uid')==uid_value),None)
    if not r: return ''
    admin=can(s,'diagnostics') or can(s,'classify')
    admin_evidence=f'<dt>App-ID evidence</dt><dd>{esc(uid_value)}</dd><dt>Original Title</dt><dd>{esc(r.get("Original Title"))}</dd><dt>Translation Source</dt><dd>{esc(r.get("Translation Source"))}</dd><dt>Translation Status</dt><dd>{esc(r.get("Translation Review Status"))}</dd>' if admin else ''
    note=f'<section class="drawer-section"><h4>Notes</h4><p>{esc(r.get("Approved Report Note"))}</p></section>' if r.get('Approved Report Note') else ''
    return f'''<aside class="public-detail"><a class="close" href="/market-brief">Close</a><h2>{esc(display_name(r))}</h2><section class="drawer-section"><h4>Overview</h4><dl><dt>Publisher</dt><dd>{esc(r.get('Publisher'))}</dd><dt>Signal</dt><dd>{esc(r.get('Signal Display'))}</dd><dt>Platform</dt><dd>{esc(r.get('Platform'))}</dd><dt>SG Release Date</dt><dd>{esc(display_date(r.get('Release Date')) or '')}</dd><dt>Genre</dt><dd>{esc(r.get('Genre'))}</dd><dt>SG Gross Revenue</dt><dd>{money(r.get('SG Gross Revenue'))}</dd><dt>SG Downloads</dt><dd>{sg_downloads_value(r):,}</dd><dt>SG App Store Ranks</dt><dd>{esc(r.get('SG App Store Ranks'))}</dd></dl></section><section class="drawer-section"><h4>SEA6 Performance</h4>{sea6_table(r)}</section><section class="drawer-section"><h4>Evidence</h4><dl><dt>Ranking Evidence</dt><dd>{esc(r.get('SG App Store Ranks'))}</dd><dt>Release-date Evidence</dt><dd>{esc(display_date(r.get('Release Date')) or '')}</dd>{admin_evidence}</dl></section>{note}</aside>'''

def market(s,q,msg=''):
    view=q.get('view',['cards'])[0]; selected=q.get('selected',[''])[0]
    rs=[r for r in rows() if brief_included(r)]
    c,total_rev=public_signal_summary(rs)
    strong=sorted([r for r in rs if r.get('Signal Type')=='Strong Market Signal'],key=lambda r:(curation_sort(r),-sf(r.get('SG Gross Revenue'))))
    emerging=sorted([r for r in rs if r.get('Signal Type')!='Strong Market Signal'],key=lambda r:(curation_sort(r),-sf(r.get('SG Gross Revenue')),bestrank(r.get('SG App Store Ranks')),pdate(r.get('Release Date')) or date.min))
    summary=f"{c['total']} new mobile launches were detected this period. {c['strong']} show clear commercial traction, while {c['emerging']} are emerging launches to monitor."
    cards_strong=''.join(market_signal_card(r,i+1,'strong',i==0) for i,r in enumerate(strong)) or '<p class="empty">No strong market signals this period.</p>'
    cards_em=''.join(market_signal_card(r,i+1,'emerging') for i,r in enumerate(emerging)) or '<p class="empty">No emerging market signals this period.</p>'
    strong_body=compact_public_table(strong) if view=='table' else f'<div class="signal-card-grid strong-grid">{cards_strong}</div>'
    emerging_body=compact_public_table(emerging) if view=='table' else f'<div class="signal-card-grid emerging-grid">{cards_em}</div>'
    p=period(s); toggle=f'<div class="view-toggle"><a class="{"on" if view=="cards" else ""}" href="/market-brief?view=cards">Cards</a><a class="{"on" if view=="table" else ""}" href="/market-brief?view=table">Compact Table</a></div>'
    detail=market_detail_drawer(selected,s)
    return f'''<section class="portal-hero"><div class="portal-copy"><em>Market Brief</em><h2>Singapore Mobile Launch Brief</h2><p class="periodline">{nd(p['start'])} to {nd(p['end'])}</p><p class="summaryline">{esc(summary)}</p><div class="hero-actions"><a class="btn blue" href="/export/print.html">Print Report</a><a class="btn" href="/export/executive.csv">Export Executive CSV</a></div></div>{featured_leader(rs)}</section><section class="signal-strip">{card('Detected Launches',c['total'],'Singapore mobile launches detected.')}{card('Strong Market Signals',c['strong'],'SG gross revenue exceeded ,000 during the release/report period.')}{card('Emerging Market Signals',c['emerging'],'New launches worth monitoring.')}{card('Estimated SG Gross Revenue',money(total_rev),'Gross revenue estimate across detected launches.')}</section>{toggle}<section class="report-section strong-section"><div class="section-head"><h2>Strong Market Signals</h2><p>SG gross revenue exceeded ,000 during the release/report period.</p></div>{strong_body}</section><section class="report-section emerging-section"><div class="section-head"><h2>Emerging Market Signals</h2><p>New SG launches detected this period; commercial relevance is still developing.</p></div>{emerging_body}</section>{explore_launches_section(s,q)}<details class="methodology"><summary>Methodology and data notes</summary><p>Source: Sensor Tower. Data as of {data_asof(rs,p)}. Launches use Singapore country release date where available. Strong Market Signal means commercial traction is visible through SG grossing/revenue evidence. Emerging Market Signal means a new SG launch was detected but commercial relevance is still developing. Revenue is shown as estimated gross dollars. This proof of concept covers Singapore mobile launch discovery only.</p></details>{detail}'''

# --- Monthly meeting calendar refinement ---
def month_bounds(ym):
    if ym:
        y,m=[int(x) for x in ym.split('-')]
        first=date(y,m,1)
    else:
        first=date.today().replace(day=1)
    nxt=(first.replace(day=28)+timedelta(days=4)).replace(day=1)
    prev=(first-timedelta(days=1)).replace(day=1)
    return first,prev,nxt

def meeting_period_for_date(s,meeting):
    cur=period(s,0); cur_meet=pdate(cur['meeting']); start=pdate(s['active_report_start_date'])
    if meeting==cur_meet:
        st=start
    else:
        delta=(meeting-cur_meet).days//14
        st=cur_meet+timedelta(days=14*(delta-1)) if delta>0 else start+timedelta(days=14*delta)
    end=meeting-timedelta(days=1); eff=end-timedelta(days=LAG); nxt=meeting+timedelta(days=14); prev=st
    return {'start':st,'end':end,'meeting':meeting,'effective':eff,'next':nxt,'previous':prev,'key':f'{st}_{end}'}

def meetings_around(s,months=4):
    cur=pdate(period(s,0)['meeting']); out=[]
    for i in range(-6,10): out.append(cur+timedelta(days=14*i))
    return out

def monthly_calendar_grid(s,q):
    ym=q.get('month',[''])[0]; first,prev_month,next_month=month_bounds(ym)
    selected=pdate(q.get('selected_meeting',[''])[0]) or pdate(period(s,0)['meeting'])
    meetings=meetings_around(s); today=date.today(); start=first-timedelta(days=first.weekday()); cells=[]
    for i in range(42):
        d=start+timedelta(days=i); inmonth=d.month==first.month; cls='muted' if not inmonth else ''
        label=''; badge=''
        if d in meetings:
            if d < pdate(period(s,0)['meeting']): badge='Previous Meeting'; cls+=' meeting previous'
            elif d == pdate(period(s,0)['meeting']): badge='Current Meeting'; cls+=' meeting current'
            else: badge='Future Meeting'; cls+=' meeting future'
            label=f'<a href="/calendar?month={first.strftime("%Y-%m")}&selected_meeting={d.isoformat()}">{badge}</a>'
        if d==selected: cls+=' selected'
        if d==today: cls+=' today'
        cells.append(f'<div class="cal-cell {cls}"><b>{d.day}</b>{label}</div>')
    heads=''.join(f'<div class="cal-head">{x}</div>' for x in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'])
    nav=f'<div class="month-nav"><a class="btn" href="/calendar?month={prev_month.strftime("%Y-%m")}">Previous Month</a><a class="btn" href="/calendar">Current Month</a><a class="btn" href="/calendar?month={pdate(period(s,0)["meeting"]).strftime("%Y-%m")}">Next Meeting Month</a><a class="btn" href="/calendar?month={next_month.strftime("%Y-%m")}">Next Month</a></div>'
    return nav+f'<div class="month-title"><h3>{first.strftime("%B %Y")}</h3><div class="legend"><span class="prevdot">Previous</span><span class="curdot">Upcoming / Current</span><span class="futdot">Future</span></div></div><div class="month-grid">{heads}{"".join(cells)}</div>', selected

def selected_meeting_panel(s,meeting):
    mp=meeting_period_for_date(s,meeting); exists=bool(list(SNAP.glob(f"*{mp['start']}_to_{mp['end']}*.csv")))
    status='Portal Report' if exists else 'No report snapshot exists for this meeting yet.'
    steps=[('Previous Meeting',mp['previous'],'meeting'),('Report Start',mp['start'],'window'),('Report End',mp['end'],'window'),('Meeting Date',mp['meeting'],'meeting current'),('Data As Of',mp['effective'],'data'),('Next Expected Meeting',mp['next'],'meeting')]
    timeline=''.join(f'<div class="time-step {cls}"><small>{esc(label)}</small><b>{nd(d)}</b></div>' for label,d,cls in steps)
    return f'<aside class="meeting-panel"><h3>Selected Meeting</h3><div class="selected-date">{nd(meeting)}</div><dl><dt>Report Window</dt><dd>{nd(mp["start"])} to {nd(mp["end"])}</dd><dt>Data As Of</dt><dd>{nd(mp["effective"])}</dd><dt>Status</dt><dd>{esc(status)}</dd></dl><div class="timeline refined">{timeline}</div></aside>'

def calendar_page(s,q,msg=''):
    grid,selected=monthly_calendar_grid(s,q)
    admin=calendar_admin_controls(s,q)
    return f'<section class="head"><div><em>Calendar</em><h2>Meeting Calendar</h2><p>Meeting dates are shown on the monthly calendar. Report windows are explained separately so the two concepts do not blur together.</p></div></section><section class="calendar-layout"><div class="panel calendar-grid-panel">{grid}</div>{selected_meeting_panel(s,selected)}</section>{admin}<section class="panel"><h3>Historical Reports</h3>{history(s)}</section>'

# --- Focused visual cleanup and organisation pass ---
def clean_role_form(s):
    role=''.join(f'<option {"selected" if s.get("current_role")==r else ""}>{r}</option>' for r in ['Viewer','Contributor','Admin'])
    user=''.join(f'<option {"selected" if s.get("current_user")==u else ""}>{u}</option>' for u in ['Shauna','Daryl','Contributor','Viewer'])
    return f'<form class="role-compact" method="post" action="/set-role"><span>POC role</span><select name="user">{user}</select><select name="role">{role}</select><button>Apply</button></form>'

def layout(path,s,content):
    rs=rows(); p=period(s); status='Stale' if stale(s) else s.get('report_status','Draft')
    if path=='/market-brief' and 'CURRENT_BRIEF_CONTEXT' in globals():
        br=globals().get('CURRENT_BRIEF_CONTEXT') or {}
        p={'start':br.get('start') or p.get('start'), 'end':br.get('end') or p.get('end'), 'meeting':br.get('meeting') or ''}
        status=br.get('status') or status
        data_as_of=nd((pdate(p.get('end'))-timedelta(days=LAG)).isoformat()) if pdate(p.get('end')) else 'Unavailable'
    else:
        data_as_of=data_asof(rs,p)
    meeting_label=nd(p['meeting']) if p.get('meeting') else 'Unavailable'
    nav_items=[('/market-brief','Market Brief'),('/data-export','Data Export'),('/calendar','Calendar')]
    if s.get('current_role')=='Admin': nav_items.append(('/admin','Admin'))
    else: nav_items.append(('/admin','Admin'))
    nav=''.join(f'<a class="{"on" if path==u else ""}" href="{u}">{label}</a>' for u,label in nav_items)
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IBD Market Intelligence</title><style>{CSS}</style><script>{JS}</script></head><body><div class="shell clean-shell"><aside><div class="brandmark">IBD Market Intelligence</div><h1>Singapore · Mobile Launch Discovery</h1><span>Proof of Concept</span><nav>{nav}</nav><p class="future">Mobile launch discovery module. Future intelligence modules remain out of scope for this POC.</p></aside><div class="page-frame"><header class="context clean-context"><div><small>Reporting period</small><b>{nd(p['start'])} – {nd(p['end'])}</b></div><div><small>Meeting</small><b>{meeting_label}</b></div><div><small>Data as of</small><b>{data_as_of}</b></div><div><small>Status</small><b class="pill">{esc(status)}</b></div></header><main class="content-wrap">{content}</main></div></div></body></html>'''

def safe_metric(value, money_value=False):
    if value in (None,'','NA'): return '—'
    return money(value) if money_value else esc(value)

def market_chips(r,full=False):
    entries=parse_market_entries(r.get('Top 3 Markets'))
    if not entries: return '<div class="market-chips"><div class="market-chip empty-chip"><small>SEA6</small><b>—</b><span>Not available</span></div></div>'
    chips=''
    for x in entries[:4]:
        sg=' sg' if x['country']=='SG' else ''
        chips+=f'<div class="market-chip{sg}"><small>#{x["rank"]} {x["country"]}</small><b>{money(x["revenue"])}</b><span>{x["downloads"]:,} DL</span></div>'
    return f'<div class="market-chips">{chips}</div>'

def market_signal_card(r,i,kind='strong',featured=False):
    accent='strong' if kind=='strong' else 'emerging'
    subtitle='SG revenue threshold met' if kind=='strong' else 'New launch to monitor'
    size=' featured-card' if featured or r.get('market_brief_card_size')=='featured' else ''
    pin='<span class="pin">Featured</span>' if featured or r.get('pinned_position') else ''
    genre_bits=' · '.join([x for x in [r.get('Platform'),r.get('Genre'),('Released '+r.get('Release Date')) if r.get('Release Date') else ''] if x])
    return f'''<a class="signal-card {accent}{size}" href="/market-brief?selected={esc(r.get('_uid'))}&view=cards">
      <div class="card-top"><span class="sig {'strong' if kind=='strong' else 'em'}">{esc(r.get('Signal Display'))}</span>{pin}</div>
      <div class="card-title-block"><h3>{esc(display_name(r))}</h3><p class="publisher">{esc(r.get('Publisher'))}</p><p class="game-meta2">{esc(genre_bits)}</p></div>
      <div class="revenue-metric"><b>{money(r.get('SG Gross Revenue'))}</b><span>Estimated SG gross revenue</span></div>
      <div class="support-metrics"><span><b>{sg_downloads_value(r):,}</b>SG Downloads</span><span><b>{sg_rank_value(r)}</b>Best SG Rank</span></div>
      <div class="markets-label">Top SEA6 Markets</div>{market_chips(r)}
      <div class="card-footer"><span>{subtitle}</span><strong>View Details</strong></div>
    </a>'''

def public_explore_table(rs):
    if not rs: return '<p class="empty polished-empty">No launches match the current view.</p>'
    body=''
    for r in rs:
        body+=f'<tr onclick="location.href=\'/market-brief?selected={esc(r.get("_uid"))}\'"><td><b>{esc(display_name(r))}</b></td><td>{esc(r.get("Publisher"))}</td><td>{esc(r.get("Platform"))}</td><td><span class="sig {"strong" if r.get("Signal Type")=="Strong Market Signal" else "em"}">{esc(r.get("Signal Display"))}</span></td><td class="num">{money(r.get("SG Gross Revenue"))}</td><td class="num">{sg_downloads_value(r):,}</td><td class="num">{sg_rank_value(r)}</td><td>{esc(topm(r.get("Top 3 Markets")))}</td></tr>'
    return f'<div class="table public-table clean-table"><table><thead><tr><th>Game</th><th>Publisher</th><th>Platform</th><th>Signal</th><th class="num">SG Revenue</th><th class="num">Downloads</th><th class="num">SG Rank</th><th>Top Market</th></tr></thead><tbody>{body}</tbody></table></div>'

def export_card(title,audience,count,fmt,url,desc,period_label):
    return f'<div class="export-card clean-export"><div><small>{esc(audience)} · {esc(fmt)}</small><h3>{esc(title)}</h3><p>{esc(desc)}</p></div><dl><dt>Period</dt><dd>{esc(period_label)}</dd><dt>Rows</dt><dd>{esc(count)}</dd><dt>Format</dt><dd>{esc(fmt)}</dd></dl><a class="btn blue" href="{url}">Export</a></div>'

def data_export(s,q,msg=''):
    rs=rows(); p=period(s); per=f'{nd(p["start"])} to {nd(p["end"])}'
    report=''.join([
        export_card('Print-friendly report','Executive',len(rs),'HTML','/export/print.html','Presentation-ready Market Brief export.',per),
        export_card('Executive CSV','Executive',len(rs),'CSV','/export/executive.csv','Clean output using English Display Title.',per),
        export_card('Strong Market Signals CSV','Executive / Analyst',counts(rs)['strong'],'CSV','/export/strong.csv','Commercial traction section only.',per),
        export_card('Emerging Market Signals CSV','Executive / Analyst',counts(rs)['emerging'],'CSV','/export/emerging.csv','Emerging launch section only.',per)])
    analysis=''.join([
        export_card('Full launch dataset','Analyst',len(rows(True)),'CSV','/export/launches.csv','All launch records with analyst-facing fields.',per),
        export_card('Filtered launch dataset','Analyst',len(filter_rows(rows(True),q)),'CSV','/export/launches.csv','Filtered data access for analysis.',per),
        export_card('Detailed evidence dataset','Analyst',len(rows(True)),'CSV','/export/evidence.csv','Includes app IDs and supporting evidence.',per),
        export_card('SEA6 market metrics','Analyst','available','CSV','/export/sea6.csv','Country-level SEA6 market metrics.',per),
        export_card('Title normalisation dataset','Analyst','available','CSV','/export/title-normalisation.csv','Title-language and display-title fields.',per)])
    internal=''
    if can(s,'diagnostics'):
        internal=''.join([export_card('Override history','Admin',len(rc(HIST) or rc(OVR)),'CSV','/export/admin.csv','Manual curation and override audit.',per),export_card('Review queue','Admin',counts(rows(True))['attention'],'CSV','/export/review.csv','Internal quality-check records.',per),export_card('Raw workflow decisions','Admin','available','CSV','/export/workflow-decisions.csv','Workflow decision audit trail.',per)])
    return f'<section class="page-title"><em>Data Export</em><h2>Download report and analysis datasets</h2><p>Exports are grouped by audience so report readers do not need to touch admin files.</p></section><section class="export-section"><h3>Report Exports</h3><div class="export-grid2 clean-export-grid">{report}</div></section><section class="export-section"><h3>Analysis Exports</h3><div class="export-grid2 clean-export-grid">{analysis}</div></section>{f"<section class=\"export-section admin-only\"><h3>Admin/Internal Exports</h3><div class=\"export-grid2 clean-export-grid\">{internal}</div></section>" if internal else ""}'

def factual_meetings(s):
    p=period(s,0); previous=pdate(s.get('active_report_start_date')); current=pdate(p['meeting'])
    meetings=[]
    if previous: meetings.append({'date':previous,'kind':'previous','label':'Previous Meeting','projected':False})
    if current: meetings.append({'date':current,'kind':'current','label':'Current Meeting','projected':False})
    if current:
        for i in (1,2): meetings.append({'date':current+timedelta(days=14*i),'kind':'future','label':'Planned Meeting','projected':True})
    return meetings

def selected_meeting_info(s,selected):
    p=period(s,0); current=pdate(p['meeting']); previous=pdate(s.get('active_report_start_date'))
    if selected==current:
        return {'meeting':current,'start':pdate(p['start']),'end':pdate(p['end']),'effective':pdate(p['effective']),'previous':previous,'next':current+timedelta(days=14),'status':('Stale' if stale(s) else s.get('report_status','Draft')),'report_label':'Current Portal Report'}
    if selected==previous:
        return {'meeting':previous,'start':None,'end':None,'effective':None,'previous':None,'next':current,'status':'Historical date','report_label':'Meeting date known; report window unavailable in current local state.'}
    if current and selected and selected>current:
        start=selected-timedelta(days=14); end=selected-timedelta(days=1); return {'meeting':selected,'start':start,'end':end,'effective':end-timedelta(days=LAG),'previous':start,'next':selected+timedelta(days=14),'status':'Planned','report_label':'Projected future meeting; no report snapshot exists yet.'}
    return {'meeting':selected,'start':None,'end':None,'effective':None,'previous':None,'next':None,'status':'Unavailable','report_label':'No report snapshot exists for this meeting yet.'}

def monthly_calendar_grid(s,q):
    selected=pdate(q.get('selected_meeting',[''])[0]) or pdate(period(s,0)['meeting'])
    ym=q.get('month',[''])[0] or (selected.strftime('%Y-%m') if selected else date.today().strftime('%Y-%m'))
    first,prev_month,next_month=month_bounds(ym); meetings=factual_meetings(s); bydate={m['date']:m for m in meetings}; today=date.today(); start=first-timedelta(days=first.weekday()); cells=[]
    for i in range(42):
        d=start+timedelta(days=i); m=bydate.get(d); cls='muted' if d.month!=first.month else ''
        label=''
        if m:
            cls+=f' meeting {m["kind"]}'; proj=' projected' if m.get('projected') else ''; label=f'<a class="{proj}" href="/calendar?month={first.strftime("%Y-%m")}&selected_meeting={d.isoformat()}">{esc(m["label"])}</a>'
        if d==selected: cls+=' selected'
        if d==today: cls+=' today'
        cells.append(f'<div class="cal-cell {cls}"><b>{d.day}</b>{label}</div>')
    heads=''.join(f'<div class="cal-head">{x}</div>' for x in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'])
    nav=f'<div class="month-nav"><a class="btn" href="/calendar?month={prev_month.strftime("%Y-%m")}">Previous Month</a><a class="btn" href="/calendar">Current Reporting Month</a><a class="btn" href="/calendar?month={next_month.strftime("%Y-%m")}">Next Month</a></div>'
    return nav+f'<div class="month-title"><h3>{first.strftime("%B %Y")}</h3><div class="legend"><span class="prevdot">Previous</span><span class="curdot">Current</span><span class="futdot">Projected</span></div></div><div class="month-grid clean-month-grid">{heads}{"".join(cells)}</div>', selected

def selected_meeting_panel(s,meeting):
    info=selected_meeting_info(s,meeting)
    def d(x): return nd(x) if x else 'Unavailable'
    steps=[('Previous Meeting',info.get('previous'),'meeting'),('Report Start',info.get('start'),'window'),('Report End',info.get('end'),'window'),('Meeting Date',info.get('meeting'),'meeting current'),('Data As Of',info.get('effective'),'data'),('Next Expected Meeting',info.get('next'),'meeting')]
    timeline=''.join(f'<div class="time-step {cls}"><small>{esc(label)}</small><b>{d(val)}</b></div>' for label,val,cls in steps)
    return f'<aside class="meeting-panel clean-meeting-panel"><h3>Selected Meeting</h3><div class="selected-date">{d(info.get("meeting"))}</div><dl><dt>Report Window</dt><dd>{d(info.get("start"))} to {d(info.get("end"))}</dd><dt>Data As Of</dt><dd>{d(info.get("effective"))}</dd><dt>Status</dt><dd>{esc(info.get("status"))}</dd><dt>Report</dt><dd>{esc(info.get("report_label"))}</dd></dl><div class="timeline refined">{timeline}</div></aside>'

def calendar_page(s,q,msg=''):
    grid,selected=monthly_calendar_grid(s,q); admin=calendar_admin_controls(s,q)
    return f'<section class="page-title"><em>Calendar</em><h2>Meeting Calendar</h2><p>The calendar shows known meeting dates from the local project state. Future dates are shown only as projected/planned meetings.</p></section><section class="calendar-layout"><div class="panel calendar-grid-panel">{grid}</div>{selected_meeting_panel(s,selected)}</section>{admin}<section class="panel history-panel"><h3>Historical Reports</h3>{history(s)}</section>'

def admin_page(s,q,msg=''):
    if s.get('current_role')!='Admin':
        return '<section class="page-title"><em>Admin</em><h2>Admin access</h2><p>This area contains workflow controls, diagnostics, review queues, and curation settings. Switch to an Admin role to view local proof-of-concept controls.</p></section>'
    rs=rows(True); c=counts(rs); ts=title_stats(); p=period(s); sel=q.get('selected',[''])[0]
    msg_html=f'<div class="toast">{esc(msg)}</div>' if msg else ''
    run=f'<details class="admin-group" open><summary>Run Market Scan</summary><div class="pipeline"><div>1. Retrieve SG ranking candidates</div><div>2. Resolve identities</div><div>3. Fetch metadata</div><div>3.5 Normalise titles</div><div>4. Fetch SEA6</div><div>5. Build brief</div></div><p><b>Selected period:</b> {nd(p["start"])} to {nd(p["end"])} · <b>Data as of:</b> {nd(p["effective"])}</p><form method="post" action="/run-scan"><button class="blue">Run Market Scan</button></form></details>'
    controls=f'<details class="admin-group" open><summary>Report Controls</summary><div class="grid four">{card("Report Status","Stale" if stale(s) else s.get("report_status"))}{card("Strong",c["strong"])}{card("Emerging",c["emerging"])}{card("Internal Checks",c["attention"])}</div><form method="post" action="/set-report-status"><button name="status" value="Ready">Mark Ready</button><button name="status" value="Finalised">Finalise Snapshot</button><button name="status" value="Draft">Reopen Draft</button></form></details>'
    curation=f'<details class="admin-group" open><summary>Market Brief Curation</summary><p>Control inclusion, signal group, highlighting, notes, and display titles for the official brief.</p>{admin_curation_table(rs,s)}</details>'
    title=f'<details class="admin-group" open><summary>Title Normalisation</summary><div class="grid six">{card("Total",ts["total"])}{card("English",ts["english"])}{card("Canonicalized",ts["auto"])}{card("Manual",ts["manual"])}{card("Needs Review",ts["needs"])}{card("Unresolved",ts["failed"])}</div></details>'
    rules=f'<details class="admin-group"><summary>Definitions and Rules</summary><div class="grid four">{card("Strong Market Signal","SG gross revenue exceeded ,000 during the release/report period.")}{card("Emerging Market Signal","New SG launch detected; relevance still developing.")}{card("Revenue","Gross dollars")}{card("Data lag",f"Report end -{LAG} day")}</div></details>'
    files=''.join(f'<tr><td>{esc(f.name)}</td><td>{"Present" if f.exists() else "Missing"}</td></tr>' for f in [FINAL,WATCH,OVR,HIST,DECISIONS,OUT/"layer3_5_title_normalised_metadata.csv"])
    diag=f'<details class="admin-group"><summary>Diagnostics</summary><table>{files}</table></details><details class="admin-group"><summary>Override History</summary><p><a class="btn" href="/export/admin.csv">Export override history</a></p></details>'
    return f'<section class="page-title"><em>Admin</em><h2>Admin Workbench</h2><p>Internal workflow controls and quality checks are organised here, away from the reader-facing Market Brief.</p></section>{msg_html}<div class="admin-layout"><div>{run}{controls}{curation}{title}{rules}{diag}</div>{drawer(sel,s) if sel else ""}</div>'

# --- Market Brief archive and selected-brief reader ---
def row_period_key(row):
    start=row.get('report_start_date') or row.get('Report Start') or row.get('report_start') or ''
    end=row.get('report_end_date') or row.get('Report End') or row.get('report_end') or ''
    return start,end

def brief_record_current(s):
    p=period(s,0); rs=rows()
    return {'id':'current','type':'Portal Brief','status':('Stale' if stale(s) else s.get('report_status','Draft')),'meeting':p.get('meeting'),'start':p.get('start'),'end':p.get('end'),'path':str(FINAL),'rows':len(rs),'source':'current'}

def brief_records():
    s=state(); recs=[brief_record_current(s)]
    for f in sorted(SNAP.glob('*.csv'), reverse=True):
        m=re.search(r'(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})', f.name)
        start,end=(m.group(1),m.group(2)) if m else ('','')
        recs.append({'id':'snapshot:'+urllib.parse.quote(str(f.relative_to(ROOT))),'type':'Portal Brief','status':'Finalised Snapshot','meeting':'','start':start,'end':end,'path':str(f),'rows':len(rc(f)),'source':'snapshot'})
    legacy_roots=[ROOT/'archive'/'cleanup_20260714'/'data'/'backtest_jan_to_jun_2026_discover_later_assign_back',ROOT/'archive'/'cleanup_20260714'/'data'/'backtest_jan_to_jun_2026_sg_rankings_release_date',ROOT/'archive'/'cleanup_20260714'/'data'/'backtest_3_months_sg_rankings_release_date']
    seen=set()
    for root in legacy_roots:
        if not root.exists(): continue
        for f in sorted(root.glob('*_to_*/final_sg_market_scan*.csv')):
            rel=str(f.relative_to(ROOT))
            if rel in seen: continue
            seen.add(rel)
            m=re.search(r'(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})', rel)
            if not m: continue
            data=rc(f); recs.append({'id':'legacy:'+urllib.parse.quote(rel),'type':'Legacy Brief','status':'Legacy Report','meeting':'','start':m.group(1),'end':m.group(2),'path':str(f),'rows':len(data),'source':'legacy'})
    def sort_key(r):
        return pdate(r.get('meeting')) or (pdate(r.get('end')) or date.min)
    return sorted([r for r in recs if r.get('rows',0)>0], key=sort_key, reverse=True)

def selected_brief(q,s):
    bid=q.get('brief',['current'])[0]
    for r in brief_records():
        if r['id']==bid or urllib.parse.unquote(r['id'])==bid:
            return r
    return brief_record_current(s)

def raw_rows_for_brief(rec):
    if rec.get('source')=='current': return rows()
    data=rc(Path(rec['path']))
    out=[]
    for r in data:
        x=dict(r)
        x.setdefault('_uid',x.get('unified_app_id') or x.get('Game Title',''))
        x.setdefault('English Display Title',x.get('Game Title',''))
        x.setdefault('Original Title',x.get('Game Title',''))
        x.setdefault('Signal Type',x.get('Signal Type') or ('Strong Market Signal' if sf(x.get('SG Gross Revenue'))>0 else 'Early Market Signal'))
        x['Signal Display']=SIGDIS.get(x.get('Signal Type'),x.get('Signal Type'))
        x.setdefault('Selected For Report','Yes'); x.setdefault('Excluded','No'); x.setdefault('Starred','No')
        out.append(x)
    return sorted(out,key=lambda r:({'Strong Market Signal':0,'Early Market Signal':1}.get(r.get('Signal Type'),9),-sf(r.get('SG Gross Revenue')),display_name(r)))

def brief_title(rec):
    start=nd(rec.get('start')) if rec.get('start') else 'Period unavailable'
    end=nd(rec.get('end')) if rec.get('end') else ''
    meeting=nd(rec.get('meeting')) if rec.get('meeting') else 'Meeting unavailable'
    period_label=f'{start}–{end}' if end else start
    return f'{period_label} · {meeting} · {rec.get("type")}'

def brief_selector(q,s,rec,rs):
    search=q.get('brief_search',[''])[0].strip().lower()
    allrecs=brief_records()
    if search:
        filtered=[]
        for br in allrecs:
            hay=' '.join([br.get('start',''),br.get('end',''),br.get('meeting',''),br.get('type',''),br.get('status','')]).lower()
            sample=' '.join((r.get('Game Title','')+' '+r.get('Publisher','')+' '+r.get('Signal Display','')) for r in raw_rows_for_brief(br)[:200]).lower()
            if search in hay or search in sample: filtered.append(br)
    else: filtered=allrecs
    recent=''.join(brief_option_card(br,rec) for br in allrecs[:5])
    grouped={}
    for br in filtered:
        d=pdate(br.get('meeting')) or pdate(br.get('end'))
        key=d.strftime('%b %Y') if d else 'Date unavailable'
        grouped.setdefault(key,[]).append(br)
    archive=''.join(f'<div class="brief-month"><h4>{esc(k)}</h4>{"".join(brief_option_card(x,rec,compact=True) for x in v)}</div>' for k,v in grouped.items()) or '<p class="empty">No briefs match the search.</p>'
    legacy_note='<div class="legacy-note">Viewing legacy brief. This report was created before the portal format, so some structured fields may be unavailable.</div>' if rec.get('type')=='Legacy Brief' else ''
    return f'''<section class="brief-selector"><details><summary><span>Viewing</span><b>{esc(brief_title(rec))}</b></summary><div class="brief-popover"><div class="brief-search"><h3>Select Market Brief</h3><form><input type="hidden" name="brief" value="{esc(rec['id'])}"><input name="brief_search" value="{esc(search)}" placeholder="Search by game, publisher, period, meeting date, signal"><button>Search</button><a class="btn" href="/market-brief">Reset</a></form></div><div class="brief-columns"><section><h4>Recent</h4>{recent}</section><section><h4>All Briefs</h4>{archive}</section></div></div></details><p class="selected-line">Viewing: {esc(brief_title(rec))}</p>{legacy_note}</section>'''

def brief_option_card(br,current,compact=False):
    active=' active' if br['id']==current['id'] else ''
    meeting=nd(br.get('meeting')) if br.get('meeting') else 'Meeting unavailable'
    period_label=(nd(br.get('start'))+' to '+nd(br.get('end'))) if br.get('start') and br.get('end') else 'Period unavailable'
    return f'<a class="brief-option{active}" href="/market-brief?brief={esc(br["id"])}"><b>{esc(period_label)}</b><span>{esc(meeting)} · {esc(br.get("type"))} · {esc(br.get("status"))}</span><small>{br.get("rows",0)} rows</small></a>'

def market(s,q,msg=''):
    rec=selected_brief(q,s); all_rows=raw_rows_for_brief(rec); view=q.get('view',['cards'])[0]; selected=q.get('selected',[''])[0]
    rs=[r for r in all_rows if brief_included(r)]
    c,total_rev=public_signal_summary(rs)
    strong=sorted([r for r in rs if r.get('Signal Type')=='Strong Market Signal'],key=lambda r:(curation_sort(r),-sf(r.get('SG Gross Revenue'))))
    emerging=sorted([r for r in rs if r.get('Signal Type')!='Strong Market Signal'],key=lambda r:(curation_sort(r),-sf(r.get('SG Gross Revenue')),bestrank(r.get('SG App Store Ranks')),pdate(r.get('Release Date')) or date.min))
    summary=f"{c['total']} mobile launches are available in this brief. {c['strong']} show clear commercial traction, while {c['emerging']} are emerging launches to monitor."
    cards_strong=''.join(market_signal_card(r,i+1,'strong',i==0) for i,r in enumerate(strong)) or '<p class="empty">No strong market signals in this brief.</p>'
    cards_em=''.join(market_signal_card(r,i+1,'emerging') for i,r in enumerate(emerging)) or '<p class="empty">No emerging market signals in this brief.</p>'
    strong_body=compact_public_table(strong) if view=='table' else f'<div class="signal-card-grid strong-grid">{cards_strong}</div>'
    emerging_body=compact_public_table(emerging) if view=='table' else f'<div class="signal-card-grid emerging-grid">{cards_em}</div>'
    toggle=f'<div class="view-toggle"><a class="{"on" if view=="cards" else ""}" href="/market-brief?brief={esc(rec["id"])}&view=cards">Cards</a><a class="{"on" if view=="table" else ""}" href="/market-brief?brief={esc(rec["id"])}&view=table">Compact Table</a></div>'
    detail=market_detail_drawer(selected,s) if rec.get('source')=='current' else ''
    return f'''{brief_selector(q,s,rec,rs)}<section class="portal-hero"><div class="portal-copy"><em>Market Brief</em><h2>Singapore Mobile Launch Brief</h2><p class="periodline">{esc(brief_title(rec))}</p><p class="summaryline">{esc(summary)}</p><div class="hero-actions"><a class="btn blue" href="/export/print.html?brief={esc(rec['id'])}">Print Report</a><a class="btn" href="/export/executive.csv?brief={esc(rec['id'])}">Export Executive CSV</a></div></div>{featured_leader(rs)}</section><section class="signal-strip">{card('Detected Launches',c['total'],'Singapore mobile launches detected.')}{card('Strong Market Signals',c['strong'],'SG gross revenue exceeded ,000 during the release/report period.')}{card('Emerging Market Signals',c['emerging'],'New launches worth monitoring.')}{card('Estimated SG Gross Revenue',money(total_rev),'Gross revenue estimate across detected launches.')}</section>{toggle}<section class="report-section strong-section"><div class="section-head"><h2>Strong Market Signals</h2><p>SG gross revenue exceeded ,000 during the release/report period.</p></div>{strong_body}</section><section class="report-section emerging-section"><div class="section-head"><h2>Emerging Market Signals</h2><p>New SG launches detected; commercial relevance is still developing.</p></div>{emerging_body}</section>{explore_launches_section(s,q)}<details class="methodology"><summary>Methodology and data notes</summary><p>Source: Sensor Tower. Brief type: {esc(rec.get('type'))}. Legacy briefs may have fewer structured fields. This proof of concept covers Singapore mobile launch discovery only.</p></details>{detail}'''

# --- Selected brief export/detail support ---
def market_signal_card(r,i,kind='strong',featured=False):
    accent='strong' if kind=='strong' else 'emerging'
    subtitle='SG revenue threshold met' if kind=='strong' else 'New launch to monitor'
    size=' featured-card' if featured or r.get('market_brief_card_size')=='featured' else ''
    pin='<span class="pin">Featured</span>' if featured or r.get('pinned_position') else ''
    genre_bits=' · '.join([x for x in [r.get('Platform'),r.get('Genre'),('Released '+r.get('Release Date')) if r.get('Release Date') else ''] if x])
    brief_id=globals().get('CURRENT_BRIEF_ID','current')
    return f'''<a class="signal-card {accent}{size}" href="/market-brief?brief={esc(brief_id)}&selected={esc(r.get('_uid'))}&view=cards">
      <div class="card-top"><span class="sig {'strong' if kind=='strong' else 'em'}">{esc(r.get('Signal Display'))}</span>{pin}</div>
      <div class="card-title-block"><h3>{esc(display_name(r))}</h3><p class="publisher">{esc(r.get('Publisher'))}</p><p class="game-meta2">{esc(genre_bits)}</p></div>
      <div class="revenue-metric"><b>{money(r.get('SG Gross Revenue'))}</b><span>Estimated SG gross revenue</span></div>
      <div class="support-metrics"><span><b>{sg_downloads_value(r):,}</b>SG Downloads</span><span><b>{sg_rank_value(r)}</b>Best SG Rank</span></div>
      <div class="markets-label">Top SEA6 Markets</div>{market_chips(r)}
      <div class="card-footer"><span>{subtitle}</span><strong>View Details</strong></div>
    </a>'''

def market_detail_from_rows(uid_value,s,source_rows,rec):
    if not uid_value: return ''
    r=next((x for x in source_rows if x.get('_uid')==uid_value),None)
    if not r: return ''
    admin=can(s,'diagnostics') or can(s,'classify')
    admin_evidence=f'<dt>App-ID evidence</dt><dd>{esc(uid_value)}</dd><dt>Original Title</dt><dd>{esc(r.get("Original Title"))}</dd><dt>Translation Source</dt><dd>{esc(r.get("Translation Source"))}</dd><dt>Translation Status</dt><dd>{esc(r.get("Translation Review Status"))}</dd>' if admin else ''
    note=f'<section class="drawer-section"><h4>Notes</h4><p>{esc(r.get("Approved Report Note"))}</p></section>' if r.get('Approved Report Note') else ''
    return f'''<aside class="public-detail"><a class="close" href="/market-brief?brief={esc(rec['id'])}">Close</a><h2>{esc(display_name(r))}</h2><section class="drawer-section"><h4>Overview</h4><dl><dt>Publisher</dt><dd>{esc(r.get('Publisher'))}</dd><dt>Signal</dt><dd>{esc(r.get('Signal Display'))}</dd><dt>Platform</dt><dd>{esc(r.get('Platform'))}</dd><dt>SG Release Date</dt><dd>{esc(display_date(r.get('Release Date')) or '')}</dd><dt>Genre</dt><dd>{esc(r.get('Genre'))}</dd><dt>SG Gross Revenue</dt><dd>{money(r.get('SG Gross Revenue'))}</dd><dt>SG Downloads</dt><dd>{sg_downloads_value(r):,}</dd><dt>SG App Store Ranks</dt><dd>{esc(r.get('SG App Store Ranks'))}</dd></dl></section><section class="drawer-section"><h4>SEA6 Performance</h4>{sea6_table(r)}</section><section class="drawer-section"><h4>Evidence</h4><dl><dt>Ranking Evidence</dt><dd>{esc(r.get('SG App Store Ranks'))}</dd><dt>Release-date Evidence</dt><dd>{esc(display_date(r.get('Release Date')) or '')}</dd><dt>Brief Type</dt><dd>{esc(rec.get('type'))}</dd>{admin_evidence}</dl></section>{note}</aside>'''

def market(s,q,msg=''):
    rec=selected_brief(q,s); globals()['CURRENT_BRIEF_ID']=rec['id']; globals()['CURRENT_BRIEF_CONTEXT']=rec; all_rows=raw_rows_for_brief(rec); view=q.get('view',['cards'])[0]; selected=q.get('selected',[''])[0]
    rs=[r for r in all_rows if brief_included(r)]
    c,total_rev=public_signal_summary(rs)
    strong=sorted([r for r in rs if r.get('Signal Type')=='Strong Market Signal'],key=lambda r:(curation_sort(r),-sf(r.get('SG Gross Revenue'))))
    emerging=sorted([r for r in rs if r.get('Signal Type')!='Strong Market Signal'],key=lambda r:(curation_sort(r),-sf(r.get('SG Gross Revenue')),bestrank(r.get('SG App Store Ranks')),pdate(r.get('Release Date')) or date.min))
    summary=f"{c['total']} mobile launches are available in this brief. {c['strong']} show clear commercial traction, while {c['emerging']} are emerging launches to monitor."
    cards_strong=''.join(market_signal_card(r,i+1,'strong',i==0) for i,r in enumerate(strong)) or '<p class="empty">No strong market signals in this brief.</p>'
    cards_em=''.join(market_signal_card(r,i+1,'emerging') for i,r in enumerate(emerging)) or '<p class="empty">No emerging market signals in this brief.</p>'
    strong_body=compact_public_table(strong) if view=='table' else f'<div class="signal-card-grid strong-grid">{cards_strong}</div>'
    emerging_body=compact_public_table(emerging) if view=='table' else f'<div class="signal-card-grid emerging-grid">{cards_em}</div>'
    toggle=f'<div class="view-toggle"><a class="{"on" if view=="cards" else ""}" href="/market-brief?brief={esc(rec["id"])}&view=cards">Cards</a><a class="{"on" if view=="table" else ""}" href="/market-brief?brief={esc(rec["id"])}&view=table">Compact Table</a></div>'
    detail=market_detail_from_rows(selected,s,all_rows,rec)
    return f'''{brief_selector(q,s,rec,rs)}<section class="portal-hero"><div class="portal-copy"><em>Market Brief</em><h2>Singapore Mobile Launch Brief</h2><p class="periodline">{esc(brief_title(rec))}</p><p class="summaryline">{esc(summary)}</p><div class="hero-actions"><a class="btn blue" href="/export/print.html?brief={esc(rec['id'])}">Print Report</a><a class="btn" href="/export/executive.csv?brief={esc(rec['id'])}">Export Executive CSV</a></div></div>{featured_leader(rs)}</section><section class="signal-strip">{card('Detected Launches',c['total'],'Singapore mobile launches detected.')}{card('Strong Market Signals',c['strong'],'SG gross revenue exceeded ,000 during the release/report period.')}{card('Emerging Market Signals',c['emerging'],'New launches worth monitoring.')}{card('Estimated SG Gross Revenue',money(total_rev),'Gross revenue estimate across detected launches.')}</section>{toggle}<section class="report-section strong-section"><div class="section-head"><h2>Strong Market Signals</h2><p>SG gross revenue exceeded ,000 during the release/report period.</p></div>{strong_body}</section><section class="report-section emerging-section"><div class="section-head"><h2>Emerging Market Signals</h2><p>New SG launches detected; commercial relevance is still developing.</p></div>{emerging_body}</section>{explore_launches_section(s,q)}<details class="methodology"><summary>Methodology and data notes</summary><p>Source: Sensor Tower. Brief type: {esc(rec.get('type'))}. Legacy briefs may have fewer structured fields. This proof of concept covers Singapore mobile launch discovery only.</p></details>{detail}'''

def rows_for_export_kind(kind,q,s):
    rec=selected_brief(q,s) if q.get('brief') else brief_record_current(s)
    base=raw_rows_for_brief(rec)
    if kind=='strong': base=[r for r in base if r.get('Signal Type')=='Strong Market Signal']
    elif kind in ('emerging','early'): base=[r for r in base if r.get('Signal Type')!='Strong Market Signal']
    elif kind=='launches': base=filter_rows(base,q)
    return base

def print_html_for_brief(s,q):
    rec=selected_brief(q,s) if q.get('brief') else brief_record_current(s); rs=raw_rows_for_brief(rec)
    strong=''.join(report_card(r,i+1,'strong') for i,r in enumerate([x for x in rs if x.get('Signal Type')=='Strong Market Signal']))
    emerging=''.join(report_card(r,i+1,'emerging') for i,r in enumerate([x for x in rs if x.get('Signal Type')!='Strong Market Signal']))
    return f"<html><head><meta charset='utf-8'><style>{PRINT}</style></head><body><h1>Singapore Mobile Launch Brief</h1><p>{esc(brief_title(rec))} · Generated {todaystamp()}</p><h2>Strong Market Signals</h2>{strong}<h2>Emerging Market Signals</h2>{emerging}</body></html>".encode()

# --- Calendar meeting summary with Open Market Brief only when content exists ---
def brief_for_meeting_date(s,meeting):
    for br in brief_records():
        if br.get('meeting') and pdate(br.get('meeting'))==meeting:
            return br
    return None

def selected_meeting_panel(s,meeting):
    info=selected_meeting_info(s,meeting); br=brief_for_meeting_date(s,meeting)
    if br:
        br_rows=raw_rows_for_brief(br); c=counts(br_rows)
        strong_names=', '.join(display_name(r) for r in br_rows if r.get('Signal Type')=='Strong Market Signal') or 'None'
        emerging_names=', '.join(display_name(r) for r in br_rows if r.get('Signal Type')!='Strong Market Signal') or 'None'
        summary=f'<div class="meeting-summary"><h4>Brief Preview</h4><p><b>{c["total"]}</b> detected launches · <b>{c["strong"]}</b> strong · <b>{c["emerging"]}</b> emerging</p><p><b>Strong:</b> {esc(strong_names)}</p><p><b>Emerging:</b> {esc(emerging_names)}</p><a class="btn blue" href="/market-brief?brief={esc(br["id"])}">Open Market Brief</a></div>'
        report_label=f'{br.get("type")} · {br.get("status")}'
    else:
        summary='<div class="meeting-summary empty">No market brief has been generated yet.</div>' if info.get('status')=='Planned' else '<div class="meeting-summary empty">No report snapshot exists for this meeting yet.</div>'
        report_label=info.get('report_label')
    def d(x): return nd(x) if x else 'Unavailable'
    steps=[('Previous Meeting',info.get('previous'),'meeting'),('Report Start',info.get('start'),'window'),('Report End',info.get('end'),'window'),('Meeting Date',info.get('meeting'),'meeting current'),('Data As Of',info.get('effective'),'data'),('Next Expected Meeting',info.get('next'),'meeting')]
    timeline=''.join(f'<div class="time-step {cls}"><small>{esc(label)}</small><b>{d(val)}</b></div>' for label,val,cls in steps)
    return f'<aside class="meeting-panel clean-meeting-panel"><h3>Selected Meeting</h3><div class="selected-date">{d(info.get("meeting"))}</div><dl><dt>Report Window</dt><dd>{d(info.get("start"))} to {d(info.get("end"))}</dd><dt>Data As Of</dt><dd>{d(info.get("effective"))}</dd><dt>Status</dt><dd>{esc(info.get("status"))}</dd><dt>Brief</dt><dd>{esc(report_label)}</dd></dl>{summary}<div class="timeline refined">{timeline}</div></aside>'

def public_explore_table(rs):
    if not rs: return '<p class="empty polished-empty">No launches match the current view.</p>'
    brief_id=globals().get('CURRENT_BRIEF_ID','current')
    body=''
    for r in rs:
        body+=f'<tr onclick="location.href=\'/market-brief?brief={esc(brief_id)}&selected={esc(r.get("_uid"))}\'"><td><b>{esc(display_name(r))}</b></td><td>{esc(r.get("Publisher"))}</td><td>{esc(r.get("Platform"))}</td><td><span class="sig {"strong" if r.get("Signal Type")=="Strong Market Signal" else "em"}">{esc(r.get("Signal Display"))}</span></td><td class="num">{money(r.get("SG Gross Revenue"))}</td><td class="num">{sg_downloads_value(r):,}</td><td class="num">{sg_rank_value(r)}</td><td>{esc(topm(r.get("Top 3 Markets")))}</td></tr>'
    return f'<div class="table public-table clean-table"><table><thead><tr><th>Game</th><th>Publisher</th><th>Platform</th><th>Signal</th><th class="num">SG Revenue</th><th class="num">Downloads</th><th class="num">SG Rank</th><th>Top Market</th></tr></thead><tbody>{body}</tbody></table></div>'

# --- Reader-facing shell and navigation finetune ---
def clean_role_form(s):
    # Keep role simulation out of the reader-facing UI. Real auth can replace this later.
    user=s.get('current_user','Shauna')
    role='Admin' if user in ('Shauna','Daryl') or s.get('current_role')=='Admin' else 'Viewer'
    return f'<div class="mode-pill" title="Local proof-of-concept access is controlled by local state, not by a public role switcher.">{esc(role)} view</div>'

def current_access_role(s):
    return 'Admin' if s.get('current_user') in ('Shauna','Daryl') or s.get('current_role')=='Admin' else s.get('current_role','Viewer')

def layout(path,s,content):
    rs=rows(); p=period(s); brief_label='Current Portal Brief'; data_as_of=data_asof(rs,p)
    if path=='/market-brief' and 'CURRENT_BRIEF_CONTEXT' in globals():
        br=globals().get('CURRENT_BRIEF_CONTEXT') or {}
        p={'start':br.get('start') or p.get('start'), 'end':br.get('end') or p.get('end'), 'meeting':br.get('meeting') or ''}
        brief_label=br.get('type') or brief_label
        data_as_of=nd((pdate(p.get('end'))-timedelta(days=LAG)).isoformat()) if pdate(p.get('end')) else 'Unavailable'
    meeting_label=nd(p['meeting']) if p.get('meeting') else 'Unavailable'
    nav_desc={
        '/market-brief':'Read current and archived Singapore launch briefs.',
        '/data-export':'Download the main report or analyst datasets.',
        '/calendar':'View meeting months and reporting windows.',
        '/admin':'Internal controls for scans, curation, and diagnostics.'
    }
    nav_items=[('/market-brief','Market Brief'),('/data-export','Data Export'),('/calendar','Calendar')]
    if current_access_role(s)=='Admin': nav_items.append(('/admin','Admin'))
    nav=''.join(f'<a class="{"on" if path==u else ""}" href="{u}" title="{esc(nav_desc[u])}"><span>{label}</span><small>{esc(nav_desc[u])}</small></a>' for u,label in nav_items)
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IBD Market Intelligence</title><style>{CSS}</style><script>{JS}</script></head><body><div class="shell clean-shell"><aside><div class="brandmark">IBD Market Intelligence</div><h1>Singapore · Mobile Launch Discovery</h1><span>Proof of Concept</span><nav>{nav}</nav><p class="future">Mobile launch discovery module. Future PC, console, announcement, and news modules are not part of this proof of concept.</p></aside><div class="page-frame"><header class="context clean-context"><div><small>Report period</small><b>{nd(p['start'])} – {nd(p['end'])}</b></div><div><small>Meeting date</small><b>{meeting_label}</b></div><div><small>Data as of</small><b>{data_as_of}</b></div><div><small>Brief type</small><b class="pill neutral">{esc(brief_label)}</b></div></header><main class="content-wrap">{content}</main></div></div></body></html>'''

def export_card(title,audience,count,fmt,url,desc,period_label,primary=False):
    klass='export-card clean-export primary-export' if primary else 'export-card clean-export'
    return f'<div class="{klass}"><div><small>{esc(audience)} · {esc(fmt)}</small><h3>{esc(title)}</h3><p>{esc(desc)}</p></div><dl><dt>Period</dt><dd>{esc(period_label)}</dd><dt>Rows</dt><dd>{esc(count)}</dd></dl><a class="btn blue" href="{url}">Export</a></div>'

def data_export(s,q,msg=''):
    rs=rows(); p=period(s); per=f'{nd(p["start"])} to {nd(p["end"])}'
    primary=''.join([
        export_card('Print-ready Market Brief','Readers / meeting use',len(rs),'HTML','/export/print.html','Use this when someone wants to read or present the brief outside the app.',per,True),
        export_card('Executive CSV','Leadership / report paste',len(rs),'CSV','/export/executive.csv','Clean report data only: display title, publisher, signal, market metrics, and ranks.',per,True)])
    advanced_report=''.join([
        export_card('Strong signals only','Analyst',counts(rs)['strong'],'CSV','/export/strong.csv','Only launches with visible commercial traction.',per),
        export_card('Emerging signals only','Analyst',counts(rs)['emerging'],'CSV','/export/emerging.csv','Only launches still being monitored.',per)])
    analysis=''.join([
        export_card('Full launch dataset','Analyst',len(rows(True)),'CSV','/export/launches.csv','All current launch rows for deeper checking.',per),
        export_card('Detailed evidence dataset','Analyst',len(rows(True)),'CSV','/export/evidence.csv','Includes app IDs and supporting evidence fields.',per),
        export_card('SEA6 market metrics','Analyst','available','CSV','/export/sea6.csv','Country-level revenue and download metrics.',per),
        export_card('Title normalisation dataset','Analyst','available','CSV','/export/title-normalisation.csv','Original titles, English display titles, and translation status.',per)])
    internal=''
    if current_access_role(s)=='Admin' and can(s,'diagnostics'):
        internal=''.join([export_card('Override history','Admin',len(rc(HIST) or rc(OVR)),'CSV','/export/admin.csv','Manual curation and override audit.',per),export_card('Review queue','Admin',counts(rows(True))['attention'],'CSV','/export/review.csv','Internal quality-check records.',per),export_card('Raw workflow decisions','Admin','available','CSV','/export/workflow-decisions.csv','Workflow decision audit trail.',per)])
    return f'''<section class="page-title"><em>Data Export</em><h2>Download the brief</h2><p>Most users only need the two main exports below. Analyst and admin files are tucked away so the page does not feel like a spreadsheet warehouse.</p></section><section class="export-section primary-export-section"><h3>Main exports</h3><div class="export-grid2 clean-export-grid primary-only">{primary}</div></section><details class="export-section export-details"><summary>More analyst exports</summary><p class="muted">Use these only when you need to check a signal group, evidence, SEA6 metrics, or title-normalisation data.</p><h4>Report slices</h4><div class="export-grid2 clean-export-grid">{advanced_report}</div><h4>Analysis datasets</h4><div class="export-grid2 clean-export-grid">{analysis}</div></details>{f"<details class='export-section export-details admin-only'><summary>Admin/internal exports</summary><div class='export-grid2 clean-export-grid'>{internal}</div></details>" if internal else ""}'''

def month_year_selector(first,selected):
    months=''.join(f'<option value="{m:02d}" {"selected" if first.month==m else ""}>{date(2000,m,1).strftime("%B")}</option>' for m in range(1,13))
    base=(selected or date.today()).year
    years=''.join(f'<option value="{y}" {"selected" if first.year==y else ""}>{y}</option>' for y in range(base-1,base+3))
    return f'<form class="month-picker" method="get" action="/calendar"><label>Month<select name="month_m">{months}</select></label><label>Year<select name="month_y">{years}</select></label><button>View month</button></form>'

def monthly_calendar_grid(s,q):
    selected=pdate(q.get('selected_meeting',[''])[0]) or pdate(period(s,0)['meeting'])
    if q.get('month_y') and q.get('month_m'):
        ym=f'{q.get("month_y",[""])[0]}-{q.get("month_m",[""])[0]}'
    else:
        ym=q.get('month',[''])[0] or (selected.strftime('%Y-%m') if selected else date.today().strftime('%Y-%m'))
    first,prev_month,next_month=month_bounds(ym); meetings=factual_meetings(s); bydate={m['date']:m for m in meetings}; today=date.today(); start=first-timedelta(days=first.weekday()); cells=[]
    for i in range(42):
        d=start+timedelta(days=i); m=bydate.get(d); cls='muted' if d.month!=first.month else ''
        label=''
        if m:
            cls+=f' meeting {m["kind"]}'; proj=' projected' if m.get('projected') else ''; label=f'<a class="{proj}" href="/calendar?month={first.strftime("%Y-%m")}&selected_meeting={d.isoformat()}">{esc(m["label"])}</a>'
        if d==selected: cls+=' selected'
        if d==today: cls+=' today'
        cells.append(f'<div class="cal-cell {cls}"><b>{d.day}</b>{label}</div>')
    heads=''.join(f'<div class="cal-head">{x}</div>' for x in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'])
    nav=f'<div class="month-tools">{month_year_selector(first,selected)}<div class="month-nav"><a class="btn" href="/calendar?month={prev_month.strftime("%Y-%m")}">Previous</a><a class="btn" href="/calendar">Current reporting month</a><a class="btn" href="/calendar?month={next_month.strftime("%Y-%m")}">Next</a></div></div>'
    return nav+f'<div class="month-title"><h3>{first.strftime("B %Y") if False else first.strftime("%B %Y")}</h3><div class="legend"><span class="prevdot">Previous meeting</span><span class="curdot">Current meeting</span><span class="futdot">Projected meeting</span></div></div><div class="month-grid clean-month-grid">{heads}{"".join(cells)}</div>', selected

def calendar_page(s,q,msg=''):
    grid,selected=monthly_calendar_grid(s,q); admin=calendar_admin_controls(s,q)
    return f'<section class="page-title"><em>Calendar</em><h2>Meeting schedule</h2><p>Use this page to see which month meetings fall in and which report window each meeting covers. Read the actual briefs from Market Brief.</p></section><section class="calendar-layout"><div class="panel calendar-grid-panel">{grid}</div>{selected_meeting_panel(s,selected)}</section>{admin}<section class="panel history-panel"><h3>Historical brief files</h3><p class="muted">Historical files are shown for reference. Open readable briefs from the Market Brief selector.</p>{history(s)}</section>'

# Local proof-of-concept permissions after removing visible role cosplay control.
def can(s,a):
    role='Admin' if s.get('current_user') in ('Shauna','Daryl') or s.get('current_role')=='Admin' else s.get('current_role','Viewer')
    return a in ROLES.get(role,set())

# --- Final display fix: clear SG rank labels, tighter cards, readable detail drawer ---
def rank_pair_values(rank_text):
    text=str(rank_text or '')
    dl=[int(x) for x in re.findall(r'DL\s*#(\d+)', text, flags=re.I)]
    rev=[int(x) for x in re.findall(r'Rev\s*#(\d+)', text, flags=re.I)]
    return (min(dl) if dl else None, min(rev) if rev else None)

def rank_badge(value):
    return f'#{value}' if value else 'NA'

def sg_rank_blocks(r):
    dl,rev=rank_pair_values(r.get('SG App Store Ranks'))
    return f'''<div class="rank-pair"><span><small>SG Top Free Rank</small><b>{rank_badge(dl)}</b></span><span><small>SG Top Grossing Rank</small><b>{rank_badge(rev)}</b></span></div>'''

def market_signal_card(r,i,kind='strong',featured=False):
    accent='strong' if kind=='strong' else 'emerging'
    subtitle='SG revenue threshold met' if kind=='strong' else 'New launch to monitor'
    size=' featured-card' if featured or r.get('market_brief_card_size')=='featured' else ''
    pin='<span class="pin">Featured</span>' if featured or r.get('pinned_position') else ''
    genre_bits=' · '.join([x for x in [r.get('Platform'),r.get('Genre'),('Released '+r.get('Release Date')) if r.get('Release Date') else ''] if x])
    brief_id=globals().get('CURRENT_BRIEF_ID','current')
    selected=urllib.parse.quote(str(r.get('_uid','')), safe='')
    return f'''<a class="signal-card {accent}{size}" href="/market-brief?brief={esc(brief_id)}&selected={selected}&view=cards">
      <div class="card-top"><span class="sig {'strong' if kind=='strong' else 'em'}">{esc(r.get('Signal Display'))}</span>{pin}</div>
      <div class="card-title-block"><h3>{esc(display_name(r))}</h3><p class="publisher">{esc(r.get('Publisher'))}</p><p class="game-meta2">{esc(genre_bits)}</p></div>
      <div class="revenue-metric"><b>{money(r.get('SG Gross Revenue'))}</b><span>Estimated SG gross revenue</span></div>
      <div class="support-metrics"><span><b>{sg_downloads_value(r):,}</b><small>SG downloads</small></span></div>
      {sg_rank_blocks(r)}
      <div class="markets-label">Top SEA6 Markets</div>{market_chips(r)}
      <div class="card-footer"><span>{subtitle}</span><strong>View Details</strong></div>
    </a>'''

def featured_leader(rs):
    strong=[r for r in rs if r.get('Signal Type')=='Strong Market Signal']
    starred=[r for r in strong if r.get('Starred')=='Yes']
    pool=starred or strong or rs
    leader=max(pool,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
    if not leader: return '<div class="feature-card empty">No featured title yet.</div>'
    return f'''<aside class="feature-card hero-feature"><div class="feature-kicker">Featured Commercial Signal</div><h3>{esc(display_name(leader))}</h3><p>{esc(leader.get('Publisher'))}</p><div class="feature-money">{money(leader.get('SG Gross Revenue'))}<small>Estimated SG gross revenue</small></div>{sg_rank_blocks(leader)}<div class="markets-label">Top SEA6 Markets</div>{market_chips(leader)}<span class="sig strong">Strong Market Signal</span></aside>'''

def detail_metric(label,value):
    return f'<div class="detail-metric"><small>{esc(label)}</small><b>{value}</b></div>'

def market_detail_from_rows(uid_value,s,source_rows,rec):
    if not uid_value: return ''
    uid_decoded=urllib.parse.unquote(str(uid_value))
    r=next((x for x in source_rows if str(x.get('_uid')) in (str(uid_value),uid_decoded)),None)
    if not r: return '<aside class="public-detail"><a class="close" href="/market-brief">Close</a><h2>Details unavailable</h2><p class="empty">This game could not be matched to the selected brief row.</p></aside>'
    admin=can(s,'diagnostics') or can(s,'classify')
    dl,rev=rank_pair_values(r.get('SG App Store Ranks'))
    note=f'<section class="drawer-section"><h4>Approved report note</h4><p>{esc(r.get("Approved Report Note"))}</p></section>' if r.get('Approved Report Note') else ''
    admin_evidence=f'<div class="evidence-grid"><div><small>App-ID evidence</small><b>{esc(uid_decoded)}</b></div><div><small>Original Title</small><b>{esc(r.get("Original Title"))}</b></div><div><small>Translation Source</small><b>{esc(r.get("Translation Source"))}</b></div><div><small>Translation Status</small><b>{esc(r.get("Translation Review Status"))}</b></div></div>' if admin else ''
    return f'''<aside class="public-detail refined-detail"><a class="close" href="/market-brief?brief={esc(rec['id'])}">Close</a><div class="detail-title"><span class="sig {'strong' if r.get('Signal Type')=='Strong Market Signal' else 'em'}">{esc(r.get('Signal Display'))}</span><h2>{esc(display_name(r))}</h2><p>{esc(r.get('Publisher'))}</p></div><section class="drawer-section overview-section"><h4>Overview</h4><div class="detail-grid"><div><small>Platform</small><b>{esc(r.get('Platform') or 'Not available')}</b></div><div><small>SG Release Date</small><b>{esc(display_date(r.get('Release Date')) or 'Not available')}</b></div><div><small>Genre</small><b>{esc(r.get('Genre') or 'Not available')}</b></div></div><div class="drawer-metrics">{detail_metric('Estimated SG gross revenue',money(r.get('SG Gross Revenue')))}{detail_metric('SG downloads',f'{sg_downloads_value(r):,}')}{detail_metric('SG Top Free Rank',rank_badge(dl))}{detail_metric('SG Top Grossing Rank',rank_badge(rev))}</div></section><section class="drawer-section"><h4>SEA6 Performance</h4>{sea6_table(r)}</section><section class="drawer-section"><h4>Evidence</h4><div class="evidence-grid"><div><small>SG ranking evidence</small><b>{esc(r.get('SG App Store Ranks') or 'Not available')}</b></div><div><small>Release-date evidence</small><b>{esc(display_date(r.get('Release Date')) or 'Not available')}</b></div><div><small>Brief type</small><b>{esc(rec.get('type'))}</b></div></div>{admin_evidence}</section>{note}</aside>'''

# Market overview judgement layer: hide Radar-filtered false alarms from reader-facing Market Brief.
def brief_included(r):
    if r.get('Market Overview Status') == 'Filter from Market Overview':
        return False
    if r.get('Excluded') == 'Yes':
        return False
    if r.get('admin_hide_from_brief') == 'true':
        return False
    if r.get('include_in_market_brief') == 'false':
        return False
    if r.get('Selected For Report') == 'No':
        return False
    return True

# --- UX alignment cleanup pass: reduce refresh jump, remove duplicate hero content, clarify ranks ---
def clean_date_label(value):
    return nd(value) if value else 'Unavailable'

def brief_title(rec):
    start=nd(rec.get('start')) if rec.get('start') else 'Period unavailable'
    end=nd(rec.get('end')) if rec.get('end') else ''
    meeting=nd(rec.get('meeting')) if rec.get('meeting') else 'Meeting unavailable'
    period_label=f'{start}–{end}' if end else start
    return f'Report Period: {period_label} · Meeting: {meeting} · {rec.get("type")}'

def brief_selector(q,s,rec,rs):
    search=q.get('brief_search',[''])[0].strip().lower()
    allrecs=brief_records()
    if search:
        filtered=[]
        for br in allrecs:
            hay=' '.join([br.get('start',''),br.get('end',''),br.get('meeting',''),br.get('type',''),br.get('status','')]).lower()
            sample=' '.join((r.get('Game Title','')+' '+r.get('Publisher','')+' '+r.get('Signal Display','')) for r in raw_rows_for_brief(br)[:200]).lower()
            if search in hay or search in sample: filtered.append(br)
    else:
        filtered=allrecs
    recent=''.join(brief_option_card(br,rec) for br in allrecs[:5])
    grouped={}
    for br in filtered:
        d=pdate(br.get('meeting')) or pdate(br.get('end'))
        key=d.strftime('%b %Y') if d else 'Date unavailable'
        grouped.setdefault(key,[]).append(br)
    archive=''.join(f'<div class="brief-month"><h4>{esc(k)}</h4>{"".join(brief_option_card(x,rec,compact=True) for x in v)}</div>' for k,v in grouped.items()) or '<p class="empty">No briefs match the search.</p>'
    legacy_note='<div class="legacy-note">Legacy brief: some structured fields may be unavailable.</div>' if rec.get('type')=='Legacy Brief' else ''
    return f'''<section class="brief-selector refined-selector"><details><summary><span>Viewing</span><b>{esc(brief_title(rec))}</b></summary><div class="brief-popover"><div class="brief-search"><h3>Select Market Brief</h3><form><input type="hidden" name="brief" value="{esc(rec['id'])}"><input name="brief_search" value="{esc(search)}" placeholder="Search by game, publisher, period, meeting date, signal"><button>Search</button><a class="btn" href="/market-brief">Reset</a></form></div><div class="brief-columns"><section><h4>Recent</h4>{recent}</section><section><h4>All Briefs</h4>{archive}</section></div></div></details>{legacy_note}</section>'''

def compact_public_table(rs):
    if not rs: return '<p class="empty polished-empty">No launches match the current view.</p>'
    brief_id=globals().get('CURRENT_BRIEF_ID','current')
    body=''
    for r in rs:
        dl,rev=rank_pair_values(r.get('SG App Store Ranks'))
        body+=f'<tr onclick="location.href=\'/market-brief?brief={esc(brief_id)}&selected={esc(r.get("_uid"))}&view=table\'"><td><b>{esc(display_name(r))}</b></td><td>{esc(r.get("Publisher"))}</td><td><span class="sig {"strong" if r.get("Signal Type")=="Strong Market Signal" else "em"}">{esc(r.get("Signal Display"))}</span></td><td class="num">{money(r.get("SG Gross Revenue"))}</td><td class="num">{sg_downloads_value(r):,}</td><td class="num">{rank_badge(dl)}</td><td class="num">{rank_badge(rev)}</td><td>{esc(topm(r.get("Top 3 Markets")))}</td></tr>'
    return f'<div class="table public-table clean-table"><table><thead><tr><th>Game</th><th>Publisher</th><th>Signal</th><th class="num">SG Revenue</th><th class="num">SG Downloads</th><th class="num">SG Top Free Rank</th><th class="num">SG Top Grossing Rank</th><th>Top Market</th></tr></thead><tbody>{body}</tbody></table></div>'

def hero_kpis(c,total_rev):
    return f'''<div class="hero-kpis">{card('Detected Launches',c['total'],'Included in this Market Brief.')}{card('Strong Market Signals',c['strong'],'Above $1K SG gross revenue during the release/report period.')}{card('Emerging Market Signals',c['emerging'],'New launches worth monitoring.')}{card('Estimated SG Gross Revenue',money(total_rev),'Gross revenue estimate across included launches.')}</div>'''

def market(s,q,msg=''):
    rec=selected_brief(q,s); globals()['CURRENT_BRIEF_ID']=rec['id']; globals()['CURRENT_BRIEF_CONTEXT']=rec
    all_rows=raw_rows_for_brief(rec); view=q.get('view',['cards'])[0]; selected=q.get('selected',[''])[0]
    rs=[r for r in all_rows if brief_included(r)]
    c,total_rev=public_signal_summary(rs)
    strong=sorted([r for r in rs if r.get('Signal Type')=='Strong Market Signal'],key=lambda r:(curation_sort(r),-sf(r.get('SG Gross Revenue'))))
    emerging=sorted([r for r in rs if r.get('Signal Type')!='Strong Market Signal'],key=lambda r:(curation_sort(r),-sf(r.get('SG Gross Revenue')),bestrank(r.get('SG App Store Ranks')),pdate(r.get('Release Date')) or date.min))
    summary=f"{c['total']} launches are included in this Market Brief. {c['strong']} meet the Strong threshold, while {c['emerging']} are emerging titles to monitor."
    cards_strong=''.join(market_signal_card(r,i+1,'strong',i==0) for i,r in enumerate(strong)) or '<p class="empty">No strong market signals in this brief.</p>'
    cards_em=''.join(market_signal_card(r,i+1,'emerging') for i,r in enumerate(emerging)) or '<p class="empty">No emerging market signals in this brief.</p>'
    strong_body=compact_public_table(strong) if view=='table' else f'<div class="signal-card-grid strong-grid">{cards_strong}</div>'
    emerging_body=compact_public_table(emerging) if view=='table' else f'<div class="signal-card-grid emerging-grid">{cards_em}</div>'
    toggle=f'<div class="view-toggle"><a class="{"on" if view=="cards" else ""}" href="/market-brief?brief={esc(rec["id"])}&view=cards">Cards</a><a class="{"on" if view=="table" else ""}" href="/market-brief?brief={esc(rec["id"])}&view=table">Compact Table</a></div>'
    detail=market_detail_from_rows(selected,s,all_rows,rec)
    return f'''{brief_selector(q,s,rec,rs)}<section class="portal-hero refined-hero"><div class="portal-copy"><em>Market Brief</em><h2>Singapore Mobile Launch Brief</h2><p class="periodline">{esc(brief_title(rec))}</p><p class="summaryline">{esc(summary)}</p><div class="hero-actions"><a class="btn blue" href="/export/print.html?brief={esc(rec['id'])}">Print Report</a><a class="btn" href="/export/executive.csv?brief={esc(rec['id'])}">Export Executive CSV</a></div></div>{hero_kpis(c,total_rev)}</section>{toggle}<section class="report-section strong-section"><div class="section-head"><h2>Strong Market Signals</h2><p>Above $1K SG gross revenue during the release/report period.</p></div>{strong_body}</section><section class="report-section emerging-section"><div class="section-head"><h2>Emerging Market Signals</h2><p>New SG launches detected; commercial relevance is still developing.</p></div>{emerging_body}</section>{explore_launches_section(s,q)}{detail}'''

def selected_meeting_panel(s,meeting):
    info=selected_meeting_info(s,meeting); br=brief_for_meeting_date(s,meeting)
    if br:
        br_rows=raw_rows_for_brief(br); c=counts(br_rows)
        brief_block=f'<div class="meeting-brief-preview"><p><b>{c["total"]}</b> launches · <b>{c["strong"]}</b> strong · <b>{c["emerging"]}</b> emerging</p><a class="btn blue" href="/market-brief?brief={esc(br["id"])}">Open Market Brief</a></div>'
        report_label=f'{br.get("type")} · {br.get("status")}'
    else:
        brief_block='<p class="muted">No Market Brief has been generated for this meeting yet.</p>' if info.get('status')=='Planned' else '<p class="muted">No saved brief is linked to this meeting.</p>'
        report_label=info.get('report_label')
    def d(x): return nd(x) if x else 'Unavailable'
    rows_html=''.join(f'<div class="meeting-detail-row"><span>{label}</span><b>{value}</b></div>' for label,value in [('Report Window',f'{d(info.get("start"))} to {d(info.get("end"))}'),('Data As Of',d(info.get('effective'))),('Status',info.get('status')),('Brief',report_label)])
    steps=[('Previous Meeting',info.get('previous'),'meeting'),('Report Start',info.get('start'),'window'),('Report End',info.get('end'),'window'),('Meeting Date',info.get('meeting'),'meeting current'),('Data As Of',info.get('effective'),'data')]
    timeline=''.join(f'<div class="time-step {cls}"><small>{esc(label)}</small><b>{d(val)}</b></div>' for label,val,cls in steps)
    return f'<aside class="meeting-panel clean-meeting-panel aligned-meeting-panel"><h3>{d(info.get("meeting"))}</h3><div class="meeting-detail-grid">{rows_html}</div>{brief_block}<div class="timeline refined">{timeline}</div></aside>'

def layout(path,s,content):
    rs=rows(); p=period(s); data_as_of=data_asof(rs,p)
    if path=='/market-brief' and 'CURRENT_BRIEF_CONTEXT' in globals():
        br=globals().get('CURRENT_BRIEF_CONTEXT') or {}
        p={'start':br.get('start') or p.get('start'), 'end':br.get('end') or p.get('end'), 'meeting':br.get('meeting') or ''}
        data_as_of=nd((pdate(p.get('end'))-timedelta(days=LAG)).isoformat()) if pdate(p.get('end')) else 'Unavailable'
    meeting_label=nd(p['meeting']) if p.get('meeting') else 'Unavailable'
    nav_desc={'/market-brief':'Read current and archived Singapore launch briefs.','/data-export':'Download the main report or analyst datasets.','/calendar':'View meeting months and reporting windows.','/admin':'Internal controls for scans, curation, and diagnostics.'}
    nav_items=[('/market-brief','Market Brief'),('/data-export','Data Export'),('/calendar','Calendar')]
    if current_access_role(s)=='Admin': nav_items.append(('/admin','Admin'))
    nav=''.join(f'<a class="{"on" if path==u else ""}" href="{u}" title="{esc(nav_desc[u])}"><span>{label}</span><small>{esc(nav_desc[u])}</small></a>' for u,label in nav_items)
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IBD Market Intelligence</title><style>{CSS}</style><script>{JS}</script></head><body><div class="shell clean-shell"><aside><div class="brandmark">IBD Market Intelligence</div><h1>Singapore · Mobile Launch Discovery</h1><span>Proof of Concept</span><nav>{nav}</nav><p class="future">Mobile launch discovery module. Future PC, console, announcement, and news modules are not part of this proof of concept.</p></aside><div class="page-frame"><header class="context clean-context refined-context"><div><small>Report period</small><b>{nd(p['start'])} – {nd(p['end'])}</b></div><div><small>Meeting date</small><b>{meeting_label}</b></div><div><small>Data as of</small><b>{data_as_of}</b></div></header><main class="content-wrap">{content}</main></div></div></body></html>'''

def data_export(s,q,msg=''):
    rs=rows(); p=period(s); per=f'{nd(p["start"])} to {nd(p["end"])}'
    primary=''.join([export_card('Print-ready Market Brief','Readers / meeting use',len(rs),'HTML','/export/print.html','A clean reading copy of the Market Brief.',per,True),export_card('Executive CSV','Leadership / report paste',len(rs),'CSV','/export/executive.csv','A clean CSV for report preparation.',per,True)])
    advanced_report=''.join([export_card('Strong signals only','Analyst',counts(rs)['strong'],'CSV','/export/strong.csv','Strong section only.',per),export_card('Emerging signals only','Analyst',counts(rs)['emerging'],'CSV','/export/emerging.csv','Emerging section only.',per)])
    analysis=''.join([export_card('Full launch dataset','Analyst',len(rows(True)),'CSV','/export/launches.csv','All current launch rows.',per),export_card('Detailed evidence dataset','Analyst',len(rows(True)),'CSV','/export/evidence.csv','App IDs and supporting evidence.',per),export_card('SEA6 market metrics','Analyst','available','CSV','/export/sea6.csv','Country-level revenue and downloads.',per),export_card('Title normalisation dataset','Analyst','available','CSV','/export/title-normalisation.csv','Original titles and English display titles.',per)])
    internal=''
    if current_access_role(s)=='Admin' and can(s,'diagnostics'):
        internal=''.join([export_card('Override history','Admin',len(rc(HIST) or rc(OVR)),'CSV','/export/admin.csv','Manual curation history.',per),export_card('Review queue','Admin',counts(rows(True))['attention'],'CSV','/export/review.csv','Internal review records.',per),export_card('Raw workflow decisions','Admin','available','CSV','/export/workflow-decisions.csv','Workflow decision trail.',per)])
    return f'''<section class="page-title"><em>Data Export</em><h2>Download reports and datasets</h2><p>Export the reader-ready brief or supporting analyst datasets.</p></section><section class="export-section primary-export-section"><h3>Main exports</h3><div class="export-grid2 clean-export-grid primary-only">{primary}</div></section><details class="export-section export-details"><summary>More analyst exports</summary><h4>Report slices</h4><div class="export-grid2 clean-export-grid">{advanced_report}</div><h4>Analysis datasets</h4><div class="export-grid2 clean-export-grid">{analysis}</div></details>{f"<details class='export-section export-details admin-only'><summary>Admin/internal exports</summary><div class='export-grid2 clean-export-grid'>{internal}</div></details>" if internal else ""}'''

# -----------------------------------------------------------------------------
# Executive intelligence UX layer
# -----------------------------------------------------------------------------
# Reader-first portal layer. It preserves the Sensor Tower workflow and CSV
# outputs, while changing navigation, labels, and progressive disclosure.

AI_NEWS_RADAR_URL = 'https://darylwong-playpark.github.io/ai-news-radar/'
NAV_ITEMS = [
    ('/latest-brief', 'Latest Brief', 'Read the current executive market update.'),
    ('/historical-briefs', 'Historical Briefs', 'Open previous reporting-period briefs.'),
    ('/game-tracker', 'Game Tracker', 'Review games mentioned across briefs.'),
    ('/market-timeline', 'Market Timeline', 'Understand meeting dates and reporting windows.'),
    ('/trends', 'Trends / Insights', 'See patterns across launches, publishers, and genres.'),
    ('/admin', 'Admin Console', 'Manage scans, drafts, publishing, and evidence.'),
]
ROUTE_ALIASES = {'/':'/latest-brief','':'/latest-brief','/market-brief':'/latest-brief','/data-export':'/historical-briefs','/calendar':'/market-timeline','/launches':'/game-tracker','/reports':'/historical-briefs','/review':'/admin','/operations':'/admin'}

def current_access_role(s): return s.get('_auth_role') or s.get('current_role') or ('Admin' if s.get('current_user') in ADMINS else 'Viewer')
def display_name(r): return (r.get('Manual English Title') or r.get('manual_english_title') or r.get('English Display Title') or r.get('display_title') or r.get('Machine English Title') or r.get('Game Title') or r.get('Original Title') or 'Untitled Game').strip()
def signal_label(r): return SIGDIS.get(r.get('Signal Type'), r.get('Signal Display') or r.get('Signal Type') or 'Emerging Market Signal')
def rank_text(v): return f'#{v}' if v else 'Not ranked'

def source_rows(include_filtered=True):
    path = OUT / 'layer5_market_overview_judgement.csv'
    if not path.exists(): path = FINAL
    base = rc(path); ovs = ovr(); out = []
    for raw in base:
        r = dict(raw); u = uid(r); y = ovs.get(u,{})
        r['_uid'] = u
        if y.get('manual_english_title'): r['Manual English Title'] = y.get('manual_english_title')
        if y.get('override_signal_type'): r['Signal Type'] = DISP_BACK.get(y['override_signal_type'], y['override_signal_type'])
        r['Signal Display'] = signal_label(r)
        r['Starred'] = y.get('starred','No') or 'No'; r['Excluded'] = y.get('deleted','No') or 'No'
        r['Approved Report Note'] = y.get('approved_report_note',''); r['Discussion Notes'] = y.get('notes','')
        r['Review Status'] = y.get('review_status','Unreviewed') or 'Unreviewed'
        r['include_in_market_brief'] = y.get('include_in_market_brief',''); r['admin_hide_from_brief'] = y.get('admin_hide_from_brief','')
        if include_filtered or brief_included(r): out.append(r)
    return out

def reader_rows(): return [r for r in source_rows(True) if brief_included(r)]

def first_date(rows_, field):
    vals = [pdate(r.get(field)) for r in rows_ if pdate(r.get(field))]
    return min(vals).isoformat() if vals else ''
def last_date(rows_, field):
    vals = [pdate(r.get(field)) for r in rows_ if pdate(r.get(field))]
    return max(vals).isoformat() if vals else ''

def brief_records():
    rs=source_rows(True); s=state(); p=period(s)
    start=first_date(rs,'report_start_date') or p['start']; end=last_date(rs,'report_end_date') or p['end']
    meeting=(pdate(end)+timedelta(days=1)).isoformat() if pdate(end) else p['meeting']
    recs=[{'id':'current','start':start,'end':end,'meeting':meeting,'type':'Portal Brief','status':s.get('report_status','Draft'),'path':'current'}]
    if SNAP.exists():
        for f in sorted(SNAP.glob('portal_report_*.csv'), reverse=True):
            m=re.search(r'portal_report_(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})', f.name)
            if m:
                st,en=m.group(1),m.group(2); mt=(pdate(en)+timedelta(days=1)).isoformat() if pdate(en) else ''
                recs.append({'id':f.name,'start':st,'end':en,'meeting':mt,'type':'Portal Brief','status':'Archived','path':str(f)})
    seen=set(); clean=[]
    for r in recs:
        key=(r.get('start'),r.get('end'),r.get('meeting'),r.get('type'))
        if key not in seen: seen.add(key); clean.append(r)
    return clean

def selected_brief(q,s):
    wanted=q.get('brief',['current'])[0]; recs=brief_records()
    return next((r for r in recs if r['id']==wanted), recs[0])
def raw_rows_for_brief(rec):
    if rec.get('path')=='current': return source_rows(True)
    path=Path(rec.get('path','')); return rc(path) if path.exists() else []
def rows_for_brief(rec):
    out=[]
    for raw in raw_rows_for_brief(rec):
        r=dict(raw); r['_uid']=uid(r); r['Signal Display']=signal_label(r)
        if rec.get('path')!='current' or brief_included(r): out.append(r)
    return out
def period_label(rec): return f"{nd(rec.get('start')) or 'Start unavailable'}–{nd(rec.get('end')) or 'End unavailable'}"
def brief_title(rec): return f"{period_label(rec)} · Meeting {nd(rec.get('meeting')) or 'Unavailable'} · {rec.get('type','Brief')}"

def sg_downloads_value(r):
    m=re.search(r'SG \(\$[0-9,]+ / ([0-9,]+) DL\)', r.get('Top 3 Markets','') or '')
    return int(m.group(1).replace(',','')) if m else 0
def rank_pair_values(text):
    text=text or ''; dl=re.findall(r'DL #([0-9]+|NA)',text); rev=re.findall(r'Rev #([0-9]+|NA)',text)
    def best(vals):
        nums=[int(v) for v in vals if str(v).isdigit()]
        return min(nums) if nums else None
    return best(dl), best(rev)
def best_rank_strength(r):
    dl,rev=rank_pair_values(r.get('SG App Store Ranks'))
    return min([x for x in (dl,rev) if x] or [99999])
def market_entries(r):
    raw=(r.get('Top 3 Markets') or '').replace('Top Mkts:','').strip().rstrip('.'); entries=[]
    for part in [p.strip() for p in raw.split('||') if p.strip()]:
        m=re.match(r'([A-Z]{2}) \(\$([0-9,]+) / ([0-9,]+) DL\)',part)
        if m: entries.append({'country':m.group(1),'revenue':float(m.group(2).replace(',','')),'downloads':int(m.group(3).replace(',',''))})
    return entries
def market_chips(r):
    entries=market_entries(r)
    if not entries: return '<div class="market-chip-row"><span class="market-chip empty">SEA6 markets unavailable</span></div>'
    chips=''
    for i,e in enumerate(entries[:4],1):
        sg=' sg-market' if e['country']=='SG' else ''
        chips += f'<span class="market-chip{sg}"><small>#{i} {esc(e["country"])}</small><b>{money(e["revenue"])}</b><em>{e["downloads"]:,} DL</em></span>'
    return f'<div class="market-chip-row">{chips}</div>'
def status_badge(text):
    klass='published' if str(text).lower() in ('published','finalised','archived') else 'draft'
    return f'<span class="status-badge {klass}">{esc(text or "Draft")}</span>'
def export_links(): return '<div class="action-row"><a class="btn primary" href="/export/print.html">Print Report</a><a class="btn" href="/export/executive.csv">Export Executive CSV</a></div>'

def executive_summary_bullets(rs):
    strong=[r for r in rs if r.get('Signal Type')=='Strong Market Signal']; emerging=[r for r in rs if r.get('Signal Type')!='Strong Market Signal']
    leader=max(strong or rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={}); pubs={}; genres={}
    for r in rs:
        pubs[r.get('Publisher') or 'Unknown']=pubs.get(r.get('Publisher') or 'Unknown',0)+1
        for g in re.split(r';|,',r.get('Genre','') or ''):
            g=g.strip()
            if g: genres[g]=genres.get(g,0)+1
    top_pub=max(pubs.items(),key=lambda x:x[1],default=('No publisher concentration',0)); top_genre=max(genres.items(),key=lambda x:x[1],default=('No clear genre concentration',0))
    bullets=[f"{len(rs)} Singapore mobile launches are included in this brief: {len(strong)} Strong Market Signals and {len(emerging)} Emerging Market Signals.",
             f"{display_name(leader)} leads the period by estimated SG gross revenue at {money(leader.get('SG Gross Revenue'))}." if leader else 'No commercial leader is available for this period.',
             f"{top_pub[0]} has the highest publisher activity in this brief with {top_pub[1]} launch record(s)." if top_pub[1] else 'No publisher concentration is available.',
             f"{top_genre[0]} is the most repeated genre signal among detected launches." if top_genre[1] else 'No genre concentration is available.']
    return ''.join(f'<li>{esc(b)}</li>' for b in bullets)

def top_cards(rs):
    strong=[r for r in rs if r.get('Signal Type')=='Strong Market Signal']; emerging=[r for r in rs if r.get('Signal Type')!='Strong Market Signal']
    leader=max(strong or rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
    emerg=sorted(emerging,key=lambda r:(-sf(r.get('SG Gross Revenue')),best_rank_strength(r),r.get('Release Date','')))
    risk=emerg[0] if emerg else {}; snapshot=f'{len(rs)} included launches · {len(strong)} strong · {len(emerging)} emerging'
    opportunity=f'{display_name(leader)} leads SG revenue at {money(leader.get("SG Gross Revenue"))}' if leader else 'No opportunity signal available yet'
    risk_text=f'{display_name(risk)} remains watchlist-level until stronger commercial evidence appears' if risk else 'No major watchlist item identified'
    action='Prioritise Strong Market Signals for business discussion; keep Emerging titles on monitoring until evidence strengthens.'
    return f'''<section class="summary-card-grid"><article class="summary-card"><small>Market Snapshot</small><h3>{esc(snapshot)}</h3><p>Current reporting-period launch activity.</p></article><article class="summary-card opportunity"><small>Notable Update</small><h3>{esc(opportunity)}</h3><p>Strongest commercially supported launch signal.</p></article><article class="summary-card risk"><small>Follow-up Note</small><h3>{esc(risk_text)}</h3><p>Needs monitoring, not escalation by default.</p></article><article class="summary-card action"><small>Monitoring Note</small><h3>{esc(action)}</h3><p>Use details only when further evidence is needed.</p></article></section>'''

def signal_card(r,kind='strong'):
    dl,rev=rank_pair_values(r.get('SG App Store Ranks')); href=f'/latest-brief?selected={urllib.parse.quote(str(r.get("_uid","")))}'
    return f'''<a class="signal-card {kind}" href="{href}"><div class="signal-card-top"><span class="signal-pill {kind}">{esc(signal_label(r))}</span><span class="view-link">View Details</span></div><h3>{esc(display_name(r))}</h3><p class="publisher-line">{esc(r.get('Publisher') or 'Publisher unavailable')}</p><p class="meta-line">{esc(r.get('Platform') or 'Platform unavailable')} · {esc(r.get('Genre') or 'Genre unavailable')} · Released {esc(display_date(r.get('Release Date')) or 'Unavailable')}</p><div class="primary-money"><b>{money(r.get('SG Gross Revenue'))}</b><span>Estimated SG gross revenue</span></div><div class="support-row"><span><b>{sg_downloads_value(r):,}</b><small>SG downloads</small></span><span><b>{rank_text(dl)}</b><small>SG Top Free</small></span><span><b>{rank_text(rev)}</b><small>SG Top Grossing</small></span></div><div class="market-title">Top SEA6 Markets</div>{market_chips(r)}</a>'''

def global_announcement_cards(rs):
    supported=[r for r in source_rows(True) if r.get('Radar URL') or r.get('Radar Matched Title') or r.get('Radar Source')]; cards=''
    for r in supported[:4]:
        title=r.get('Radar Matched Title') or display_name(r); source=r.get('Radar Source') or 'AI News Radar'; url=r.get('Radar URL') or AI_NEWS_RADAR_URL
        cards += f'''<article class="news-card"><span>Global Game Announcement</span><h3>{esc(title)}</h3><p>{esc(r.get('Publisher') or 'Publisher/developer unavailable')} · Source: {esc(source)}</p><p>Lightweight news highlight only. Sensor Tower performance metrics are intentionally not used for this section.</p><a href="{esc(url)}" target="_blank" rel="noopener">View source</a></article>'''
    if not cards:
        cards=f'<article class="empty-state"><h3>No global announcement highlights attached yet.</h3><p>Editors can attach highlights from AI News Radar when a story is relevant to the market brief.</p><a href="{AI_NEWS_RADAR_URL}" target="_blank" rel="noopener">Open AI News Radar</a></article>'
    return f'<section class="brief-section"><div class="section-heading"><h2>Global Game Announcements</h2><p>Lightweight news highlights only; no Sensor Tower metrics are shown here.</p></div><div class="news-grid">{cards}</div></section>'

def compact_public_table(rs):
    body=''
    for r in rs:
        dl,rev=rank_pair_values(r.get('SG App Store Ranks'))
        body += f'<tr><td><b>{esc(display_name(r))}</b></td><td>{esc(r.get("Publisher"))}</td><td>{esc(signal_label(r))}</td><td class="num">{money(r.get("SG Gross Revenue"))}</td><td class="num">{sg_downloads_value(r):,}</td><td class="num">{rank_text(dl)}</td><td class="num">{rank_text(rev)}</td></tr>'
    return f'<div class="data-table"><table><thead><tr><th>Game</th><th>Publisher</th><th>Signal</th><th class="num">SG Revenue</th><th class="num">SG Downloads</th><th class="num">SG Top Free</th><th class="num">SG Top Grossing</th></tr></thead><tbody>{body or "<tr><td colspan=7>No launches available.</td></tr>"}</tbody></table></div>'

def released_games_section(strong,emerging,view):
    if view=='table': return f'<section class="brief-section"><div class="section-heading"><h2>Released Games in Singapore</h2><p>Local market performance view for released mobile games.</p></div>{compact_public_table(strong+emerging)}</section>'
    strong_html=''.join(signal_card(r,'strong') for r in strong) or '<article class="empty-state"><h3>No Strong Market Signals yet.</h3><p>No launch exceeded the SG revenue threshold for this period.</p></article>'
    emerging_html=''.join(signal_card(r,'emerging') for r in emerging) or '<article class="empty-state"><h3>No Emerging Market Signals yet.</h3><p>No additional SG launches are included in this brief.</p></article>'
    return f'''<section class="brief-section"><div class="section-heading"><div><h2>Released Games in Singapore</h2><p>Sensor Tower-supported local launch performance. Stats support the judgement, but the cards stay executive-readable.</p></div><div class="view-toggle"><a class="on" href="/latest-brief?view=cards">Cards</a><a href="/latest-brief?view=table">Compact Table</a></div></div><h3 class="signal-heading strong-heading">Strong Market Signals <span>Commercial traction is already visible.</span></h3><div class="signal-grid strong-grid">{strong_html}</div><h3 class="signal-heading emerging-heading">Emerging Market Signals <span>New SG launches worth monitoring.</span></h3><div class="signal-grid emerging-grid">{emerging_html}</div></section>'''

def local_trends_section(rs):
    genres={}; pubs={}; platforms={}
    for r in rs:
        pubs[r.get('Publisher') or 'Unknown']=pubs.get(r.get('Publisher') or 'Unknown',0)+1; platforms[r.get('Platform') or 'Unknown']=platforms.get(r.get('Platform') or 'Unknown',0)+1
        for g in re.split(r';|,',r.get('Genre','') or ''):
            g=g.strip()
            if g: genres[g]=genres.get(g,0)+1
    def chips(d): return ''.join(f'<span class="trend-chip"><b>{esc(k)}</b><small>{v}</small></span>' for k,v in sorted(d.items(),key=lambda x:-x[1])[:5]) or '<span class="trend-chip">Unavailable</span>'
    return f'<section class="brief-section"><div class="section-heading"><h2>Local Market / Industry Trends</h2><p>Deterministic patterns from the launches in this brief.</p></div><div class="trend-panel"><div><h3>Genre Signals</h3>{chips(genres)}</div><div><h3>Publisher Activity</h3>{chips(pubs)}</div><div><h3>Platform Mix</h3>{chips(platforms)}</div></div></section>'

def watchlist_section(rs):
    emerging=sorted([r for r in rs if r.get('Signal Type')!='Strong Market Signal'], key=lambda r:(-sf(r.get('SG Gross Revenue')),best_rank_strength(r)))[:5]
    items=''.join(f'<li><b>{esc(display_name(r))}</b><span>{esc(r.get("Publisher"))} · {money(r.get("SG Gross Revenue"))} SG gross revenue · {rank_text(rank_pair_values(r.get("SG App Store Ranks"))[1])} SG Top Grossing</span></li>' for r in emerging)
    return f'<section class="brief-section"><div class="section-heading"><h2>Monitoring Notes / Watchlist</h2><p>Follow-up items for the next reporting discussion.</p></div><ul class="watch-list">{items or "<li>No watchlist items for this brief.</li>"}</ul></section>'

def detail_panel(selected, rs):
    if not selected: return ''
    decoded=urllib.parse.unquote(str(selected)); r=next((x for x in rs if str(x.get('_uid')) in (str(selected),decoded)),None)
    if not r: return '<aside class="detail-drawer"><a class="close" href="/latest-brief">Close</a><h2>Details unavailable</h2><p>This item could not be matched.</p></aside>'
    dl,rev=rank_pair_values(r.get('SG App Store Ranks'))
    market_rows=''.join(f'<tr><td>#{i}</td><td>{esc(e["country"])}</td><td class="num">{money(e["revenue"])}</td><td class="num">{e["downloads"]:,}</td></tr>' for i,e in enumerate(market_entries(r),1)) or '<tr><td colspan="4">SEA6 data unavailable.</td></tr>'
    source=f'<a href="{esc(r.get("Radar URL"))}" target="_blank" rel="noopener">{esc(r.get("Radar Source") or "Source")}</a>' if r.get('Radar URL') else 'Source unavailable'
    return f'''<aside class="detail-drawer"><a class="close" href="/latest-brief">Close</a><span class="signal-pill {'strong' if r.get('Signal Type')=='Strong Market Signal' else 'emerging'}">{esc(signal_label(r))}</span><h2>{esc(display_name(r))}</h2><p>{esc(r.get('Publisher') or '')}</p><div class="drawer-metrics"><div><small>SG Gross Revenue</small><b>{money(r.get('SG Gross Revenue'))}</b></div><div><small>SG Downloads</small><b>{sg_downloads_value(r):,}</b></div><div><small>SG Top Free</small><b>{rank_text(dl)}</b></div><div><small>SG Top Grossing</small><b>{rank_text(rev)}</b></div></div><section><h3>Overview</h3><dl><dt>Platform</dt><dd>{esc(r.get('Platform') or 'Unavailable')}</dd><dt>Release Date</dt><dd>{esc(display_date(r.get('Release Date')) or 'Unavailable')}</dd><dt>Genre</dt><dd>{esc(r.get('Genre') or 'Unavailable')}</dd><dt>Local relevance</dt><dd>{esc(r.get('Market Overview Reason') or r.get('Inclusion Reason') or 'Included in this reporting-period scan.')}</dd></dl></section><section><h3>SEA6 Performance</h3><table><thead><tr><th>Rank</th><th>Country</th><th class="num">Gross Revenue</th><th class="num">Downloads</th></tr></thead><tbody>{market_rows}</tbody></table></section><details><summary>Analyst evidence</summary><dl><dt>Ranking evidence</dt><dd>{esc(r.get('SG App Store Ranks') or 'Unavailable')}</dd><dt>Source</dt><dd>{source}</dd><dt>App family ID</dt><dd>{esc(r.get('_uid') or 'Unavailable')}</dd><dt>Original title</dt><dd>{esc(r.get('Original Title') or display_name(r))}</dd></dl></details></aside>'''

def brief_selector_widget(rec):
    recent=''.join(f'<a class="brief-choice {"active" if b["id"]==rec["id"] else ""}" href="/latest-brief?brief={urllib.parse.quote(b["id"])}"><b>{esc(period_label(b))}</b><span>{esc(nd(b.get("meeting")) or "Meeting unavailable")} · {esc(b.get("type"))} · {esc(b.get("status"))}</span></a>' for b in brief_records()[:8])
    return f'<details class="period-selector"><summary><span>Selected brief</span><b>{esc(brief_title(rec))}</b></summary><div class="selector-panel"><h3>Select Market Brief</h3><div class="selector-actions"><a class="btn primary" href="/latest-brief">Latest</a><a class="btn" href="/historical-briefs">Browse all historical briefs</a></div><div class="brief-choice-list">{recent}</div></div></details>'

def latest_brief(s,q,msg=''):
    rec=selected_brief(q,s); rs=rows_for_brief(rec); view=q.get('view',['cards'])[0]; selected=q.get('selected',[''])[0]
    strong=sorted([r for r in rs if r.get('Signal Type')=='Strong Market Signal'], key=lambda r:-sf(r.get('SG Gross Revenue')))
    emerging=sorted([r for r in rs if r.get('Signal Type')!='Strong Market Signal'], key=lambda r:(-sf(r.get('SG Gross Revenue')),best_rank_strength(r),r.get('Release Date','')))
    detail=detail_panel(selected,rs)
    page=f'''<section class="brief-hero"><div class="hero-copy"><em>Market Brief</em><h1>Singapore Gaming Market</h1><p class="period-line">{esc(period_label(rec))} · Meeting {esc(nd(rec.get('meeting')) or 'Unavailable')}</p><p class="hero-summary">{len(rs)} mobile launches are included in this brief. {len(strong)} show clear commercial traction, while {len(emerging)} are emerging launches to monitor.</p>{export_links()}</div><div class="hero-status"><small>Status</small>{status_badge(rec.get('status'))}<p>Last updated {esc(todaystamp())}</p></div></section>{brief_selector_widget(rec)}{top_cards(rs)}<section class="brief-section"><div class="section-heading"><h2>Executive Summary</h2><p>Level 1 scan: what changed, why it matters, and where to focus.</p></div><ul class="executive-bullets">{executive_summary_bullets(rs)}</ul></section>{global_announcement_cards(rs)}{released_games_section(strong,emerging,view)}{local_trends_section(rs)}{watchlist_section(rs)}<details class="methodology"><summary>Methodology and data notes</summary><p>Released Games in Singapore uses Sensor Tower-derived Singapore launch and SEA6 performance data where available. Global Game Announcements are lightweight news highlights and do not use Sensor Tower performance metrics. Revenue is shown as estimated gross revenue. Analyst evidence is available through details, exports, or Admin Console.</p><p><a href="{AI_NEWS_RADAR_URL}" target="_blank" rel="noopener">Open AI News Radar</a></p></details>'''
    return f'<div class="detail-layout"><div>{page}</div>{detail}</div>' if detail else page

def historical_briefs(s,q,msg=''):
    cards=''
    for rec in brief_records():
        rs=rows_for_brief(rec); strong=[r for r in rs if r.get('Signal Type')=='Strong Market Signal']; leader=max(strong or rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
        cards+=f'''<article class="archive-card"><div><small>{esc(rec.get('type'))}</small><h3>{esc(period_label(rec))}</h3><p>Meeting {esc(nd(rec.get('meeting')) or 'Unavailable')}</p>{status_badge(rec.get('status'))}</div><ul><li>{len(rs)} included launch records</li><li>{len(strong)} Strong Market Signals</li><li>Top title: {esc(display_name(leader)) if leader else 'Unavailable'}</li></ul><a class="btn primary" href="/latest-brief?brief={urllib.parse.quote(rec['id'])}">Open full brief</a></article>'''
    return f'<section class="page-intro"><em>Historical Briefs</em><h1>Brief archive</h1><p>Open past market briefs by reporting period. The calendar supports schedule context; this is the reading archive.</p></section><section class="archive-toolbar"><a class="btn primary" href="/latest-brief">Latest</a><select><option>Month selector</option></select><select><option>Year selector</option></select></section><div class="archive-grid">{cards or "<article class=\"empty-state\">No archived briefs available yet.</article>"}</div>'

def game_tracker(s,q,msg=''):
    text=q.get('q',[''])[0].strip().lower(); sig=q.get('signal',[''])[0]; rs=source_rows(True)
    if text: rs=[r for r in rs if text in ' '.join(str(v).lower() for v in r.values())]
    if sig: rs=[r for r in rs if signal_label(r)==sig]
    body=''.join(f'<tr><td><b>{esc(display_name(r))}</b><small>{esc(r.get("Original Title") or "")}</small></td><td>{esc(r.get("Publisher"))}</td><td>{esc(r.get("Platform"))}</td><td>Singapore</td><td>{esc(display_date(r.get("Release Date")) or "")}</td><td>{esc(r.get("Genre"))}</td><td>{"Released" if r.get("Release Date") else "Mentioned"}</td><td>{esc(signal_label(r))}</td><td>{esc(r.get("Market Overview Reason") or r.get("Inclusion Reason"))}</td><td><a href="/latest-brief?selected={urllib.parse.quote(str(r.get("_uid","")))}">Open brief</a></td></tr>' for r in rs)
    return f'''<section class="page-intro"><em>Game Tracker</em><h1>Games mentioned across briefs</h1><p>A structured working view for games, sources, status, and related briefs.</p></section><form class="tracker-filters"><input name="q" value="{esc(q.get('q',[''])[0])}" placeholder="Search game, publisher, genre, source"><select name="signal"><option value="">All signals</option><option>Strong Market Signal</option><option>Emerging Market Signal</option></select><button>Filter</button></form><div class="data-table"><table><thead><tr><th>Game</th><th>Publisher</th><th>Platform</th><th>Market</th><th>Event / Release Date</th><th>Genre</th><th>Status</th><th>Market Relevance</th><th>Key Details</th><th>Related Brief</th></tr></thead><tbody>{body or '<tr><td colspan="10">No matching games.</td></tr>'}</tbody></table></div>'''

def market_timeline(s,q,msg=''):
    recs=brief_records(); cur=recs[0]; p=period(s); md=pdate(cur.get('meeting')) or date.today()
    months=''.join(f'<option value="{i}" {"selected" if i==md.month else ""}>{datetime(2026,i,1).strftime("%B")}</option>' for i in range(1,13)); years=''.join(f'<option {"selected" if y==md.year else ""}>{y}</option>' for y in range(2025,2028))
    brief_list=''.join(f'<article class="meeting-card"><b>{esc(nd(r.get("meeting")) or "Unavailable")}</b><span>{esc(period_label(r))}</span>{status_badge(r.get("status"))}<a href="/latest-brief?brief={urllib.parse.quote(r["id"])}">Open Market Brief</a></article>' for r in recs)
    timeline=f'<div class="timeline-card"><div><small>Report Start</small><b>{esc(nd(cur.get("start")) or "Unavailable")}</b></div><div><small>Report End</small><b>{esc(nd(cur.get("end")) or "Unavailable")}</b></div><div><small>Meeting Date</small><b>{esc(nd(cur.get("meeting")) or "Unavailable")}</b></div><div><small>Data As Of</small><b>{esc(nd(p.get("effective")) or "Unavailable")}</b></div></div>'
    return f'<section class="page-intro"><em>Market Timeline</em><h1>Meeting rhythm and report windows</h1><p>Calendar is for schedule context. Use Historical Briefs or the Latest Brief selector to read briefs.</p></section><section class="calendar-controls"><button>Previous Month</button><select>{months}</select><select>{years}</select><button>Next Month</button><a class="btn" href="/market-timeline">Current reporting month</a></section><section class="timeline-layout"><div class="monthly-grid"><h3>Available brief meetings</h3>{brief_list or "<p class=\"empty-state\">No meeting records available.</p>"}</div><div class="selected-window"><h2>{esc(nd(cur.get("meeting")) or "Meeting unavailable")}</h2><p>Selected meeting summary</p><dl><dt>Report Window</dt><dd>{esc(period_label(cur))}</dd><dt>Status</dt><dd>{esc(cur.get("status"))}</dd><dt>Brief</dt><dd>{esc(cur.get("type"))}</dd></dl><a class="btn primary" href="/latest-brief?brief={urllib.parse.quote(cur["id"])}">Open Market Brief</a>{timeline}</div></section>'

def trends_insights(s,q,msg=''):
    rs=reader_rows(); total=sum(sf(r.get('SG Gross Revenue')) for r in rs); strong=[r for r in rs if r.get('Signal Type')=='Strong Market Signal']; pubs={}; genres={}; platforms={}
    for r in rs:
        pubs[r.get('Publisher') or 'Unknown']=pubs.get(r.get('Publisher') or 'Unknown',0)+1; platforms[r.get('Platform') or 'Unknown']=platforms.get(r.get('Platform') or 'Unknown',0)+1
        for g in re.split(r';|,',r.get('Genre','') or ''):
            g=g.strip()
            if g: genres[g]=genres.get(g,0)+1
    def insight(title,d):
        lis=''.join(f'<li><b>{esc(k)}</b><span>{v} signal(s)</span></li>' for k,v in sorted(d.items(),key=lambda x:-x[1])[:6]) or '<li>Not enough data yet.</li>'
        return f'<article class="insight-card"><h3>{esc(title)}</h3><ul>{lis}</ul></article>'
    return f'<section class="page-intro"><em>Trends / Insights</em><h1>Patterns across the market scan</h1><p>Deterministic summaries from current available brief data. Historical trend comparison can expand after more portal snapshots exist.</p></section><section class="summary-card-grid"><article class="summary-card"><small>Included Launches</small><h3>{len(rs)}</h3><p>Current brief data set.</p></article><article class="summary-card"><small>Strong Signals</small><h3>{len(strong)}</h3><p>Commercial traction visible.</p></article><article class="summary-card"><small>Estimated SG Gross Revenue</small><h3>{money(total)}</h3><p>Included launches only.</p></article></section><div class="insight-grid">{insight("Genre trends",genres)}{insight("Publisher activity",pubs)}{insight("Platform trends",platforms)}</div>'

def admin_console(s,q,msg=''):
    if current_access_role(s)!='Admin': return '<section class="page-intro"><em>Admin Console</em><h1>Restricted area</h1><p>This area is for editors, reviewers, and admins. Published briefs remain available from Latest Brief and Historical Briefs.</p></section>'
    p=period(s); allrs=source_rows(True); hidden=[r for r in allrs if not brief_included(r)]
    stages=''.join(f'<li>{esc(x)}</li>' for x in ['Retrieve SG ranking candidates','Resolve app identities','Fetch metadata','Fetch SEA6 performance','Build brief and review queue'])
    return f'''<section class="page-intro"><em>Admin Console</em><h1>Editor and publishing workspace</h1><p>Behind-the-scenes controls stay here so the executive brief remains clean.</p></section>{('<div class="toast">'+esc(msg)+'</div>') if msg else ''}<div class="admin-grid"><section class="admin-card"><h2>Reporting Period Management</h2><dl><dt>Current period</dt><dd>{esc(nd(p['start']))}–{esc(nd(p['end']))}</dd><dt>Meeting date</dt><dd>{esc(nd(p['meeting']))}</dd><dt>Status</dt><dd>{esc(s.get('report_status'))}</dd></dl><form method="post" action="/preview-date-change"><label>Upcoming meeting date</label><input type="date" name="meeting_date" value="{esc(p['meeting'])}"><button>Preview date change</button></form></section><section class="admin-card"><h2>Run Market Scan</h2><p>Runs the existing local Sensor Tower workflow. Token/configuration values are never displayed here.</p><ol>{stages}</ol><form method="post" action="/run-scan"><button class="primary">Run Market Scan</button></form></section><section class="admin-card"><h2>Brief Editor</h2><p>Edit executive summary, sections, follow-up notes, and source links in the next product phase. Current proof of concept uses deterministic generated copy.</p><a class="btn" href="/game-tracker">Open Game Tracker</a></section><section class="admin-card"><h2>Review & Publish</h2><form method="post" action="/set-report-status"><select name="status"><option>Draft</option><option>Review Required</option><option>Ready</option><option>Finalised</option><option>Archived</option></select><button>Update Status</button></form><p>Finalised snapshots are stored separately and should not be silently recomputed.</p></section><section class="admin-card"><h2>Game Entry Editor</h2><p>{len(allrs)} total launch records · {len(hidden)} hidden from Market Brief. Use this area for curation, manual English titles, notes, and source attachment.</p><a class="btn" href="/export/full.csv">Export full analyst dataset</a></section><details class="admin-card"><summary>Diagnostics and Evidence</summary><p>Output folder: data/output</p><div class="action-row"><a class="btn" href="/export/workflow-decisions.csv">Workflow decisions</a><a class="btn" href="/export/admin.csv">Override history</a><a class="btn" href="/export/title-normalisation.csv">Title normalisation</a></div></details></div>'''

market=latest_brief; calendar_page=market_timeline; data_export=historical_briefs; admin_page=admin_console

def layout(path,s,content):
    canonical=ROUTE_ALIASES.get(path,path)
    nav=''.join(f'<a class="{ "on" if canonical==href else "" }" href="{href}" title="{esc(desc)}"><span>{esc(label)}</span><small>{esc(desc)}</small></a>' for href,label,desc in NAV_ITEMS)
    p=period(s)
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IBD Market Intelligence</title><style>{CSS}</style></head><body><div class="app-shell"><aside class="sidebar"><div class="brand"><h1>IBD Market Intelligence</h1><p>Singapore · Mobile Launch Discovery</p><span>Proof of Concept</span></div><nav>{nav}</nav><div class="sidebar-note">Global news and local performance are intentionally separated.</div></aside><div class="workspace"><header class="topbar"><div><small>Reporting period</small><b>{esc(nd(p['start']))}–{esc(nd(p['end']))}</b></div><div><small>Meeting date</small><b>{esc(nd(p['meeting']))}</b></div><div><small>Data as of</small><b>{esc(nd(p['effective']))}</b></div><div><small>Publish status</small><b>{esc(s.get('report_status','Draft'))}</b></div><div class="top-actions"><a class="btn" href="/historical-briefs">Previous briefs</a><a class="btn primary" href="/latest-brief">Latest Brief</a></div></header><main>{content}</main></div></div><script>{JS}</script></body></html>'''



# -----------------------------------------------------------------------------
# Frontend polish layer
# -----------------------------------------------------------------------------
# This layer standardizes the executive UI system: typography, metadata, archive
# cards, timeline rhythm, and empty states. It deliberately avoids changing the
# scan pipeline or market classification logic.

def clean_period(rec):
    return f"{nd(rec.get('start')) or 'Start unavailable'}–{nd(rec.get('end')) or 'End unavailable'}"

def meta_item(label, value):
    return f'<div class="meta-item"><span>{esc(label)}</span><b>{esc(value or "Unavailable")}</b></div>'

def context_strip(rec, s=None):
    p = period(s or state())
    return f'''<section class="context-strip" aria-label="Brief context">
        {meta_item('Reporting period', clean_period(rec))}
        {meta_item('Meeting date', nd(rec.get('meeting')))}
        {meta_item('Data as of', nd(p.get('effective')))}
        <div class="meta-item status-meta"><span>Publish status</span>{status_badge(rec.get('status'))}</div>
    </section>'''

def page_header(eyebrow, title, desc='', actions=''):
    return f'''<section class="page-header">
        <div><em>{esc(eyebrow)}</em><h1>{esc(title)}</h1>{f'<p>{esc(desc)}</p>' if desc else ''}</div>
        {f'<div class="page-actions">{actions}</div>' if actions else ''}
    </section>'''

def empty_state(title, desc, action=''):
    return f'<article class="empty-state polished-empty"><h3>{esc(title)}</h3><p>{esc(desc)}</p>{action}</article>'

def latest_brief(s,q,msg=''):
    rec = selected_brief(q,s)
    rs = rows_for_brief(rec)
    view = q.get('view',['cards'])[0]
    selected = q.get('selected',[''])[0]
    strong = sorted([r for r in rs if r.get('Signal Type')=='Strong Market Signal'], key=lambda r:-sf(r.get('SG Gross Revenue')))
    emerging = sorted([r for r in rs if r.get('Signal Type')!='Strong Market Signal'], key=lambda r:(-sf(r.get('SG Gross Revenue')),best_rank_strength(r),r.get('Release Date','')))
    detail = detail_panel(selected,rs)
    actions = '<a class="btn primary" href="/export/print.html">Print Report</a><a class="btn" href="/export/executive.csv">Export CSV</a>'
    headline = f'{len(rs)} launches are included in this brief: {len(strong)} strong market signal{"s" if len(strong)!=1 else ""} and {len(emerging)} emerging signal{"s" if len(emerging)!=1 else ""}.'
    page = f'''{page_header('Market Brief','Singapore Gaming Market',headline,actions)}
        {context_strip(rec,s)}
        {brief_selector_widget(rec)}
        {top_cards(rs)}
        <section class="brief-section executive-section">
          <div class="section-heading"><div><h2>Executive Summary</h2><p>What changed, why it matters, and where to focus first.</p></div></div>
          <ul class="executive-bullets">{executive_summary_bullets(rs)}</ul>
        </section>
        {global_announcement_cards(rs)}
        {released_games_section(strong,emerging,view)}
        {local_trends_section(rs)}
        {watchlist_section(rs)}
        <details class="methodology"><summary>Methodology and data notes</summary><p>Released Games in Singapore uses Sensor Tower-derived Singapore launch and SEA6 performance data where available. Global Game Announcements are lightweight news highlights and do not use Sensor Tower performance metrics. Revenue is shown as estimated gross revenue. Analyst evidence is available through details, exports, or Admin Console.</p><p><a href="{AI_NEWS_RADAR_URL}" target="_blank" rel="noopener">Open AI News Radar</a></p></details>'''
    return f'<div class="detail-layout"><div>{page}</div>{detail}</div>' if detail else page

def historical_briefs(s,q,msg=''):
    recs = brief_records()
    cards = ''
    for rec in recs:
        rs = rows_for_brief(rec)
        strong = [r for r in rs if r.get('Signal Type')=='Strong Market Signal']
        emerging = [r for r in rs if r.get('Signal Type')!='Strong Market Signal']
        leader = max(strong or rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
        highlights = ''.join([
            f'<li>{len(rs)} included launch records</li>',
            f'<li>{len(strong)} Strong Market Signal{"s" if len(strong)!=1 else ""} · {len(emerging)} Emerging Market Signal{"s" if len(emerging)!=1 else ""}</li>',
            f'<li>Top title: {esc(display_name(leader)) if leader else "Unavailable"}</li>'
        ])
        cards += f'''<article class="archive-card reading-card">
          <div class="archive-main"><small>{esc(rec.get('type'))}</small><h3>{esc(clean_period(rec))}</h3><p>Meeting {esc(nd(rec.get('meeting')) or 'Unavailable')}</p></div>
          <div class="archive-status">{status_badge(rec.get('status'))}</div>
          <ul class="archive-highlights">{highlights}</ul>
          <a class="btn primary" href="/latest-brief?brief={urllib.parse.quote(rec['id'])}">Open full brief</a>
        </article>'''
    month = '<select aria-label="Filter by month"><option>All months</option><option>January</option><option>February</option><option>March</option><option>April</option><option>May</option><option>June</option><option>July</option></select>'
    year = '<select aria-label="Filter by year"><option>All years</option><option>2026</option><option>2025</option></select>'
    filters = f'<div class="archive-toolbar"><a class="btn primary" href="/latest-brief">Latest</a><a class="btn" href="/historical-briefs">Previous Brief</a>{month}{year}<input aria-label="Search briefs" placeholder="Search briefs"></div>'
    return f'''{page_header('Brief Archive','Historical Briefs','Open past market briefs by reporting period. This is the reading archive, not the meeting schedule.')}
        {filters}
        <div class="archive-grid">{cards or empty_state('No historical briefs yet','Published or archived briefs will appear here after finalisation.')}</div>'''

def market_timeline(s,q,msg=''):
    recs = brief_records()
    cur = recs[0]
    p = period(s)
    md = pdate(cur.get('meeting')) or date.today()
    months = ''.join(f'<option value="{i}" {"selected" if i==md.month else ""}>{datetime(2026,i,1).strftime("%B")}</option>' for i in range(1,13))
    years = ''.join(f'<option {"selected" if y==md.year else ""}>{y}</option>' for y in range(2025,2028))
    items = ''
    for rec in recs:
        items += f'''<article class="timeline-item">
            <div class="timeline-date"><span>Meeting</span><b>{esc(nd(rec.get('meeting')) or 'Unavailable')}</b></div>
            <div class="timeline-detail"><h3>{esc(clean_period(rec))}</h3><p>Reporting window for this meeting.</p></div>
            <div>{status_badge(rec.get('status'))}</div>
            <a class="btn ghost" href="/latest-brief?brief={urllib.parse.quote(rec['id'])}">Open brief</a>
        </article>'''
    rhythm = f'''<section class="rhythm-panel">
        <h2>Selected reporting window</h2>
        <div class="rhythm-steps">
          {meta_item('Report start', nd(cur.get('start')))}
          {meta_item('Report end', nd(cur.get('end')))}
          {meta_item('Meeting date', nd(cur.get('meeting')))}
          {meta_item('Data as of', nd(p.get('effective')))}
        </div>
    </section>'''
    controls = f'<section class="calendar-controls"><button>Previous Month</button><select aria-label="Month">{months}</select><select aria-label="Year">{years}</select><button>Next Month</button><a class="btn" href="/market-timeline">Current month</a></section>'
    return f'''{page_header('Market Timeline','Schedule and Reporting Windows','See meeting dates, reporting windows, data-as-of timing, and publishing status.')}
        {controls}
        <section class="timeline-shell"><div class="timeline-list">{items or empty_state('No meetings found','No meeting records are available for the selected month.')}</div>{rhythm}</section>'''

def trends_insights(s,q,msg=''):
    rs = reader_rows(); total=sum(sf(r.get('SG Gross Revenue')) for r in rs)
    strong=[r for r in rs if r.get('Signal Type')=='Strong Market Signal']; pubs={}; genres={}; platforms={}
    for r in rs:
        pubs[r.get('Publisher') or 'Unknown']=pubs.get(r.get('Publisher') or 'Unknown',0)+1
        platforms[r.get('Platform') or 'Unknown']=platforms.get(r.get('Platform') or 'Unknown',0)+1
        for g in re.split(r';|,',r.get('Genre','') or ''):
            g=g.strip()
            if g: genres[g]=genres.get(g,0)+1
    def insight(title,d,desc):
        lis=''.join(f'<li><b>{esc(k)}</b><span>{v} signal(s)</span></li>' for k,v in sorted(d.items(),key=lambda x:-x[1])[:6]) or '<li>Not enough data yet.</li>'
        return f'<article class="insight-card"><h3>{esc(title)}</h3><p>{esc(desc)}</p><ul>{lis}</ul></article>'
    return f'''{page_header('Trends / Insights','Market Patterns','A concise pattern view from the available brief data.')}
        <section class="summary-card-grid compact-summary"><article class="summary-card"><small>Included launches</small><h3>{len(rs)}</h3><p>Current brief data set.</p></article><article class="summary-card"><small>Strong signals</small><h3>{len(strong)}</h3><p>Commercial traction visible.</p></article><article class="summary-card"><small>Estimated SG gross revenue</small><h3>{money(total)}</h3><p>Included launches only.</p></article></section>
        <div class="insight-grid">{insight('Genre trends',genres,'Repeated genre patterns in the selected brief.')}{insight('Publisher activity',pubs,'Publishers with multiple detected records.')}{insight('Platform trends',platforms,'Platform mix across included launches.')}</div>'''

def admin_console(s,q,msg=''):
    if current_access_role(s)!='Admin':
        return page_header('Admin Console','Restricted area','This area is for editors, reviewers, and admins. Published briefs remain available from Latest Brief and Historical Briefs.')
    p=period(s); allrs=source_rows(True); hidden=[r for r in allrs if not brief_included(r)]
    stages=''.join(f'<li>{esc(x)}</li>' for x in ['Retrieve SG ranking candidates','Resolve app identities','Fetch metadata','Fetch SEA6 performance','Build brief and review queue'])
    return f'''{page_header('Admin Console','Editor and Publishing Workspace','Behind-the-scenes controls stay here so the executive brief remains clean.')}
        {('<div class="toast">'+esc(msg)+'</div>') if msg else ''}
        <div class="admin-grid">
          <section class="admin-card"><h2>Reporting Period Management</h2><div class="admin-meta">{meta_item('Current period', f"{nd(p['start'])}–{nd(p['end'])}")}{meta_item('Meeting date', nd(p['meeting']))}{meta_item('Status', s.get('report_status'))}</div><form method="post" action="/preview-date-change"><label>Upcoming meeting date</label><input type="date" name="meeting_date" value="{esc(p['meeting'])}"><button>Preview date change</button></form></section>
          <section class="admin-card"><h2>Run Market Scan</h2><p>Runs the existing local Sensor Tower workflow. Token/configuration values are never displayed here.</p><ol>{stages}</ol><form method="post" action="/run-scan"><button class="primary">Run Market Scan</button></form></section>
          <section class="admin-card"><h2>Brief Editor</h2><p>Use this workspace to prepare executive summary, section notes, follow-up notes, and source links in future editorial passes.</p><a class="btn" href="/game-tracker">Open Game Tracker</a></section>
          <section class="admin-card"><h2>Review & Publish</h2><form method="post" action="/set-report-status"><select name="status"><option>Draft</option><option>Review Required</option><option>Ready</option><option>Finalised</option><option>Archived</option></select><button>Update Status</button></form><p>Finalised snapshots are stored separately and should not be silently recomputed.</p></section>
          <section class="admin-card"><h2>Game Entry Editor</h2><p>{len(allrs)} total launch records · {len(hidden)} hidden from Market Brief. Use this area for curation, manual English titles, notes, and source attachment.</p><a class="btn" href="/export/full.csv">Export full analyst dataset</a></section>
          <details class="admin-card"><summary>Diagnostics and Evidence</summary><p>Output folder: data/output</p><div class="action-row"><a class="btn" href="/export/workflow-decisions.csv">Workflow decisions</a><a class="btn" href="/export/admin.csv">Override history</a><a class="btn" href="/export/title-normalisation.csv">Title normalisation</a></div></details>
        </div>'''

market = latest_brief
calendar_page = market_timeline
data_export = historical_briefs
admin_page = admin_console

def layout(path,s,content):
    canonical=ROUTE_ALIASES.get(path,path)
    nav=''.join(f'<a class="{ "on" if canonical==href else "" }" href="{href}" title="{esc(desc)}"><span>{esc(label)}</span><small>{esc(desc)}</small></a>' for href,label,desc in NAV_ITEMS)
    p=period(s)
    active_name=next((label for href,label,desc in NAV_ITEMS if href==canonical),'Latest Brief')
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IBD Market Intelligence</title><style>{CSS}</style></head><body><div class="app-shell"><aside class="sidebar"><div class="brand"><h1>IBD Market Intelligence</h1><p>Singapore · Mobile Launch Discovery</p><span>Proof of Concept</span></div><nav aria-label="Primary navigation">{nav}</nav><div class="sidebar-note">Executive view first. Editor controls stay in Admin Console.</div></aside><div class="workspace"><header class="topbar compact-topbar"><div class="topbar-title"><small>Current view</small><b>{esc(active_name)}</b></div><div><small>Period</small><b>{esc(nd(p['start']))}–{esc(nd(p['end']))}</b></div><div><small>Meeting</small><b>{esc(nd(p['meeting']))}</b></div><div><small>Status</small>{status_badge(s.get('report_status','Draft'))}</div><div class="top-actions"><a class="btn" href="/historical-briefs">Previous briefs</a><a class="btn primary" href="/latest-brief">Latest Brief</a></div></header><main>{content}</main></div></div><script>{JS}</script></body></html>'''



# Frontend polish follow-up: make one-brief archive and sparse timeline states look intentional.
def historical_briefs(s,q,msg=''):
    recs = brief_records()
    cards = ''
    for rec in recs:
        rs = rows_for_brief(rec)
        strong = [r for r in rs if r.get('Signal Type')=='Strong Market Signal']
        emerging = [r for r in rs if r.get('Signal Type')!='Strong Market Signal']
        leader = max(strong or rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
        highlights = ''.join([
            f'<li>{len(rs)} included launch records</li>',
            f'<li>{len(strong)} Strong Market Signal{"s" if len(strong)!=1 else ""} · {len(emerging)} Emerging Market Signal{"s" if len(emerging)!=1 else ""}</li>',
            f'<li>Top title: {esc(display_name(leader)) if leader else "Unavailable"}</li>'
        ])
        cards += f'''<article class="archive-card reading-card">
          <div class="archive-main"><small>{esc(rec.get('type'))}</small><h3>{esc(clean_period(rec))}</h3><p>Meeting {esc(nd(rec.get('meeting')) or 'Unavailable')}</p></div>
          <div class="archive-status">{status_badge(rec.get('status'))}</div>
          <ul class="archive-highlights">{highlights}</ul>
          <a class="btn primary" href="/latest-brief?brief={urllib.parse.quote(rec['id'])}">Open full brief</a>
        </article>'''
    if len(recs) <= 1:
        cards += empty_state('Archive will grow over time','Finalised portal briefs and imported legacy briefs will appear here. For now, use Latest Brief for the current report.')
    filters = '<div class="archive-toolbar"><a class="btn primary" href="/latest-brief">Latest</a><a class="btn" href="/historical-briefs">Previous Brief</a><select aria-label="Filter by month"><option>All months</option></select><select aria-label="Filter by year"><option>All years</option><option>2026</option></select><input aria-label="Search briefs" placeholder="Search briefs"></div>'
    return f'''{page_header('Brief Archive','Historical Briefs','Open past market briefs by reporting period. This is the reading archive, not the meeting schedule.')}
        {filters}
        <div class="archive-grid">{cards or empty_state('No historical briefs yet','Published or archived briefs will appear here after finalisation.')}</div>'''



# -----------------------------------------------------------------------------
# Frontend structure refactor
# -----------------------------------------------------------------------------
# Active rendering now uses templates/base.html, static/dashboard.css,
# static/dashboard.js, and reusable helpers from scripts/dashboard_components.py.
import mimetypes
import dashboard_components as ui

def status_badge(text): return ui.status_badge(text)
def meta_item(label, value): return ui.meta_item(label, value)
def page_header(eyebrow, title, desc='', actions=''): return ui.page_header(eyebrow, title, desc, actions)
def empty_state(title, desc, action=''): return ui.empty_state(title, desc, action)

def layout(path,s,content):
    canonical = ROUTE_ALIASES.get(path,path)
    nav = ''.join(ui.nav_link(href,label,desc,canonical==href) for href,label,desc in NAV_ITEMS)
    p = period(s)
    active_name = next((label for href,label,desc in NAV_ITEMS if href==canonical),'Latest Brief')
    topbar = f'''<header class="topbar compact-topbar">
      <div class="topbar-title"><small>Current view</small><b>{esc(active_name)}</b></div>
      <div><small>Period</small><b>{esc(nd(p['start']))}–{esc(nd(p['end']))}</b></div>
      <div><small>Meeting</small><b>{esc(nd(p['meeting']))}</b></div>
      <div><small>Status</small>{status_badge(s.get('report_status','Draft'))}</div>
      <div class="top-actions"><a class="btn" href="/historical-briefs">Previous briefs</a><a class="btn primary" href="/latest-brief">Latest Brief</a></div>
    </header>'''
    return ui.render_template(ROOT/'templates'/'base.html', title='IBD Market Intelligence', nav=nav, topbar=topbar, content=content)



# -----------------------------------------------------------------------------
# Latest Brief focused content/readability pass
# -----------------------------------------------------------------------------
# Removes unsupported strategic cards from Latest Brief and keeps local released
# games readable in both card and compact table views.

def display_date(value):
    d = pdate(value)
    return d.strftime('%d %b %Y') if d else ''

def display_date_range(start_value, end_value):
    s = pdate(start_value)
    e = pdate(end_value)
    if not s and not e:
        return 'Period unavailable'
    if s and not e:
        return display_date(start_value)
    if e and not s:
        return display_date(end_value)
    if s.year == e.year:
        return f"{s.strftime('%d %b')} - {e.strftime('%d %b %Y')}"
    return f"{s.strftime('%d %b %Y')} - {e.strftime('%d %b %Y')}"

def clean_period(rec):
    return display_date_range(rec.get('start'), rec.get('end'))

def brief_title(rec):
    return f"{clean_period(rec)} · Meeting {display_date(rec.get('meeting')) or 'Unavailable'} · {rec.get('type','Brief')}"

def context_strip(rec, s=None):
    p = period(s or state())
    return f'''<section class="context-strip" aria-label="Brief context">
        {meta_item('Reporting period', clean_period(rec))}
        {meta_item('Meeting date', display_date(rec.get('meeting')))}
        {meta_item('Data as of', display_date(p.get('effective')))}
        <div class="meta-item status-meta"><span>Publish status</span>{status_badge(rec.get('status'))}</div>
    </section>'''

def short_signal_label(r):
    label = signal_label(r)
    return 'Strong' if 'Strong' in label else 'Emerging'

def compact_number(value):
    try:
        n = float(str(value or 0).replace(',','').replace('$',''))
    except ValueError:
        return 'N/A'
    if n >= 1_000_000: return f'${n/1_000_000:.1f}M'
    if n >= 1_000: return f'${n/1_000:.1f}K'
    return f'${n:,.0f}'

def compact_downloads(value):
    try:
        n = int(float(str(value or 0).replace(',','')))
    except ValueError:
        return 'N/A'
    if n >= 1_000_000: return f'{n/1_000_000:.1f}M downloads'
    if n >= 1_000: return f'{n/1_000:.1f}K downloads'
    return f'{n:,} downloads'

def market_entries(r):
    raw=(r.get('Top 3 Markets') or '').replace('Top Mkts:','').strip().rstrip('.')
    entries=[]
    for part in [p.strip() for p in raw.split('||') if p.strip()]:
        m=re.match(r'([A-Z]{2}) \(\$([0-9,]+) / ([0-9,]+) DL\)',part)
        if m:
            entries.append({'country':m.group(1),'revenue':float(m.group(2).replace(',','')),'downloads':int(m.group(3).replace(',',''))})
    return entries

def market_chips(r):
    entries = market_entries(r)
    if not entries:
        return '<div class="market-chip-row"><span class="market-chip empty">N/A</span></div>'
    chips = ''
    for i,e in enumerate(entries[:4],1):
        sg = ' sg-market' if e['country']=='SG' else ''
        ref = ' title="SG included for local reference"' if e['country']=='SG' and i > 3 else ''
        chips += f'''<span class="market-chip{sg}"{ref}>
            <small>#{i} {esc(e['country'])}</small>
            <b title="{money(e['revenue'])} gross revenue">{compact_number(e['revenue'])} gross</b>
            <em title="{e['downloads']:,} downloads">{compact_downloads(e['downloads'])}</em>
        </span>'''
    return f'<div class="market-chip-row">{chips}</div>'

def table_market_cell(r):
    entries = market_entries(r)
    if not entries:
        return '<span class="table-market-empty">N/A</span>'
    parts = ''
    for e in entries[:4]:
        sg = ' sg-market' if e['country']=='SG' else ''
        parts += f'''<span class="table-market-chip{sg}">
          <b>{esc(e['country'])}</b>
          <span>{compact_number(e['revenue'])} gross</span>
          <small>{compact_downloads(e['downloads'])}</small>
        </span>'''
    return f'<div class="table-market-list">{parts}</div>'

def signal_badge_for_row(r):
    kind = 'strong' if r.get('Signal Type')=='Strong Market Signal' else 'emerging'
    return f'<span class="signal-pill {kind} short-signal">{short_signal_label(r)}</span>'

def signal_card(r,kind='strong'):
    dl,rev=rank_pair_values(r.get('SG App Store Ranks'))
    href=f'/latest-brief?selected={urllib.parse.quote(str(r.get("_uid","")))}'
    return f'''<a class="signal-card {kind}" href="{href}">
      <div class="signal-card-top"><span>{signal_badge_for_row(r)}</span><span class="view-link">View Details</span></div>
      <h3>{esc(display_name(r))}</h3>
      <p class="publisher-line">{esc(r.get('Publisher') or 'Publisher unavailable')}</p>
      <p class="meta-line">{esc(r.get('Platform') or 'Platform unavailable')} · {esc(r.get('Genre') or 'Genre unavailable')} · Released {esc(display_date(r.get('Release Date')) or 'Unavailable')}</p>
      <div class="primary-money"><b>{money(r.get('SG Gross Revenue'))}</b><span>Estimated gross revenue in Singapore</span></div>
      <div class="support-row"><span><b>{sg_downloads_value(r):,}</b><small>Downloads</small></span><span><b>{rank_text(dl)}</b><small>Top Free rank</small></span><span><b>{rank_text(rev)}</b><small>Top Grossing rank</small></span></div>
      <div class="market-title">Top SEA6 Markets</div>{market_chips(r)}
    </a>'''

def compact_public_table(rs):
    body=''
    for r in rs:
        dl,rev=rank_pair_values(r.get('SG App Store Ranks'))
        body += f'''<tr>
          <td><b>{esc(display_name(r))}</b><small>{esc(r.get('Publisher') or '')}</small></td>
          <td>{signal_badge_for_row(r)}</td>
          <td class="num">{money(r.get('SG Gross Revenue'))}</td>
          <td class="num">{sg_downloads_value(r):,}</td>
          <td class="rank-cell"><span>Free {rank_text(dl)}</span><span>Grossing {rank_text(rev)}</span></td>
          <td>{table_market_cell(r)}</td>
        </tr>'''
    return f'''<div class="data-table released-table"><table>
      <thead><tr><th>Game</th><th>Signal</th><th class="num">Revenue</th><th class="num">Downloads</th><th>Rank</th><th>Top SEA6 Markets</th></tr></thead>
      <tbody>{body or '<tr><td colspan="6">N/A</td></tr>'}</tbody>
    </table></div>'''

def released_games_section(strong,emerging,view):
    active_cards = 'on' if view != 'table' else ''
    active_table = 'on' if view == 'table' else ''
    toggle = f'<div class="view-toggle" aria-label="Released games view"><a class="{active_cards}" href="/latest-brief?view=cards">Card view</a><a class="{active_table}" href="/latest-brief?view=table">Compact table</a></div>'
    if view == 'table':
        return f'''<section class="brief-section released-games-section">
          <div class="section-heading"><div><h2>Released Games in Singapore</h2><p>Local release performance with Sensor Tower-supported revenue, downloads, ranks, and SEA6 market context.</p></div>{toggle}</div>
          {compact_public_table(strong+emerging)}
        </section>'''
    strong_html=''.join(signal_card(r,'strong') for r in strong) or '<article class="empty-state"><h3>No Strong signals yet.</h3><p>No launch exceeded the Singapore revenue threshold for this period.</p></article>'
    emerging_html=''.join(signal_card(r,'emerging') for r in emerging) or '<article class="empty-state"><h3>No Emerging signals yet.</h3><p>No additional Singapore launches are included in this brief.</p></article>'
    return f'''<section class="brief-section released-games-section">
      <div class="section-heading"><div><h2>Released Games in Singapore</h2><p>Local release performance with Sensor Tower-supported revenue, downloads, ranks, and SEA6 market context.</p></div>{toggle}</div>
      <h3 class="signal-heading strong-heading">Strong <span>Commercial traction is visible in Singapore.</span></h3>
      <div class="signal-grid strong-grid">{strong_html}</div>
      <h3 class="signal-heading emerging-heading">Emerging <span>New launches worth monitoring as evidence develops.</span></h3>
      <div class="signal-grid emerging-grid">{emerging_html}</div>
    </section>'''

def latest_brief(s,q,msg=''):
    rec = selected_brief(q,s)
    rs = rows_for_brief(rec)
    view = q.get('view',['cards'])[0]
    selected = q.get('selected',[''])[0]
    strong = sorted([r for r in rs if r.get('Signal Type')=='Strong Market Signal'], key=lambda r:-sf(r.get('SG Gross Revenue')))
    emerging = sorted([r for r in rs if r.get('Signal Type')!='Strong Market Signal'], key=lambda r:(-sf(r.get('SG Gross Revenue')),best_rank_strength(r),r.get('Release Date','')))
    detail = detail_panel(selected,rs)
    actions = '<a class="btn primary" href="/export/print.html">Print Report</a><a class="btn" href="/export/executive.csv">Export CSV</a>'
    headline = f'{len(rs)} launches are included in this brief: {len(strong)} strong signal{"s" if len(strong)!=1 else ""} and {len(emerging)} emerging signal{"s" if len(emerging)!=1 else ""}.'
    page = f'''{page_header('Market Brief','Singapore Gaming Market',headline,actions)}
        {context_strip(rec,s)}
        {brief_selector_widget(rec)}
        <section class="brief-section executive-section">
          <div class="section-heading"><div><h2>Executive Summary</h2><p>Factual updates and notable market observations for this reporting period.</p></div></div>
          <ul class="executive-bullets">{executive_summary_bullets(rs)}</ul>
        </section>
        {global_announcement_cards(rs)}
        {released_games_section(strong,emerging,view)}
        {local_trends_section(rs)}
        <details class="methodology"><summary>Methodology and data notes</summary><p>Released Games in Singapore uses Sensor Tower-derived Singapore launch and SEA6 performance data where available. Global Game Announcements are lightweight news highlights and do not use Sensor Tower performance metrics. Revenue is shown as estimated gross revenue. Analyst evidence is available through details, exports, or Admin Console.</p><p><a href="{AI_NEWS_RADAR_URL}" target="_blank" rel="noopener">Open AI News Radar</a></p></details>'''
    return f'<div class="detail-layout"><div>{page}</div>{detail}</div>' if detail else page

market = latest_brief



# Shared date display fix: visible dates use spaces; ranges use " - ".
def layout(path,s,content):
    canonical = ROUTE_ALIASES.get(path,path)
    nav = ''.join(ui.nav_link(href,label,desc,canonical==href) for href,label,desc in NAV_ITEMS)
    p = period(s)
    active_name = next((label for href,label,desc in NAV_ITEMS if href==canonical),'Latest Brief')
    topbar = f'''<header class="topbar compact-topbar">
      <div class="topbar-title"><small>Current view</small><b>{esc(active_name)}</b></div>
      <div><small>Period</small><b>{esc(display_date_range(p['start'], p['end']))}</b></div>
      <div><small>Meeting</small><b>{esc(display_date(p['meeting']))}</b></div>
      <div><small>Status</small>{status_badge(s.get('report_status','Draft'))}</div>
      <div class="top-actions"><a class="btn" href="/historical-briefs">Previous briefs</a><a class="btn primary" href="/latest-brief">Latest Brief</a></div>
    </header>'''
    return ui.render_template(ROOT/'templates'/'base.html', title='IBD Market Intelligence', nav=nav, topbar=topbar, content=content)



# Brief selector date display fix.
def brief_selector_widget(rec):
    recent = ''.join(
        f'<a class="brief-choice {"active" if b["id"]==rec["id"] else ""}" href="/latest-brief?brief={urllib.parse.quote(b["id"])}"><b>{esc(clean_period(b))}</b><span>{esc(display_date(b.get("meeting")) or "Meeting unavailable")} · {esc(b.get("type"))} · {esc(b.get("status"))}</span></a>'
        for b in brief_records()[:8]
    )
    return f'<details class="period-selector"><summary><span>Selected brief</span><b>{esc(brief_title(rec))}</b></summary><div class="selector-panel"><h3>Select Market Brief</h3><div class="selector-actions"><a class="btn primary" href="/latest-brief">Latest</a><a class="btn" href="/historical-briefs">Browse all historical briefs</a></div><div class="brief-choice-list">{recent}</div></div></details>'



# -----------------------------------------------------------------------------
# Official live brief stabilisation pass
# -----------------------------------------------------------------------------
# Public pages are treated as the official live brief. Draft/publish workflow
# language is limited to Admin Console, while public sections remain factual.

PUBLIC_NAV_ITEMS = [
    ('/latest-brief', 'Latest Brief', 'Read the current executive market update.'),
    ('/historical-briefs', 'Historical Briefs', 'Open previous reporting-period briefs.'),
    ('/game-tracker', 'Game Tracker', 'Review games mentioned across briefs.'),
    ('/market-timeline', 'Market Timeline', 'Understand meeting dates and reporting windows.'),
]

def visible_nav_items(s):
    items = list(PUBLIC_NAV_ITEMS)
    if current_access_role(s) == 'Admin':
        items.append(('/admin', 'Admin Console', 'Manage corrections, scans, and evidence.'))
    return items

def clean_period(rec):
    return display_date_range(rec.get('start'), rec.get('end'))

def context_strip(rec, s=None):
    p = period(s or state())
    return f'''<section class="context-strip" aria-label="Brief context">
        {meta_item('Reporting period', clean_period(rec))}
        {meta_item('Meeting date', display_date(rec.get('meeting')))}
        {meta_item('Data as of', display_date(p.get('effective')))}
        {meta_item('Last updated', todaystamp())}
    </section>'''

def brief_title(rec):
    return f"{clean_period(rec)} · Meeting {display_date(rec.get('meeting')) or 'Unavailable'} · Live Brief"

def public_status_label(rec):
    return 'Live Brief'

def executive_summary_bullets(rs):
    total = len(rs)
    strong = [r for r in rs if r.get('Signal Type') == 'Strong Market Signal']
    emerging = [r for r in rs if r.get('Signal Type') != 'Strong Market Signal']
    released = [r for r in rs if r.get('Release Date')]
    publishers = {}
    genres = {}
    st_available = 0
    for r in rs:
        publishers[r.get('Publisher') or 'Unknown'] = publishers.get(r.get('Publisher') or 'Unknown', 0) + 1
        if sf(r.get('SG Gross Revenue')) > 0 or sg_downloads_value(r) > 0 or market_entries(r):
            st_available += 1
        for g in re.split(r';|,', r.get('Genre','') or ''):
            g = g.strip()
            if g:
                genres[g] = genres.get(g, 0) + 1
    bullets = [
        f"{len(released) or total} released games were tracked in Singapore during this reporting period.",
        f"{len(strong)} titles are classified as Strong and {len(emerging)} as Emerging based on available Singapore launch/performance evidence.",
    ]
    if publishers:
        counts = sorted(publishers.values(), reverse=True)
        if len(counts) > 1 and counts[0] == counts[-1]:
            bullets.append("Publisher activity was evenly distributed this period; no single publisher dominated released-game activity.")
        elif len(counts) > 1 and counts[0] > counts[1]:
            top = [p for p,c in publishers.items() if c == counts[0]]
            bullets.append(f"{', '.join(top[:2])} had the most listed release records this period, with {counts[0]} record(s).")
        else:
            bullets.append("No single publisher clearly dominated released-game activity this period.")
    if genres:
        top_count = max(genres.values())
        top_genres = [g for g,c in genres.items() if c == top_count]
        if top_count > 1 and len(top_genres) <= 3:
            bullets.append(f"{', '.join(top_genres)} appeared more than once among listed genres.")
        else:
            bullets.append("Genre distribution was mixed; no single genre clearly dominated the released-game list.")
    bullets.append(f"Sensor Tower-derived SEA6 market data is shown where available for released games; Global Game Announcements remain news highlights only.")
    return ''.join(f'<li>{esc(b)}</li>' for b in bullets[:5])

def platform_rank_values(text):
    text = text or ''
    def parse(platform):
        m = re.search(platform + r' \((.*?)\)', text, flags=re.I)
        if not m:
            return {'free': None, 'grossing': None}
        segment = m.group(1)
        dl = re.search(r'DL #([0-9]+|NA)', segment)
        rev = re.search(r'Rev #([0-9]+|NA)', segment)
        def val(match):
            if not match: return None
            x = match.group(1)
            return int(x) if str(x).isdigit() else None
        return {'free': val(dl), 'grossing': val(rev)}
    return {'ios': parse('iOS'), 'android': parse('Android')}

def rank_display(v):
    return f'#{v}' if v else 'N/A'

def store_ranks_block(r):
    ranks = platform_rank_values(r.get('SG App Store Ranks'))
    return f'''<div class="store-ranks">
        <div><b>iOS</b><span>Free {rank_display(ranks['ios']['free'])}</span><span>Grossing {rank_display(ranks['ios']['grossing'])}</span></div>
        <div><b>Android</b><span>Free {rank_display(ranks['android']['free'])}</span><span>Grossing {rank_display(ranks['android']['grossing'])}</span></div>
    </div>'''

def table_rank_cell(r, platform):
    ranks = platform_rank_values(r.get('SG App Store Ranks'))[platform]
    label = 'iOS' if platform == 'ios' else 'Android'
    return f'<div class="rank-platform"><b>{label}</b><span>Free {rank_display(ranks["free"])}</span><span>Grossing {rank_display(ranks["grossing"])}</span></div>'

def signal_card(r,kind='strong'):
    href=f'/latest-brief?selected={urllib.parse.quote(str(r.get("_uid","")))}'
    return f'''<a class="signal-card {kind}" href="{href}">
      <div class="signal-card-top"><span>{signal_badge_for_row(r)}</span><span class="view-link">View Details</span></div>
      <h3>{esc(display_name(r))}</h3>
      <p class="publisher-line">{esc(r.get('Publisher') or 'Publisher unavailable')}</p>
      <p class="meta-line">{esc(r.get('Platform') or 'Platform unavailable')} · {esc(r.get('Genre') or 'Genre unavailable')} · Released {esc(display_date(r.get('Release Date')) or 'Unavailable')}</p>
      <div class="primary-money"><b>{money(r.get('SG Gross Revenue'))}</b><span>Estimated gross revenue in Singapore</span></div>
      <div class="support-row"><span><b>{sg_downloads_value(r):,}</b><small>Downloads</small></span></div>
      <div class="market-title">Store Ranks</div>{store_ranks_block(r)}
      <div class="market-title">Top SEA6 Markets</div>{market_chips(r)}
    </a>'''

def compact_public_table(rs):
    body=''
    for r in rs:
        body += f'''<tr>
          <td><b>{esc(display_name(r))}</b><small>{esc(r.get('Publisher') or '')}</small></td>
          <td>{signal_badge_for_row(r)}</td>
          <td class="num">{money(r.get('SG Gross Revenue'))}</td>
          <td class="num">{sg_downloads_value(r):,}</td>
          <td>{table_rank_cell(r,'ios')}</td>
          <td>{table_rank_cell(r,'android')}</td>
          <td>{table_market_cell(r)}</td>
        </tr>'''
    return f'''<div class="data-table released-table"><table>
      <thead><tr><th>Game</th><th>Signal</th><th class="num">Revenue</th><th class="num">Downloads</th><th>iOS Rank</th><th>Android Rank</th><th>Top SEA6 Markets</th></tr></thead>
      <tbody>{body or '<tr><td colspan="7">N/A</td></tr>'}</tbody>
    </table></div>'''

def global_announcement_cards(rs):
    seen = set()
    supported=[]
    for r in source_rows(True):
        key = (r.get('Radar Matched Title') or display_name(r) or '').strip().lower()
        if not key or key in seen:
            continue
        if r.get('Radar URL') or r.get('Radar Matched Title') or r.get('Radar Source'):
            seen.add(key)
            supported.append(r)
    cards=''
    for r in supported[:4]:
        title=r.get('Radar Matched Title') or display_name(r)
        source=r.get('Radar Source') or 'AI News Radar'
        url=r.get('Radar URL') or AI_NEWS_RADAR_URL
        cards += f'''<article class="news-card">
            <span>News highlight</span>
            <h3>{esc(title)}</h3>
            <p>{esc(r.get('Publisher') or 'Publisher/developer unavailable')} · Source: {esc(source)}</p>
            <p>Global announcement/news item. Revenue, downloads, and store ranks are not used for this section.</p>
            <a href="{esc(url)}" target="_blank" rel="noopener">View source</a>
        </article>'''
    if not cards:
        cards=f'<article class="empty-state"><h3>No global announcement highlights attached yet.</h3><p>Relevant AI News Radar items can be attached when available.</p><a href="{AI_NEWS_RADAR_URL}" target="_blank" rel="noopener">Open AI News Radar</a></article>'
    return f'<section class="brief-section"><div class="section-heading"><h2>Global Game Announcements</h2><p>News highlights only; no Sensor Tower performance metrics are shown here.</p></div><div class="news-grid">{cards}</div></section>'

def latest_brief(s,q,msg=''):
    rec = selected_brief(q,s)
    rs = rows_for_brief(rec)
    view = q.get('view',['cards'])[0]
    selected = q.get('selected',[''])[0]
    strong = sorted([r for r in rs if r.get('Signal Type')=='Strong Market Signal'], key=lambda r:-sf(r.get('SG Gross Revenue')))
    emerging = sorted([r for r in rs if r.get('Signal Type')!='Strong Market Signal'], key=lambda r:(-sf(r.get('SG Gross Revenue')),best_rank_strength(r),r.get('Release Date','')))
    detail = detail_panel(selected,rs)
    actions = '<a class="btn primary" href="/export/print.html">Print Report</a><a class="btn" href="/export/executive.csv">Export CSV</a>'
    headline = f'{len(rs)} launches are included in this brief: {len(strong)} strong signal{"s" if len(strong)!=1 else ""} and {len(emerging)} emerging signal{"s" if len(emerging)!=1 else ""}.'
    page = f'''{page_header('Market Brief','Singapore Gaming Market',headline,actions)}
        {context_strip(rec,s)}
        {brief_selector_widget(rec)}
        <section class="brief-section executive-section">
          <div class="section-heading"><div><h2>Executive Summary</h2><p>Factual updates and notable market observations for this reporting period.</p></div></div>
          <ul class="executive-bullets">{executive_summary_bullets(rs)}</ul>
        </section>
        {global_announcement_cards(rs)}
        {released_games_section(strong,emerging,view)}
        {local_trends_section(rs)}
        <details class="methodology"><summary>Methodology and data notes</summary><p>Released Games in Singapore uses Sensor Tower-derived Singapore launch and SEA6 performance data where available. Global Game Announcements are lightweight news highlights and do not use Sensor Tower performance metrics. Revenue is shown as estimated gross revenue. Analyst evidence is available through details, exports, or Admin Console.</p><p><a href="{AI_NEWS_RADAR_URL}" target="_blank" rel="noopener">Open AI News Radar</a></p></details>'''
    return f'<div class="detail-layout"><div>{page}</div>{detail}</div>' if detail else page

def historical_briefs(s,q,msg=''):
    recs = brief_records()
    cards = ''
    for rec in recs:
        rs = rows_for_brief(rec)
        strong = [r for r in rs if r.get('Signal Type')=='Strong Market Signal']
        emerging = [r for r in rs if r.get('Signal Type')!='Strong Market Signal']
        leader = max(strong or rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
        highlights = ''.join([
            f'<li>{len(rs)} included launch records</li>',
            f'<li>{len(strong)} Strong signal{"s" if len(strong)!=1 else ""} · {len(emerging)} Emerging signal{"s" if len(emerging)!=1 else ""}</li>',
            f'<li>Top revenue title: {esc(display_name(leader)) if leader else "Unavailable"}</li>'
        ])
        cards += f'''<article class="archive-card reading-card">
          <div class="archive-main"><small>Market Brief</small><h3>{esc(clean_period(rec))}</h3><p>Meeting {esc(display_date(rec.get('meeting')) or 'Unavailable')}</p></div>
          <ul class="archive-highlights">{highlights}</ul>
          <a class="btn primary" href="/latest-brief?brief={urllib.parse.quote(rec['id'])}">Open full brief</a>
        </article>'''
    if len(recs) <= 1:
        cards += empty_state('Archive will grow over time','Finalised portal briefs and imported legacy briefs will appear here. For now, use Latest Brief for the current report.')
    filters = '<div class="archive-toolbar"><a class="btn primary" href="/latest-brief">Latest</a><a class="btn" href="/historical-briefs">Previous Brief</a><select aria-label="Filter by month"><option>All months</option></select><select aria-label="Filter by year"><option>All years</option><option>2026</option></select><input aria-label="Search briefs" placeholder="Search briefs"></div>'
    return f'''{page_header('Brief Archive','Historical Briefs','Open past market briefs by reporting period. This is the reading archive, not the meeting schedule.')}
        {filters}
        <div class="archive-grid">{cards or empty_state('No historical briefs yet','Historical briefs will appear here when available.')}</div>'''

def market_timeline(s,q,msg=''):
    recs = brief_records()
    cur = recs[0]
    p = period(s)
    md = pdate(cur.get('meeting')) or date.today()
    months = ''.join(f'<option value="{i}" {"selected" if i==md.month else ""}>{datetime(2026,i,1).strftime("%B")}</option>' for i in range(1,13))
    years = ''.join(f'<option {"selected" if y==md.year else ""}>{y}</option>' for y in range(2025,2028))
    items = ''
    for rec in recs:
        items += f'''<article class="timeline-item">
            <div class="timeline-date"><span>Meeting</span><b>{esc(display_date(rec.get('meeting')) or 'Unavailable')}</b></div>
            <div class="timeline-detail"><h3>{esc(clean_period(rec))}</h3><p>Reporting window for this meeting.</p></div>
            <a class="btn ghost" href="/latest-brief?brief={urllib.parse.quote(rec['id'])}">Open brief</a>
        </article>'''
    rhythm = f'''<section class="rhythm-panel">
        <h2>Selected reporting window</h2>
        <div class="rhythm-steps">
          {meta_item('Report start', display_date(cur.get('start')))}
          {meta_item('Report end', display_date(cur.get('end')))}
          {meta_item('Meeting date', display_date(cur.get('meeting')))}
          {meta_item('Data as of', display_date(p.get('effective')))}
        </div>
    </section>'''
    controls = f'<section class="calendar-controls"><button>Previous Month</button><select aria-label="Month">{months}</select><select aria-label="Year">{years}</select><button>Next Month</button><a class="btn" href="/market-timeline">Current month</a></section>'
    return f'''{page_header('Market Timeline','Schedule and Reporting Windows','See meeting dates, reporting windows, data-as-of timing, and brief timing.')}
        {controls}
        <section class="timeline-shell"><div class="timeline-list">{items or empty_state('No meetings found','No meeting records are available for the selected month.')}</div>{rhythm}</section>'''

def layout(path,s,content):
    canonical = ROUTE_ALIASES.get(path,path)
    nav = ''.join(ui.nav_link(href,label,desc,canonical==href) for href,label,desc in visible_nav_items(s))
    p = period(s)
    active_name = next((label for href,label,desc in visible_nav_items(s) if href==canonical),'Latest Brief')
    topbar = f'''<header class="topbar compact-topbar">
      <div class="topbar-title"><small>Current view</small><b>{esc(active_name)}</b></div>
      <div><small>Period</small><b>{esc(display_date_range(p['start'], p['end']))}</b></div>
      <div><small>Meeting</small><b>{esc(display_date(p['meeting']))}</b></div>
      <div><small>Data as of</small><b>{esc(display_date(p['effective']))}</b></div>
      <div class="top-actions"><a class="btn" href="/historical-briefs">Previous briefs</a><a class="btn primary" href="/latest-brief">Latest Brief</a></div>
    </header>'''
    return ui.render_template(ROOT/'templates'/'base.html', title='IBD Market Intelligence', nav=nav, topbar=topbar, content=content)

market = latest_brief
calendar_page = market_timeline
data_export = historical_briefs



# Public selector should show brief context, not draft/publish workflow status.
def brief_selector_widget(rec):
    recent = ''.join(
        f'<a class="brief-choice {"active" if b["id"]==rec["id"] else ""}" href="/latest-brief?brief={urllib.parse.quote(b["id"])}"><b>{esc(clean_period(b))}</b><span>{esc(display_date(b.get("meeting")) or "Meeting unavailable")} · Market Brief</span></a>'
        for b in brief_records()[:8]
    )
    return f'<details class="period-selector"><summary><span>Selected brief</span><b>{esc(brief_title(rec))}</b></summary><div class="selector-panel"><h3>Select Market Brief</h3><div class="selector-actions"><a class="btn primary" href="/latest-brief">Latest</a><a class="btn" href="/historical-briefs">Browse all historical briefs</a></div><div class="brief-choice-list">{recent}</div></div></details>'


# --- Key Details content-structure pass ---
# Keeps placeholder/news sections honest while making each item easy to swap to sourced copy later.
def key_details_text(r, section='released'):
    if section == 'global':
        detail = (r.get('Radar Summary') or r.get('Radar Key Details') or r.get('Key Details') or '').strip()
        return detail or 'Verified announcement details will be populated after source integration. This item is treated as a news highlight, not performance analysis.'
    if section == 'local':
        return 'Local industry context will be updated once the news source pipeline is connected. Current wording is limited to factual patterns available in the report data.'
    detail = (r.get('Approved Report Note') or r.get('Key Details') or r.get('Market Overview Reason') or '').strip()
    if detail:
        return detail
    release = display_date(r.get('Release Date')) or 'the selected reporting period'
    title = display_name(r) or 'This title'
    return f'{title} is included as a Singapore released-game item for {release}. Sensor Tower-derived SEA6 performance and store-rank evidence are shown where available.'

def key_details_box(text):
    return f'<div class="key-details"><strong>Key Details</strong><p>{esc(text or "Details pending source integration.")}</p></div>'

def signal_card(r,kind='strong'):
    href=f'/latest-brief?selected={urllib.parse.quote(str(r.get("_uid","")))}'
    return f'''<a class="signal-card {kind}" href="{href}">
      <div class="signal-card-top"><span>{signal_badge_for_row(r)}</span><span class="view-link">View Details</span></div>
      <h3>{esc(display_name(r))}</h3>
      <p class="publisher-line">{esc(r.get('Publisher') or 'Publisher unavailable')}</p>
      <p class="meta-line">{esc(r.get('Platform') or 'Platform unavailable')} · {esc(r.get('Genre') or 'Genre unavailable')} · Released {esc(display_date(r.get('Release Date')) or 'Unavailable')}</p>
      {key_details_box(key_details_text(r,'released'))}
      <div class="primary-money"><b>{money(r.get('SG Gross Revenue'))}</b><span>Estimated gross revenue in Singapore</span></div>
      <div class="support-row"><span><b>{sg_downloads_value(r):,}</b><small>Downloads</small></span></div>
      <div class="market-title">Store Ranks</div>{store_ranks_block(r)}
      <div class="market-title">Top SEA6 Markets</div>{market_chips(r)}
    </a>'''

def compact_public_table(rs):
    body=''
    for r in rs:
        body += f'''<tr>
          <td><b>{esc(display_name(r))}</b><small>{esc(r.get('Publisher') or '')}</small></td>
          <td>{signal_badge_for_row(r)}</td>
          <td>{esc(key_details_text(r,'released'))}</td>
          <td class="num">{money(r.get('SG Gross Revenue'))}</td>
          <td class="num">{sg_downloads_value(r):,}</td>
          <td>{table_rank_cell(r,'ios')}</td>
          <td>{table_rank_cell(r,'android')}</td>
          <td>{table_market_cell(r)}</td>
        </tr>'''
    return f'''<div class="data-table released-table"><table>
      <thead><tr><th>Game</th><th>Signal</th><th>Key Details</th><th class="num">Revenue</th><th class="num">Downloads</th><th>iOS Rank</th><th>Android Rank</th><th>Top SEA6 Markets</th></tr></thead>
      <tbody>{body or '<tr><td colspan="8">N/A</td></tr>'}</tbody>
    </table></div>'''

def global_announcement_cards(rs):
    seen = set()
    supported=[]
    for r in source_rows(True):
        key = (r.get('Radar Matched Title') or r.get('Radar Title') or display_name(r) or '').strip().lower()
        if not key or key in seen:
            continue
        if r.get('Radar URL') or r.get('Radar Matched Title') or r.get('Radar Source') or r.get('Radar Title'):
            seen.add(key)
            supported.append(r)
    cards=''
    for r in supported[:4]:
        title=r.get('Radar Matched Title') or r.get('Radar Title') or display_name(r)
        source=r.get('Radar Source') or 'AI News Radar'
        url=r.get('Radar URL') or AI_NEWS_RADAR_URL
        ann_type=r.get('Announcement Type') or r.get('Radar Category') or 'News highlight'
        cards += f'''<article class="news-card">
            <span>{esc(ann_type)}</span>
            <h3>{esc(title)}</h3>
            <p>{esc(r.get('Publisher') or 'Publisher/developer unavailable')} · Source: {esc(source)}</p>
            {key_details_box(key_details_text(r,'global'))}
            <p class="section-note">Revenue, downloads, and store ranks are not used for Global Game Announcements.</p>
            <a href="{esc(url)}" target="_blank" rel="noopener">View source</a>
        </article>'''
    if not cards:
        cards=f'''<article class="empty-state polished-empty">
            <h3>No global announcement highlights attached yet.</h3>
            {key_details_box('Details pending AI News Radar integration. Verified announcement details will appear here once the source pipeline is connected.')}
            <a href="{AI_NEWS_RADAR_URL}" target="_blank" rel="noopener">Open AI News Radar</a>
        </article>'''
    return f'<section class="brief-section"><div class="section-heading"><h2>Global Game Announcements</h2><p>News highlights only; no Sensor Tower performance metrics are shown here.</p></div><div class="news-grid">{cards}</div></section>'

def released_games_section(strong,emerging,view):
    toggle=f'<div class="view-toggle"><a class="{ "active" if view!="table" else "" }" href="/latest-brief?view=cards">Card view</a><a class="{ "active" if view=="table" else "" }" href="/latest-brief?view=table">Compact table</a></div>'
    if view=='table':
        return f'<section class="brief-section"><div class="section-heading"><div><h2>Released Games in Singapore</h2><p>Local performance section for released mobile games. Key Details are factual notes only.</p></div>{toggle}</div>{compact_public_table(strong+emerging)}</section>'
    strong_body=''.join(signal_card(r,'strong') for r in strong) or empty_state('No Strong releases in this brief','No released-game item currently exceeds the Strong signal threshold for Singapore.')
    emerging_body=''.join(signal_card(r,'emerging') for r in emerging) or empty_state('No Emerging releases in this brief','No Emerging released-game items are available for this reporting period.')
    return f'''<section class="brief-section"><div class="section-heading"><div><h2>Released Games in Singapore</h2><p>Local performance section for released mobile games. Key Details are factual notes only.</p></div>{toggle}</div>
        <div class="signal-heading"><h3>Strong</h3><span>Singapore gross revenue exceeded $1K during the release/report period.</span></div><div class="signal-grid">{strong_body}</div>
        <div class="signal-heading emerging-heading"><h3>Emerging</h3><span>New launches to monitor; commercial relevance is still developing.</span></div><div class="signal-grid emerging-grid">{emerging_body}</div>
    </section>'''

def local_trends_section(rs):
    def counts_for(field):
        out={}
        for r in rs:
            raw=r.get(field,'') or ''
            parts=re.split(r';|,| / ', raw) if field=='Genre' else [raw]
            for item in parts:
                item=item.strip()
                if item:
                    out[item]=out.get(item,0)+1
        return sorted(out.items(), key=lambda kv:(-kv[1],kv[0]))[:4]
    def factual_card(title, items, fallback):
        chips=''.join(f'<span class="trend-chip"><b>{esc(k)}</b><small>{v} record{"s" if v!=1 else ""}</small></span>' for k,v in items)
        return f'<article class="trend-card"><h3>{esc(title)}</h3>{key_details_box(fallback)}<div class="trend-chip-row">{chips or "<span class=\"muted\">N/A</span>"}</div></article>'
    genres=counts_for('Genre')
    pubs=counts_for('Publisher')
    platforms=counts_for('Platform')
    return f'''<section class="brief-section"><div class="section-heading"><h2>Local Market / Industry Updates</h2><p>Placeholder-ready section for local context. Current content is limited to factual patterns from released-game data.</p></div>
      <div class="trend-panel structured-trends">
        {factual_card('Genre mix', genres, 'Genre details are based on the released-game records currently included in this brief. Broader local industry context will be updated once the news source pipeline is connected.')}
        {factual_card('Publisher activity', pubs, 'Publisher details are counted from listed release records only. No strategic conclusion is implied unless supported by future source integration.')}
        {factual_card('Platform coverage', platforms, 'Platform coverage reflects available mobile app records in this proof of concept. Local industry context will be updated after source integration.')}
      </div>
    </section>'''

# --- Compact header density pass ---
def layout(path,s,content):
    canonical = ROUTE_ALIASES.get(path,path)
    nav = ''.join(ui.nav_link(href,label,desc,canonical==href) for href,label,desc in visible_nav_items(s))
    p = period(s)
    active_name = next((label for href,label,desc in visible_nav_items(s) if href==canonical),'Latest Brief')
    period_text = display_date_range(p.get('start'), p.get('end')) or 'Period unavailable'
    meeting_text = display_date(p.get('meeting')) or 'Unavailable'
    data_text = display_date(p.get('effective')) or 'Unavailable'
    topbar = f'''<header class="topbar compact-topbar slim-context-bar" aria-label="Brief context">
      <div class="inline-context"><b>{esc(active_name)}</b><span>Period: {esc(period_text)}</span><span>Meeting: {esc(meeting_text)}</span><span>Data as of: {esc(data_text)}</span></div>
      <div class="top-actions compact-actions"><a class="btn ghost" href="/historical-briefs">Previous Briefs</a><a class="btn primary" href="/latest-brief">Latest Brief</a></div>
    </header>'''
    return ui.render_template(ROOT/'templates'/'base.html', title='IBD Market Intelligence', nav=nav, topbar=topbar, content=content)

# The global header already carries period/meeting/data context, so the in-page
# brief context should stay subtle instead of repeating large metadata cards.
def context_strip(rec, s=None):
    return f'<p class="brief-context-line">Viewing {esc(clean_period(rec))} · Meeting {esc(display_date(rec.get("meeting")) or "Unavailable")}</p>'

# --- Remove duplicate Latest Brief context line ---
def context_strip(rec, s=None):
    return ''

# --- Interaction-state proof pass ---
# Adds visible cause-and-effect for selectors, filters, month/year controls, and period switching.
_real_brief_records_for_interaction = brief_records
_real_rows_for_brief_for_interaction = rows_for_brief

def _qone(q, key, default=''):
    return (q.get(key, [default]) or [default])[0]

def _query(path, params):
    clean = {k:v for k,v in params.items() if v not in ('', None, 'all')}
    return path + (('?' + urllib.parse.urlencode(clean)) if clean else '')

def _remove_param(path, q, remove):
    params = {k:_qone(q,k) for k in q.keys() if k not in remove}
    return _query(path, params)

def _month_name(m):
    try: return datetime(2026, int(m), 1).strftime('%B')
    except Exception: return 'Unknown month'

def _demo_rec(base, index, offset_days, label):
    start = pdate(base.get('start')) or date.today()
    end = pdate(base.get('end')) or start
    meeting = pdate(base.get('meeting')) or end + timedelta(days=1)
    return {
        'id': f'demo_{index}',
        'start': (start - timedelta(days=offset_days)).isoformat(),
        'end': (end - timedelta(days=offset_days)).isoformat(),
        'meeting': (meeting - timedelta(days=offset_days)).isoformat(),
        'type': label,
        'path': f'demo_{index}',
        'demo': True,
    }

def brief_records():
    recs = list(_real_brief_records_for_interaction())
    if recs and len(recs) < 3:
        base = recs[0]
        recs = recs + [_demo_rec(base, 1, 14, 'Demo Brief'), _demo_rec(base, 2, 28, 'Demo Brief')]
    return recs

def selected_brief(q,s):
    wanted = _qone(q, 'brief', 'current')
    recs = brief_records()
    return next((r for r in recs if r.get('id') == wanted), recs[0])

def rows_for_brief(rec):
    if rec.get('demo'):
        base = _real_rows_for_brief_for_interaction(_real_brief_records_for_interaction()[0])
        offset = 0 if rec.get('id') == 'demo_1' else 5
        demo = [dict(r) for r in base[offset:offset+8]] or [dict(r) for r in base[:6]]
        for r in demo:
            r['Signal Display'] = signal_label(r)
            r['_uid'] = uid(r) + '_' + rec.get('id','demo')
            r['Brief Demo Note'] = 'Demo/sample period for interaction testing only.'
        return demo
    return _real_rows_for_brief_for_interaction(rec)

def brief_type_label(rec):
    return 'Demo Brief' if rec.get('demo') else 'Live Brief'

def brief_title(rec):
    return f"{clean_period(rec)} · Meeting {display_date(rec.get('meeting')) or 'Unavailable'} · {brief_type_label(rec)}"

def result_bar(label, shown, total, extra=''):
    text = f'{shown} of {total} {label}' if shown != total else f'{shown} {label}'
    return f'<div class="result-state"><b>{esc(text)}</b>{("<span>"+esc(extra)+"</span>") if extra else ""}</div>'

def filter_chips(path, q, chips):
    rendered = ''.join(f'<a class="filter-chip" href="{esc(_remove_param(path, q, [key]))}">{esc(label)} <span>×</span></a>' for key,label in chips if label)
    return f'<div class="filter-chips"><span>Selected filters:</span>{rendered}<a class="clear-filters" href="{path}">Clear filters</a></div>' if rendered else ''

def layout(path,s,content):
    canonical = ROUTE_ALIASES.get(path,path)
    nav = ''.join(ui.nav_link(href,label,desc,canonical==href) for href,label,desc in visible_nav_items(s))
    p = period(s)
    active_name = next((label for href,label,desc in visible_nav_items(s) if href==canonical),'Latest Brief')
    recs = brief_records()
    prev = recs[1] if len(recs) > 1 else None
    prev_btn = f'<a class="btn ghost" href="/latest-brief?brief={urllib.parse.quote(prev["id"])}">Previous Brief</a>' if prev else '<button class="btn ghost" disabled title="No previous brief is available yet">Previous Brief</button>'
    topbar = f'''<header class="topbar compact-topbar slim-context-bar" aria-label="Brief context">
      <div class="inline-context"><b>{esc(active_name)}</b><span>Period: {esc(display_date_range(p.get('start'), p.get('end')) or 'Unavailable')}</span><span>Meeting: {esc(display_date(p.get('meeting')) or 'Unavailable')}</span><span>Data as of: {esc(display_date(p.get('effective')) or 'Unavailable')}</span></div>
      <div class="top-actions compact-actions">{prev_btn}<a class="btn primary" href="/latest-brief">Latest Brief</a></div>
    </header>'''
    return ui.render_template(ROOT/'templates'/'base.html', title='IBD Market Intelligence', nav=nav, topbar=topbar, content=content)

def context_strip(rec, s=None):
    return ''

def brief_selector_widget(rec):
    recs = brief_records()
    recent = ''.join(
        f'<a class="brief-choice {"active" if b["id"]==rec["id"] else ""}" href="/latest-brief?brief={urllib.parse.quote(b["id"])}"><b>{esc(clean_period(b))}</b><span>{esc(display_date(b.get("meeting")) or "Meeting unavailable")} · {esc(brief_type_label(b))}</span></a>'
        for b in recs[:8]
    )
    return f'<details class="period-selector"><summary><span>Selected brief</span><b>{esc(brief_title(rec))}</b></summary><div class="selector-panel"><h3>Select Market Brief</h3><p class="control-help">Selecting a brief updates the summary, released games, metadata, and exports shown on this page.</p><div class="selector-actions"><a class="btn primary" href="/latest-brief">Latest</a><a class="btn" href="/historical-briefs">Browse all historical briefs</a></div><div class="brief-choice-list">{recent}</div></div></details>'

def released_games_section(strong,emerging,view):
    rec_id = globals().get('CURRENT_BRIEF_ID_FOR_UI', 'current')
    base = {'brief': rec_id} if rec_id != 'current' else {}
    card_href = _query('/latest-brief', {**base, 'view':'cards'})
    table_href = _query('/latest-brief', {**base, 'view':'table'})
    toggle=f'<div class="view-toggle" aria-label="Released games view"><a class="{ "active" if view!="table" else "" }" href="{esc(card_href)}" aria-current="{ "true" if view!="table" else "false" }">Card view</a><a class="{ "active" if view=="table" else "" }" href="{esc(table_href)}" aria-current="{ "true" if view=="table" else "false" }">Compact table</a></div>'
    count = len(strong) + len(emerging)
    count_line = result_bar('released game records', count, count, 'View changes between executive cards and comparison table.')
    if view=='table':
        return f'<section class="brief-section"><div class="section-heading"><div><h2>Released Games in Singapore</h2><p>Local performance section for released mobile games. Key Details are factual notes only.</p></div>{toggle}</div>{count_line}{compact_public_table(strong+emerging)}</section>'
    strong_body=''.join(signal_card(r,'strong') for r in strong) or empty_state('No Strong releases in this brief','No released-game item currently exceeds the Strong signal threshold for Singapore.')
    emerging_body=''.join(signal_card(r,'emerging') for r in emerging) or empty_state('No Emerging releases in this brief','No Emerging released-game items are available for this reporting period.')
    return f'''<section class="brief-section"><div class="section-heading"><div><h2>Released Games in Singapore</h2><p>Local performance section for released mobile games. Key Details are factual notes only.</p></div>{toggle}</div>{count_line}
        <div class="signal-heading"><h3>Strong</h3><span>{len(strong)} shown · Singapore gross revenue exceeded $1K during the release/report period.</span></div><div class="signal-grid">{strong_body}</div>
        <div class="signal-heading emerging-heading"><h3>Emerging</h3><span>{len(emerging)} shown · New launches to monitor; commercial relevance is still developing.</span></div><div class="signal-grid emerging-grid">{emerging_body}</div>
    </section>'''

def latest_brief(s,q,msg=''):
    rec = selected_brief(q,s)
    globals()['CURRENT_BRIEF_ID_FOR_UI'] = rec.get('id','current')
    rs = rows_for_brief(rec)
    view = _qone(q, 'view', 'cards')
    selected = _qone(q, 'selected', '')
    strong = sorted([r for r in rs if r.get('Signal Type')=='Strong Market Signal'], key=lambda r:-sf(r.get('SG Gross Revenue')))
    emerging = sorted([r for r in rs if r.get('Signal Type')!='Strong Market Signal'], key=lambda r:(-sf(r.get('SG Gross Revenue')),best_rank_strength(r),r.get('Release Date','')))
    detail = detail_panel(selected,rs)
    actions = '<a class="btn primary" href="/export/print.html">Print Report</a><a class="btn" href="/export/executive.csv">Export CSV</a>'
    headline = f'{len(rs)} launches are included in this brief: {len(strong)} strong signals and {len(emerging)} emerging signals.'
    demo_note = '<div class="state-note">Demo/sample period: this view reuses local records only to prove switching behavior.</div>' if rec.get('demo') else ''
    page = f'''{page_header('Market Brief','Singapore Gaming Market',headline,actions)}
        {brief_selector_widget(rec)}{demo_note}
        <section class="brief-section executive-section"><div class="section-heading"><div><h2>Executive Summary</h2><p>Factual updates and notable market observations for this reporting period.</p></div></div><ul class="executive-bullets">{executive_summary_bullets(rs)}</ul></section>
        {global_announcement_cards(rs)}{released_games_section(strong,emerging,view)}{local_trends_section(rs)}
        <details class="methodology"><summary>Methodology and data notes</summary><p>Released Games in Singapore uses Sensor Tower-derived Singapore launch and SEA6 performance data where available. Global Game Announcements are lightweight news highlights and do not use Sensor Tower performance metrics. Revenue is shown as estimated gross revenue. Analyst evidence is available through details, exports, or Admin Console.</p><p><a href="{AI_NEWS_RADAR_URL}" target="_blank" rel="noopener">Open AI News Radar</a></p></details>'''
    return f'<div class="detail-layout"><div>{page}</div>{detail}</div>' if detail else page

def mentioned_game_rows():
    combined = []
    seen = set()
    for r in rows() + source_rows(True):
        title = display_name(r)
        key = r.get('unified_app_id') or r.get('_uid') or title.lower()
        if not title or key in seen:
            continue
        seen.add(key)
        x = dict(r)
        x['_uid'] = x.get('_uid') or uid(x)
        x['Mention Type'] = 'Released game' if r in rows() or r.get('SG Gross Revenue') else 'News / brief mention'
        combined.append(x)
    return combined

def game_tracker(s,q,msg=''):
    all_rows = mentioned_game_rows()
    search=_qone(q,'q','').strip().lower(); signal=_qone(q,'signal','all'); platform=_qone(q,'platform','all'); publisher=_qone(q,'publisher','all')
    def match(r):
        hay=' '.join([display_name(r), r.get('Publisher',''), r.get('Genre',''), r.get('Platform',''), r.get('Mention Type',''), r.get('Radar Matched Title','')]).lower()
        if search and search not in hay: return False
        if signal!='all' and signal_label(r)!=signal: return False
        if platform!='all' and platform.lower() not in (r.get('Platform','') or '').lower(): return False
        if publisher!='all' and (r.get('Publisher') or '') != publisher: return False
        return True
    filtered=[r for r in all_rows if match(r)]
    signals=sorted({signal_label(r) for r in all_rows if signal_label(r)})
    platforms=sorted({p for r in all_rows for p in ['iOS','Android'] if p.lower() in (r.get('Platform','') or '').lower()}) or ['iOS','Android']
    publishers=sorted({r.get('Publisher') for r in all_rows if r.get('Publisher')})[:80]
    def opts(vals,current): return ''.join(f'<option value="{esc(v)}" {"selected" if v==current else ""}>{esc(v)}</option>' for v in vals)
    filters=f'''<form class="tracker-filters control-panel" method="get" action="/game-tracker"><label>Search<input name="q" value="{esc(search)}" placeholder="Game, publisher, genre"></label><label>Signal<select name="signal"><option value="all">All signals</option>{opts(signals,signal)}</select></label><label>Platform<select name="platform"><option value="all">All platforms</option>{opts(platforms,platform)}</select></label><label>Publisher<select name="publisher"><option value="all">All publishers</option>{opts(publishers,publisher)}</select></label><button class="primary">Apply filters</button><a class="btn" href="/game-tracker">Clear Filters</a></form>'''
    chips=[]
    if search: chips.append(('q', f'Search: {search}'))
    if signal!='all': chips.append(('signal', signal))
    if platform!='all': chips.append(('platform', platform))
    if publisher!='all': chips.append(('publisher', publisher))
    body=''.join(f'<tr><td><b>{esc(display_name(r))}</b><small>{esc(r.get("Original Title") or r.get("original_title") or "")}</small></td><td>{esc(r.get("Publisher") or r.get("publisher_name") or "N/A")}</td><td>{esc(r.get("Platform") or "N/A")}</td><td>{esc(r.get("Mention Type") or "Mentioned")}</td><td>{esc(display_date(r.get("Release Date")) or display_date(r.get("country_release_date")) or "N/A")}</td><td>{esc(r.get("Genre") or r.get("genre") or "N/A")}</td><td>{esc(signal_label(r))}</td><td>{esc(r.get("Market Overview Reason") or r.get("Inclusion Reason") or "Details pending source integration.")}</td><td><a href="/latest-brief?selected={urllib.parse.quote(str(r.get("_uid","")))}">Open brief</a></td></tr>' for r in filtered)
    return f'''{page_header('Game Tracker','Games mentioned across briefs','Includes released games and lightweight news/brief mentions that appear in the Market Brief experience.')}{filters}{filter_chips('/game-tracker', q, chips)}{result_bar('games', len(filtered), len(all_rows), 'Filtered rows update this table after Apply filters.')}
    <div class="data-table"><table><thead><tr><th>Game</th><th>Publisher</th><th>Platform</th><th>Mention Type</th><th>Release / Event Date</th><th>Genre</th><th>Signal</th><th>Key Details</th><th>Related Brief</th></tr></thead><tbody>{body or '<tr><td colspan="9">No matching games. Clear filters or try a broader search.</td></tr>'}</tbody></table></div>'''

# --- Live current brief data-source correction ---
# The current live brief should read the refreshed final workflow CSV only.
# Older backtest/demo/source rows must not leak into the current Market Brief.
def _final_rows_only():
    return rows()

def rows_for_brief(rec):
    if rec.get('demo'):
        base = _final_rows_only()
        demo = [dict(r) for r in base[:6]]
        for r in demo:
            r['Signal Display'] = signal_label(r)
            r['_uid'] = uid(r) + '_' + rec.get('id','demo')
            r['Brief Demo Note'] = 'Demo/sample period for interaction testing only.'
        return demo
    return _final_rows_only()

def brief_records():
    current = brief_record_current(state())
    return [current]

def historical_briefs(s,q,msg=''):
    all_recs = brief_records()
    month = _qone(q,'month','all')
    year = _qone(q,'year','all')
    search = _qone(q,'q','').strip().lower()
    def matches(rec):
        md = pdate(rec.get('meeting'))
        if month != 'all' and (not md or str(md.month) != str(month)): return False
        if year != 'all' and (not md or str(md.year) != str(year)): return False
        if search:
            hay = ' '.join([clean_period(rec), display_date(rec.get('meeting')) or '', brief_type_label(rec)] + [display_name(r) + ' ' + (r.get('Publisher') or '') for r in rows_for_brief(rec)])
            if search not in hay.lower(): return False
        return True
    recs = [r for r in all_recs if matches(r)]
    years = sorted({(pdate(r.get('meeting')) or date.today()).year for r in all_recs}, reverse=True)
    months = ''.join(f'<option value="{i}" {"selected" if str(i)==str(month) else ""}>{datetime(2026,i,1).strftime("%B")}</option>' for i in range(1,13))
    year_opts = ''.join(f'<option value="{y}" {"selected" if str(y)==str(year) else ""}>{y}</option>' for y in years)
    chips=[]
    if month!='all': chips.append(('month', _month_name(month)))
    if year!='all': chips.append(('year', year))
    if search: chips.append(('q', f'Search: {search}'))
    cards=''
    for rec in recs:
        rs = rows_for_brief(rec); strong=[r for r in rs if r.get('Signal Type')=='Strong Market Signal']; emerging=[r for r in rs if r.get('Signal Type')!='Strong Market Signal']
        leader=max(strong or rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
        demo='<span class="demo-pill">Demo/sample</span>' if rec.get('demo') else ''
        cards += f'''<article class="archive-card reading-card"><div class="archive-main"><small>Market Brief {demo}</small><h3>{esc(clean_period(rec))}</h3><p>Meeting {esc(display_date(rec.get('meeting')) or 'Unavailable')}</p></div><ul class="archive-highlights"><li>{len(rs)} launch records</li><li>{len(strong)} Strong · {len(emerging)} Emerging</li><li>Top revenue title: {esc(display_name(leader)) if leader else 'Unavailable'}</li></ul><a class="btn primary" href="/latest-brief?brief={urllib.parse.quote(rec['id'])}">Open full brief</a></article>'''
    filters = f'''<form class="archive-toolbar control-panel" method="get" action="/historical-briefs"><label>Month<select name="month"><option value="all">All months</option>{months}</select></label><label>Year<select name="year"><option value="all">All years</option>{year_opts}</select></label><label>Search<input name="q" value="{esc(search)}" placeholder="Game, publisher, period"></label><button class="primary">Apply filters</button><a class="btn" href="/historical-briefs">Clear Filters</a></form>'''
    return f'''{page_header('Brief Archive','Historical Briefs','Open past market briefs by reporting period. This is the reading archive, not the meeting schedule.')}{filters}{filter_chips('/historical-briefs', q, chips)}{result_bar('briefs', len(recs), len(all_recs), 'Filtered by reporting period, meeting date, title, or publisher.')}
        <div class="archive-grid">{cards or empty_state('No matching briefs','No briefs match the selected filters. Clear filters or choose a different month/year.')}</div>'''

def market_timeline(s,q,msg=''):
    all_recs = brief_records()
    latest = all_recs[0]
    base_md = pdate(latest.get('meeting')) or date.today()
    month = int(_qone(q,'month',str(base_md.month)))
    year = int(_qone(q,'year',str(base_md.year)))
    shown=[]
    for rec in all_recs:
        md=pdate(rec.get('meeting'))
        if md and md.month==month and md.year==year: shown.append(rec)
    years=sorted({(pdate(r.get('meeting')) or base_md).year for r in all_recs}, reverse=True)
    month_opts=''.join(f'<option value="{i}" {"selected" if i==month else ""}>{datetime(2026,i,1).strftime("%B")}</option>' for i in range(1,13))
    year_opts=''.join(f'<option value="{y}" {"selected" if y==year else ""}>{y}</option>' for y in years)
    prev_month = date(year,month,1) - timedelta(days=1)
    next_month = (date(year,month,28) + timedelta(days=4)).replace(day=1)
    controls=f'''<form class="calendar-controls control-panel" method="get" action="/market-timeline"><a class="btn" href="/market-timeline?month={prev_month.month}&year={prev_month.year}">Previous Month</a><label>Month<select name="month">{month_opts}</select></label><label>Year<select name="year">{year_opts}</select></label><button class="primary">Update Timeline</button><a class="btn" href="/market-timeline?month={base_md.month}&year={base_md.year}">Current reporting month</a><a class="btn" href="/market-timeline?month={next_month.month}&year={next_month.year}">Next Month</a></form>'''
    items=''
    for rec in shown:
        demo='<span class="demo-pill">Demo/sample</span>' if rec.get('demo') else ''
        items += f'''<article class="timeline-item"><div class="timeline-date"><span>Meeting</span><b>{esc(display_date(rec.get('meeting')) or 'Unavailable')}</b>{demo}</div><div class="timeline-detail"><h3>{esc(clean_period(rec))}</h3><p>{len(rows_for_brief(rec))} launch records in this brief.</p></div><a class="btn ghost" href="/latest-brief?brief={urllib.parse.quote(rec['id'])}">Open brief</a></article>'''
    selected = shown[0] if shown else latest
    rhythm=f'''<section class="rhythm-panel"><h2>Selected month</h2>{result_bar('meeting records', len(shown), len(all_recs), _month_name(month)+' '+str(year))}<div class="rhythm-steps">{meta_item('Selected month', _month_name(month)+' '+str(year))}{meta_item('Report window', clean_period(selected))}{meta_item('Meeting date', display_date(selected.get('meeting')))}{meta_item('Brief type', brief_type_label(selected))}</div></section>'''
    return f'''{page_header('Market Timeline','Schedule and Reporting Windows','See meeting dates, reporting windows, data-as-of timing, and brief timing.')}{controls}{filter_chips('/market-timeline', q, [('month', _month_name(month)), ('year', str(year))])}<section class="timeline-shell"><div class="timeline-list">{items or empty_state('No meetings in this month','No brief or meeting record exists for the selected month/year. Try another month or return to the current reporting month.')}</div>{rhythm}</section>'''

def game_tracker(s,q,msg=''):
    all_rows = rows()
    search=_qone(q,'q','').strip().lower(); signal=_qone(q,'signal','all'); platform=_qone(q,'platform','all'); publisher=_qone(q,'publisher','all')
    def match(r):
        if search and search not in (' '.join([display_name(r), r.get('Publisher',''), r.get('Genre',''), r.get('Platform','')]).lower()): return False
        if signal!='all' and signal_label(r)!=signal: return False
        if platform!='all' and platform.lower() not in (r.get('Platform','') or '').lower(): return False
        if publisher!='all' and (r.get('Publisher') or '') != publisher: return False
        return True
    filtered=[r for r in all_rows if match(r)]
    signals=sorted({signal_label(r) for r in all_rows if signal_label(r)})
    platforms=['iOS','Android']
    publishers=sorted({r.get('Publisher') for r in all_rows if r.get('Publisher')})[:80]
    def opts(vals,current): return ''.join(f'<option value="{esc(v)}" {"selected" if v==current else ""}>{esc(v)}</option>' for v in vals)
    filters=f'''<form class="tracker-filters control-panel" method="get" action="/game-tracker"><label>Search<input name="q" value="{esc(search)}" placeholder="Game, publisher, genre"></label><label>Signal<select name="signal"><option value="all">All signals</option>{opts(signals,signal)}</select></label><label>Platform<select name="platform"><option value="all">All platforms</option>{opts(platforms,platform)}</select></label><label>Publisher<select name="publisher"><option value="all">All publishers</option>{opts(publishers,publisher)}</select></label><button class="primary">Apply filters</button><a class="btn" href="/game-tracker">Clear Filters</a></form>'''
    chips=[]
    if search: chips.append(('q', f'Search: {search}'))
    if signal!='all': chips.append(('signal', signal))
    if platform!='all': chips.append(('platform', platform))
    if publisher!='all': chips.append(('publisher', publisher))
    body=''.join(f'<tr><td><b>{esc(display_name(r))}</b><small>{esc(r.get("Original Title") or "")}</small></td><td>{esc(r.get("Publisher"))}</td><td>{esc(r.get("Platform"))}</td><td>Singapore</td><td>{esc(display_date(r.get("Release Date")) or "Unavailable")}</td><td>{esc(r.get("Genre"))}</td><td>{"Released" if r.get("Release Date") else "Mentioned"}</td><td>{esc(signal_label(r))}</td><td>{esc(r.get("Market Overview Reason") or r.get("Inclusion Reason") or "N/A")}</td><td><a href="/latest-brief?selected={urllib.parse.quote(str(r.get("_uid","")))}">Open brief</a></td></tr>' for r in filtered)
    return f'''{page_header('Game Tracker','Games mentioned across briefs','Use filters to see which games are currently included in the local market scan.')}{filters}{filter_chips('/game-tracker', q, chips)}{result_bar('games', len(filtered), len(all_rows), 'Filtered rows update this table immediately after Apply filters.')}
    <div class="data-table"><table><thead><tr><th>Game</th><th>Publisher</th><th>Platform</th><th>Market</th><th>Event / Release Date</th><th>Genre</th><th>Status</th><th>Market Relevance</th><th>Key Details</th><th>Related Brief</th></tr></thead><tbody>{body or '<tr><td colspan="10">No matching games. Clear filters or try a broader search.</td></tr>'}</tbody></table></div>'''

# --- Combine Historical Briefs and Market Timeline into one archive/schedule view ---
PUBLIC_NAV_ITEMS = [
    ('/latest-brief', 'Latest Brief', 'Read the current executive market update.'),
    ('/historical-briefs', 'Brief Archive', 'Open past briefs and review meeting schedule.'),
    ('/game-tracker', 'Game Tracker', 'Filter games mentioned across briefs.'),
]
ROUTE_ALIASES.update({'/market-timeline':'/historical-briefs','/calendar':'/historical-briefs','/reports':'/historical-briefs','/data-export':'/historical-briefs'})

def visible_nav_items(s):
    items = list(PUBLIC_NAV_ITEMS)
    if current_access_role(s) == 'Admin':
        items.append(('/admin', 'Admin Console', 'Manage corrections, scans, and evidence.'))
    return items

def layout(path,s,content):
    canonical = ROUTE_ALIASES.get(path,path)
    nav = ''.join(ui.nav_link(href,label,desc,canonical==href) for href,label,desc in visible_nav_items(s))
    p = period(s)
    active_name = next((label for href,label,desc in visible_nav_items(s) if href==canonical),'Latest Brief')
    data_text = data_asof(rows(), p)
    topbar = f'''<header class="topbar compact-topbar slim-context-bar" aria-label="Brief context">
      <div class="inline-context"><b>{esc(active_name)}</b><span>Period: {esc(display_date_range(p.get('start'), p.get('end')) or 'Unavailable')}</span><span>Meeting: {esc(display_date(p.get('meeting')) or 'Unavailable')}</span><span>Data as of: {esc(data_text or 'N/A')}</span></div>
      <div class="top-actions compact-actions"><a class="btn ghost" href="/historical-briefs">Previous Briefs</a><a class="btn primary" href="/latest-brief">Latest Brief</a><a class="btn ghost" href="/logout">Logout</a></div>
    </header>'''
    return ui.render_template(ROOT/'templates'/'base.html', title='IBD Market Intelligence', nav=nav, topbar=topbar, content=content)

def historical_briefs(s,q,msg=''):
    all_recs = brief_records()
    latest = all_recs[0]
    latest_md = pdate(latest.get('meeting')) or date.today()
    month = _qone(q,'month','all')
    year = _qone(q,'year','all')
    search = _qone(q,'q','').strip().lower()
    def rec_matches(rec):
        md = pdate(rec.get('meeting'))
        if month != 'all' and (not md or str(md.month) != str(month)): return False
        if year != 'all' and (not md or str(md.year) != str(year)): return False
        if search:
            hay = ' '.join([clean_period(rec), display_date(rec.get('meeting')) or '', brief_type_label(rec)] + [display_name(r) + ' ' + (r.get('Publisher') or '') for r in rows_for_brief(rec)])
            if search not in hay.lower(): return False
        return True
    recs = [r for r in all_recs if rec_matches(r)]
    years = sorted({(pdate(r.get('meeting')) or latest_md).year for r in all_recs}, reverse=True)
    months = ''.join(f'<option value="{i}" {"selected" if str(i)==str(month) else ""}>{datetime(2026,i,1).strftime("%B")}</option>' for i in range(1,13))
    year_opts = ''.join(f'<option value="{y}" {"selected" if str(y)==str(year) else ""}>{y}</option>' for y in years)
    chips=[]
    if month!='all': chips.append(('month', _month_name(month)))
    if year!='all': chips.append(('year', year))
    if search: chips.append(('q', f'Search: {search}'))
    archive_cards=''
    timeline_items=''
    for rec in recs:
        rs = rows_for_brief(rec)
        strong = [r for r in rs if r.get('Signal Type')=='Strong Market Signal']
        emerging = [r for r in rs if r.get('Signal Type')!='Strong Market Signal']
        leader = max(strong or rs,key=lambda r:sf(r.get('SG Gross Revenue')),default={})
        demo = '<span class="demo-pill">Demo/sample</span>' if rec.get('demo') else ''
        archive_cards += f'''<article class="archive-card reading-card"><div class="archive-main"><small>Market Brief {demo}</small><h3>{esc(clean_period(rec))}</h3><p>Meeting {esc(display_date(rec.get('meeting')) or 'Unavailable')}</p></div><ul class="archive-highlights"><li>{len(rs)} launch records</li><li>{len(strong)} Strong · {len(emerging)} Emerging</li><li>Top revenue title: {esc(display_name(leader)) if leader else 'Unavailable'}</li></ul><a class="btn primary" href="/latest-brief?brief={urllib.parse.quote(rec['id'])}">Open full brief</a></article>'''
        timeline_items += f'''<article class="timeline-item"><div class="timeline-date"><span>Meeting</span><b>{esc(display_date(rec.get('meeting')) or 'Unavailable')}</b>{demo}</div><div class="timeline-detail"><h3>{esc(clean_period(rec))}</h3><p>{len(rs)} launch records · {brief_type_label(rec)}</p></div><a class="btn ghost" href="/latest-brief?brief={urllib.parse.quote(rec['id'])}">Open brief</a></article>'''
    filters = f'''<form class="archive-toolbar control-panel" method="get" action="/historical-briefs"><label>Month<select name="month"><option value="all">All months</option>{months}</select></label><label>Year<select name="year"><option value="all">All years</option>{year_opts}</select></label><label>Search<input name="q" value="{esc(search)}" placeholder="Game, publisher, period"></label><button class="primary">Apply filters</button><a class="btn" href="/historical-briefs">Clear Filters</a></form>'''
    return f'''{page_header('Brief Archive','Historical Briefs + Meeting Timeline','Open past market briefs and see the meeting/reporting rhythm in one place.')}{filters}{filter_chips('/historical-briefs', q, chips)}{result_bar('briefs', len(recs), len(all_recs), 'Filters update both the archive cards and the timeline below.')}
      <section class="combined-archive-grid"><div><h2>Brief Archive</h2><div class="archive-grid">{archive_cards or empty_state('No matching briefs','No briefs match the selected filters. Clear filters or choose a different month/year.')}</div></div><aside class="combined-timeline"><h2>Meeting Timeline</h2><p class="muted">Schedule context for the same selected filters.</p><div class="timeline-list compact">{timeline_items or empty_state('No meetings in this selection','No meeting records match the selected filters.')}</div></aside></section>'''

market_timeline = historical_briefs
calendar_page = historical_briefs

# --- Top Grossing + WW recent-release workflow display override ---
# The current workflow uses SG Top Grossing as the discovery signal, WW Released
# Days Ago buckets as the recency signal, and SG gross revenue as the Strong
# threshold. SG country release date is evidence only.

def workflow_signal_group(r):
    return 'strong' if r.get('Signal Type') == 'Strong Market Signal' else 'monitoring'

def short_signal_label(r):
    return 'Strong' if workflow_signal_group(r) == 'strong' else 'Watchlist'

def executive_summary_bullets(rs):
    total = len(rs)
    strong = [r for r in rs if workflow_signal_group(r) == 'strong']
    monitoring = [r for r in rs if workflow_signal_group(r) != 'strong']
    publishers = {}
    st_available = 0
    for r in rs:
        publishers[r.get('Publisher') or 'Unknown'] = publishers.get(r.get('Publisher') or 'Unknown', 0) + 1
        if sf(r.get('SG Gross Revenue')) > 0 or sg_downloads_value(r) > 0 or market_entries(r):
            st_available += 1
    bullets = [
        f"{total} SG Top Grossing recent-release candidate{'s' if total != 1 else ''} are included in this brief.",
        f"{len(strong)} title{'s' if len(strong) != 1 else ''} exceeded $1K estimated SG gross revenue during the report period.",
    ]
    if monitoring:
        bullets.append(f"{len(monitoring)} title{'s' if len(monitoring) != 1 else ''} remained below the Strong threshold and should be tracked through the watchlist rather than treated as a Strong market signal.")
    if publishers:
        counts = sorted(publishers.values(), reverse=True)
        if len(counts) > 1 and counts[0] == counts[-1]:
            bullets.append("Publisher activity was evenly distributed among included records; no single publisher dominated this brief.")
        elif len(counts) > 1 and counts[0] > counts[1]:
            top = [p for p,c in publishers.items() if c == counts[0]]
            bullets.append(f"{', '.join(top[:2])} had the most included records this period, with {counts[0]} record(s).")
        else:
            bullets.append("No single publisher clearly dominated included released-game activity this period.")
    bullets.append(f"Top SEA6 markets are ranked by estimated gross revenue and show both gross revenue and downloads where available.")
    return ''.join(f'<li>{esc(b)}</li>' for b in bullets[:5])

def released_games_section(strong,emerging,view):
    rec_id = globals().get('CURRENT_BRIEF_ID_FOR_UI', 'current')
    base = {'brief': rec_id} if rec_id != 'current' else {}
    card_href = _query('/latest-brief', {**base, 'view':'cards'})
    table_href = _query('/latest-brief', {**base, 'view':'table'})
    toggle=f'<div class="view-toggle" aria-label="Released games view"><a class="{ "active" if view!="table" else "" }" href="{esc(card_href)}" aria-current="{ "true" if view!="table" else "false" }">Card view</a><a class="{ "active" if view=="table" else "" }" href="{esc(table_href)}" aria-current="{ "true" if view=="table" else "false" }">Compact table</a></div>'
    count = len(strong) + len(emerging)
    count_line = result_bar('released-game records', count, count, 'Discovery is based on SG Top Grossing + WW recent-release buckets. Top Free is recorded only for rank context.')
    if view=='table':
        return f'<section class="brief-section"><div class="section-heading"><div><h2>Released Games in Singapore</h2><p>Recently released games with SG Top Grossing evidence. Top SEA6 markets are ranked by gross revenue and include downloads.</p></div>{toggle}</div>{count_line}{compact_public_table(strong+emerging)}</section>'
    strong_body=''.join(signal_card(r,'strong') for r in strong) or empty_state('No Strong releases in this brief','No included title exceeded $1K estimated SG gross revenue during the report period.')
    return f'''<section class="brief-section"><div class="section-heading"><div><h2>Released Games in Singapore</h2><p>Recently released games with SG Top Grossing evidence. Top SEA6 markets are ranked by gross revenue and include downloads.</p></div>{toggle}</div>{count_line}
        <div class="signal-heading"><h3>Strong</h3><span>{len(strong)} shown · SG gross revenue exceeded $1K during the report period.</span></div><div class="signal-grid">{strong_body}</div>
    </section>'''

def announcement_watchlist_rows():
    released_keys = {r.get('unified_app_id') or uid(r) for r in rows()}
    out = []
    seen = set()
    for r in source_rows(True):
        title = r.get('Radar Matched Title') or display_name(r)
        key = (r.get('unified_app_id') or title).lower()
        if not title or key in seen or key in released_keys:
            continue
        seen.add(key)
        x = dict(r)
        x['Game Title'] = title
        x['Watchlist Reason'] = 'Mentioned in game announcements/news. Track around stated launch timing; remove if no SG Top Grossing signal appears within ±2 reporting periods.'
        x['Watchlist Source'] = 'Announcement / news mention'
        out.append(x)
    if out:
        return out[:4]
    return [
        {'Game Title':'Sample announced title','Publisher':'TBC','Platform':'TBC','Genre':'TBC','Watchlist Source':'Sample announcement watchlist','Watchlist Reason':'Details pending AI News Radar integration. Track if a launch window is identified, then check SG Top Grossing within ±2 reporting periods.'},
        {'Game Title':'Sample IP / publisher watch','Publisher':'TBC','Platform':'TBC','Genre':'TBC','Watchlist Source':'Sample announcement watchlist','Watchlist Reason':'Placeholder example only. Replace with AI News Radar-sourced announcement once integration is connected.'},
    ]

def combined_watchlist_section(monitoring):
    cards = ''
    for r in monitoring:
        cards += f'''<article class="watch-card market-watch"><small>Market watchlist</small><h3>{esc(display_name(r))}</h3><p>{esc(r.get('Publisher') or 'Publisher unavailable')}</p>{key_details_box('Appears in SG Top Grossing and has SG revenue above $0, but it has not crossed the $1K Strong threshold. Track for up to 3 periods.')}</article>'''
    for r in announcement_watchlist_rows():
        cards += f'''<article class="watch-card announcement-watch"><small>{esc(r.get('Watchlist Source') or 'Announcement watchlist')}</small><h3>{esc(display_name(r))}</h3><p>{esc(r.get('Publisher') or r.get('publisher_name') or 'Publisher unavailable')}</p>{key_details_box(r.get('Watchlist Reason') or 'Details pending AI News Radar integration.')}</article>'''
    return f'''<section class="brief-section watchlist-section"><div class="section-heading"><div><h2>Watchlist</h2><p>Potential report candidates that do not currently meet Strong Market Signal requirements. Announcement-based watchlist items are sample/source-ready until AI News Radar integration is executed.</p></div></div><div class="watch-card-grid">{cards or empty_state('No watchlist items','No below-threshold market candidates or announcement candidates are available for this period.')}</div></section>'''

def latest_brief(s,q,msg=''):
    rec = selected_brief(q,s)
    globals()['CURRENT_BRIEF_ID_FOR_UI'] = rec.get('id','current')
    rs = rows_for_brief(rec)
    view = _qone(q, 'view', 'cards')
    selected = _qone(q, 'selected', '')
    strong = sorted([r for r in rs if workflow_signal_group(r) == 'strong'], key=lambda r:-sf(r.get('SG Gross Revenue')))
    monitoring = sorted([r for r in rs if workflow_signal_group(r) != 'strong'], key=lambda r:(-sf(r.get('SG Gross Revenue')),best_rank_strength(r),r.get('Release Date','')))
    detail = detail_panel(selected,rs)
    actions = '<a class="btn primary" href="/export/print.html">Print Report</a><a class="btn" href="/export/executive.csv">Export CSV</a>'
    headline = f'{len(rs)} SG Top Grossing recent-release candidate{"s" if len(rs)!=1 else ""} are included: {len(strong)} strong signal{"s" if len(strong)!=1 else ""} and {len(monitoring)} watchlist item{"s" if len(monitoring)!=1 else ""}.'
    demo_note = '<div class="state-note">Demo/sample period: this view reuses local records only to prove switching behavior.</div>' if rec.get('demo') else ''
    page = f'''{page_header('Market Brief','Singapore Gaming Market',headline,actions)}
        {brief_selector_widget(rec)}{demo_note}
        <section class="brief-section executive-section"><div class="section-heading"><div><h2>Executive Summary</h2><p>Factual updates based on SG Top Grossing visibility and Sensor Tower market estimates.</p></div></div><ul class="executive-bullets">{executive_summary_bullets(rs)}</ul></section>
        {global_announcement_cards(rs)}{released_games_section(strong,monitoring,view)}{combined_watchlist_section(monitoring)}{local_trends_section(rs)}
        <details class="methodology"><summary>Methodology and data notes</summary><p>Discovery uses SG Games Top Grossing plus Sensor Tower Released Days Ago (WW) buckets for approximately one-week and two-week global recency. SG Top Free ranks are recorded for dashboard context only and do not drive inclusion. SG country release date is recorded as evidence, but it is not used as an exclusion gate because it may be early or late. Strong means estimated SG gross revenue exceeded $1K during the report period. Watchlist means potential report candidates that do not currently meet Strong criteria. Market watchlist items are monitored for up to 3 periods. Announcement watchlist items should be tracked around the launch timing mentioned by the news source and removed if no SG Top Grossing signal appears within ±2 reporting periods. Revenue is shown as estimated gross revenue. Top SEA6 markets are ranked by gross revenue and include downloads where available.</p><p><a href="{AI_NEWS_RADAR_URL}" target="_blank" rel="noopener">Open AI News Radar</a></p></details>'''
    return f'<div class="detail-layout"><div>{page}</div>{detail}</div>' if detail else page


# --- Final Game Tracker override: include all games mentioned in brief surfaces ---
def mentioned_game_rows():
    current_released = rows()
    released_keys = {rr.get('unified_app_id') or uid(rr) for rr in current_released}
    combined = []
    seen = set()
    for r in current_released + source_rows(True):
        title = display_name(r)
        key = r.get('unified_app_id') or r.get('_uid') or title.lower()
        if not title or key in seen:
            continue
        seen.add(key)
        x = dict(r)
        x['_uid'] = x.get('_uid') or uid(x)
        x['Mention Type'] = 'Released game' if key in released_keys or x.get('SG Gross Revenue') else 'News / brief mention'
        combined.append(x)
    return combined

def game_tracker(s,q,msg=''):
    all_rows = mentioned_game_rows()
    search=_qone(q,'q','').strip().lower(); signal=_qone(q,'signal','all'); platform=_qone(q,'platform','all'); publisher=_qone(q,'publisher','all')
    def match(r):
        hay=' '.join([display_name(r), r.get('Publisher',''), r.get('publisher_name',''), r.get('Genre',''), r.get('genre',''), r.get('Platform',''), r.get('Mention Type',''), r.get('Radar Matched Title','')]).lower()
        if search and search not in hay: return False
        if signal!='all' and signal_label(r)!=signal: return False
        if platform!='all' and platform.lower() not in (r.get('Platform','') or '').lower(): return False
        if publisher!='all' and (r.get('Publisher') or r.get('publisher_name') or '') != publisher: return False
        return True
    filtered=[r for r in all_rows if match(r)]
    signals=sorted({signal_label(r) for r in all_rows if signal_label(r)})
    platforms=sorted({p for r in all_rows for p in ['iOS','Android'] if p.lower() in (r.get('Platform','') or '').lower()}) or ['iOS','Android']
    publishers=sorted({r.get('Publisher') or r.get('publisher_name') for r in all_rows if r.get('Publisher') or r.get('publisher_name')})[:80]
    def opts(vals,current): return ''.join(f'<option value="{esc(v)}" {"selected" if v==current else ""}>{esc(v)}</option>' for v in vals)
    filters=f'''<form class="tracker-filters control-panel" method="get" action="/game-tracker"><label>Search<input name="q" value="{esc(search)}" placeholder="Game, publisher, genre"></label><label>Signal<select name="signal"><option value="all">All signals</option>{opts(signals,signal)}</select></label><label>Platform<select name="platform"><option value="all">All platforms</option>{opts(platforms,platform)}</select></label><label>Publisher<select name="publisher"><option value="all">All publishers</option>{opts(publishers,publisher)}</select></label><button class="primary">Apply filters</button><a class="btn" href="/game-tracker">Clear Filters</a></form>'''
    chips=[]
    if search: chips.append(('q', f'Search: {search}'))
    if signal!='all': chips.append(('signal', signal))
    if platform!='all': chips.append(('platform', platform))
    if publisher!='all': chips.append(('publisher', publisher))
    body=''.join(f'<tr><td><b>{esc(display_name(r))}</b><small>{esc(r.get("Original Title") or r.get("original_title") or "")}</small></td><td>{esc(r.get("Publisher") or r.get("publisher_name") or "N/A")}</td><td>{esc(r.get("Platform") or "N/A")}</td><td>{esc(r.get("Mention Type") or "Mentioned")}</td><td>{esc(display_date(r.get("Release Date")) or display_date(r.get("country_release_date")) or "N/A")}</td><td>{esc(r.get("Genre") or r.get("genre") or "N/A")}</td><td>{esc(signal_label(r))}</td><td>{esc(r.get("Market Overview Reason") or r.get("Inclusion Reason") or "Details pending source integration.")}</td><td><a href="/latest-brief?selected={urllib.parse.quote(str(r.get("_uid","")))}">Open brief</a></td></tr>' for r in filtered)
    return f'''{page_header('Game Tracker','Games mentioned across briefs','Includes released games and lightweight news/brief mentions that appear in the Market Brief experience.')}{filters}{filter_chips('/game-tracker', q, chips)}{result_bar('games', len(filtered), len(all_rows), 'Filtered rows update this table after Apply filters.')}
    <div class="data-table"><table><thead><tr><th>Game</th><th>Publisher</th><th>Platform</th><th>Mention Type</th><th>Release / Event Date</th><th>Genre</th><th>Signal</th><th>Key Details</th><th>Related Brief</th></tr></thead><tbody>{body or '<tr><td colspan="9">No matching games. Clear filters or try a broader search.</td></tr>'}</tbody></table></div>'''

# --- Source-of-truth product simplification ---
# The system-generated scan is treated as final. Admin is only a small control
# layer for meeting date and presentation grouping between Strong and Watchlist.

def visible_nav_items(s):
    items = list(PUBLIC_NAV_ITEMS)
    if current_access_role(s) == 'Admin':
        items.append(('/admin', 'Admin Console', 'Meeting date management.'))
    return items

def original_title_line(r):
    original = (r.get('Original Title') or r.get('original_title') or '').strip()
    display = display_name(r)
    if original and original != display:
        return f'<p class="original-title"><span>Original title</span>{esc(original)}</p>'
    return ''

def field_value(value):
    value = str(value or '').strip()
    return esc(value) if value else 'N/A'

def grouped_signal_card(r,kind='strong'):
    signal = 'Strong Market Signal' if workflow_signal_group(r) == 'strong' else 'Watchlist'
    return f'''<article class="signal-card {kind} rich-signal-card">
      <div class="signal-card-top"><span>{signal_badge_for_row(r)}</span></div>
      <section class="card-block card-overview">
        <h3>{esc(display_name(r))}</h3>
        {original_title_line(r)}
        <dl>
          <div><dt>Publisher</dt><dd>{field_value(r.get('Publisher'))}</dd></div>
          <div><dt>Platform</dt><dd>{field_value(r.get('Platform'))}</dd></div>
          <div><dt>Genre</dt><dd>{field_value(r.get('Genre'))}</dd></div>
          <div><dt>Release evidence</dt><dd>{field_value(display_date(r.get('Release Date')))}</dd></div>
          <div><dt>Signal</dt><dd>{esc(signal)}</dd></div>
        </dl>
      </section>
      <section class="card-block card-performance">
        <h4>SG Performance</h4>
        <div class="metric-pair"><div><b>{money(r.get('SG Gross Revenue'))}</b><span>Gross revenue</span></div><div><b>{sg_downloads_value(r):,}</b><span>Downloads</span></div></div>
      </section>
      <section class="card-block card-ranks">
        <h4>SG Store Ranks</h4>
        {store_ranks_block(r)}
      </section>
      <section class="card-block card-markets">
        <h4>Top SEA6 Markets</h4>
        {market_chips(r)}
      </section>
      <section class="card-block card-evidence">
        <h4>System-derived details</h4>
        <p>{field_value(r.get('Inclusion Reason') or r.get('Signal Definition'))}</p>
      </section>
    </article>'''

def signal_card(r,kind='strong'):
    return grouped_signal_card(r, kind)

def latest_brief(s,q,msg=''):
    rec = selected_brief(q,s)
    globals()['CURRENT_BRIEF_ID_FOR_UI'] = rec.get('id','current')
    rs = rows_for_brief(rec)
    view = _qone(q, 'view', 'cards')
    strong = sorted([r for r in rs if workflow_signal_group(r) == 'strong'], key=lambda r:-sf(r.get('SG Gross Revenue')))
    monitoring = sorted([r for r in rs if workflow_signal_group(r) != 'strong'], key=lambda r:(-sf(r.get('SG Gross Revenue')),best_rank_strength(r),r.get('Release Date','')))
    actions = '<a class="btn primary" href="/export/print.html">Print Report</a><a class="btn" href="/export/executive.csv">Export CSV</a>'
    headline = f'{len(rs)} SG Top Grossing recent-release candidate{"s" if len(rs)!=1 else ""} are included: {len(strong)} strong signal{"s" if len(strong)!=1 else ""} and {len(monitoring)} watchlist item{"s" if len(monitoring)!=1 else ""}.'
    page = f'''{page_header('Market Brief','Singapore Gaming Market',headline,actions)}
        {brief_selector_widget(rec)}
        <section class="brief-section executive-section"><div class="section-heading"><div><h2>Executive Summary</h2><p>System-generated factual summary from the current workflow data.</p></div></div><ul class="executive-bullets">{executive_summary_bullets(rs)}</ul></section>
        {global_announcement_cards(rs)}{released_games_section(strong,monitoring,view)}{combined_watchlist_section(monitoring)}{local_trends_section(rs)}
        <details class="methodology"><summary>Methodology and data notes</summary><p>The Market Brief is generated automatically from the local workflow output. Discovery uses SG Games Top Grossing plus Sensor Tower Released Days Ago (WW) buckets for approximately one-week and two-week global recency. SG Top Free ranks are recorded for dashboard context only and do not drive inclusion. SG country release date is recorded as evidence, not an exclusion gate. Strong means estimated SG gross revenue exceeded $1K during the report period. Watchlist means a pulled or announcement-mentioned candidate does not currently meet Strong criteria. Top SEA6 markets are ranked by gross revenue and include downloads where available.</p><p><a href="{AI_NEWS_RADAR_URL}" target="_blank" rel="noopener">Open AI News Radar</a></p></details>'''
    return page

def admin_signal_value(r):
    return 'Strong Market Signal' if workflow_signal_group(r) == 'strong' else 'Watchlist'

def admin_game_rows():
    return rows(include_deleted=True)

def admin_console(s,q,msg=''):
    if current_access_role(s) != 'Admin':
        return page_header('Admin Console','Restricted area','Admin controls are limited to meeting date management.')
    p = period(s)
    return f'''{page_header('Admin Console','Meeting Date Management','The system-generated scan is the source of truth. Admin controls only adjust the upcoming meeting date.')}
      {('<div class="toast">'+esc(msg)+'</div>') if msg else ''}
      <section class="admin-card simplified-admin-card">
        <h2>Upcoming Meeting Date</h2>
        <p>Change only the upcoming meeting date. The report window updates automatically from the meeting-cycle state.</p>
        <div class="admin-meta">{meta_item('Last completed meeting', display_date(s.get('last_completed_meeting_date')))}{meta_item('Upcoming meeting', display_date(s.get('upcoming_meeting_date')))}{meta_item('Meeting time', esc(s.get('meeting_time') or '16:00') + ' SGT')}{meta_item('Current report period', display_date_range(p.get('start'), p.get('end')))}</div>
        <form class="inline-admin-form" method="post" action="/update-meeting-date">
          <label>New upcoming meeting date <input type="date" name="upcoming_meeting_date" value="{esc(s.get('upcoming_meeting_date') or p.get('meeting') or '')}"></label>
          <button class="primary">Apply meeting date</button>
        </form>
      </section>'''

def rows_for_export_kind(kind,q,s):
    base = rows()
    if kind == 'strong':
        base = [r for r in base if workflow_signal_group(r) == 'strong']
    elif kind in ('emerging','early','watchlist'):
        base = [r for r in base if workflow_signal_group(r) != 'strong']
    elif kind == 'launches':
        base = filter_rows(base,q)
    return base

def print_html_for_brief(s,q):
    rs = rows()
    strong=''.join(grouped_signal_card(r,'strong') for r in [x for x in rs if workflow_signal_group(x)=='strong'])
    watch=''.join(grouped_signal_card(r,'emerging') for r in [x for x in rs if workflow_signal_group(x)!='strong'])
    return f"<html><head><meta charset='utf-8'><link rel='stylesheet' href='/static/dashboard.css'></head><body><h1>Singapore Gaming Market Brief</h1><p>Generated {todaystamp()}</p><h2>Strong Market Signals</h2>{strong}<h2>Watchlist</h2>{watch}</body></html>".encode()

class App(BaseHTTPRequestHandler):
    def sendb(self,b,typ,name=None,code=200):
        self.send_response(code); self.send_header('Content-Type',typ)
        if name: self.send_header('Content-Disposition',f'attachment; filename="{name}"')
        self.end_headers(); self.wfile.write(b)
    def html(self,x): self.sendb(x.encode(),'text/html; charset=utf-8')
    def set_cookie(self,sid):
        self.send_header('Set-Cookie',f'{SESSION_COOKIE}={urllib.parse.quote(sid)}; Path=/; HttpOnly; SameSite=Lax')
    def clear_cookie(self):
        self.send_header('Set-Cookie',f'{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0')
    def redir(self,u,msg=''):
        if msg: u+=('&' if '?' in u else '?')+'message='+urllib.parse.quote(msg)
        self.send_response(303); self.send_header('Location',u); self.end_headers()
    def redir_with_cookie(self,u,sid):
        self.send_response(303); self.send_header('Location',u); self.set_cookie(sid); self.end_headers()
    def redir_clear_cookie(self,u):
        self.send_response(303); self.send_header('Location',u); self.clear_cookie(); self.end_headers()
    def form(self): return urllib.parse.parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode())
    def auth_role(self): return auth_role_from_cookie(self.headers.get('Cookie',''))
    def login_required(self,next_url,msg=''):
        self.html(login_page(msg,safe_next(next_url)))
    def route_allowed(self,path,role):
        canonical=ROUTE_ALIASES.get(path,path)
        if canonical in ADMIN_ROUTES: return role=='Admin'
        if canonical in VIEWER_ROUTES: return role in ('Viewer','Admin')
        return role in ('Viewer','Admin')
    def apply_auth(self,s,role):
        s['_auth_role']=role; s['current_role']=role; s['current_user']=role
    def do_GET(self):
        ensure(); pr=urllib.parse.urlparse(self.path); path=ROUTE_ALIASES.get(pr.path, pr.path); q=urllib.parse.parse_qs(pr.query); s=state()
        if path.startswith('/static/'): return self.static(path)
        if pr.path=='/login':
            if self.auth_role(): return self.redir('/latest-brief')
            return self.html(login_page(q.get('message',[''])[0],q.get('next',['/latest-brief'])[0]))
        if pr.path=='/logout':
            sid=cookie_parts(self.headers.get('Cookie','')).get(SESSION_COOKIE,'')
            if sid in SESSIONS: del SESSIONS[sid]
            return self.redir_clear_cookie('/login')
        role=self.auth_role()
        if not role: return self.redir('/login?next='+urllib.parse.quote(self.path))
        self.apply_auth(s,role)
        if path.startswith('/export/'):
            name=path.split('/')[-1]
            if name in ADMIN_EXPORTS and role!='Admin': return self.redir('/latest-brief','Admin password required.')
            return self.export(path,q,s)
        msg=q.get('message',[''])[0]
        pages={'/latest-brief':latest_brief,'/historical-briefs':historical_briefs,'/game-tracker':game_tracker,'/market-timeline':market_timeline,'/trends':trends_insights,'/admin':admin_console,'/market-brief':latest_brief,'/data-export':historical_briefs,'/calendar':market_timeline,'/launches':game_tracker,'/reports':historical_briefs,'/review':admin_console,'/operations':admin_console}
        if path not in pages: return self.redir('/latest-brief')
        if not self.route_allowed(path,role): return self.redir('/latest-brief','Admin password required.')
        self.html(layout(path,s,pages[path](s,q,msg)))
    def static(self,path):
        target=(ROOT / path.lstrip('/')).resolve()
        static_root=(ROOT/'static').resolve()
        if not str(target).startswith(str(static_root)) or not target.exists():
            return self.sendb(b'Not found','text/plain; charset=utf-8',code=404)
        typ=mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
        return self.sendb(target.read_bytes(),typ)
    def export(self,path,q,s):
        name=path.split('/')[-1]; kind=name.replace('.csv','').replace('.html','')
        if name=='print.html': return self.sendb(print_html_for_brief(s,q),'text/html; charset=utf-8','ibd_market_brief_print.html')
        if name=='admin.csv': return self.sendb(csvbytes(rc(HIST) or rc(OVR)),'text/csv; charset=utf-8','ibd_admin_change_history.csv')
        if name=='sea6.csv': return self.sendb(csvbytes(rc(OUT/'layer4_sea6_country_totals.csv')),'text/csv; charset=utf-8','ibd_sea6_market_metrics.csv')
        if name=='title-normalisation.csv': return self.sendb(csvbytes(rc(OUT/'layer3_5_title_normalised_metadata.csv')),'text/csv; charset=utf-8','ibd_title_normalisation.csv')
        if name=='workflow-decisions.csv': return self.sendb(csvbytes(rc(DECISIONS)),'text/csv; charset=utf-8','ibd_workflow_decisions.csv')
        rs=rows_for_export_kind(kind,q,s); p=period(s); meta=[{'Intended Audience':'Executive' if kind in ('executive','strong','emerging','early') else 'Analyst','Selected Period':f"{nd(p['start'])} to {nd(p['end'])}",'Row Count':len(rs),'Generated Timestamp':todaystamp(),'Format':'CSV'}]
        if kind in ('executive','strong','emerging','early'):
            fields=['Game Title','Signal','Platform','Publisher','Release Date','Genre','Top 3 Markets','SG App Store Ranks','Approved Report Note']; rs=[{'Game Title':r.get('Game Title'),'Signal':r.get('Signal Display'),'Platform':r.get('Platform'),'Publisher':r.get('Publisher'),'Release Date':r.get('Release Date'),'Genre':r.get('Genre'),'Top 3 Markets':r.get('Top 3 Markets'),'SG App Store Ranks':r.get('SG App Store Ranks'),'Approved Report Note':r.get('Approved Report Note')} for r in rs]
        else:
            fields=[f for f in ['Game Title','English Display Title','Original Title','Detected Language','Machine English Title','Manual English Title','Translation Source','Translation Confidence','Translation Review Status','Translation Note','Publisher','Platform','Release Date','Genre','Signal Display','SG Gross Revenue','Top 3 Markets','SG App Store Ranks','Review Status','Title Status','Starred','Excluded','Discussion Notes','Approved Report Note','unified_app_id','run_timestamp_utc','ranking_date'] if any(f in r for r in rs)]
        return self.sendb((csvbytes(meta).decode('utf-8-sig')+'\n'+csvbytes(rs,fields).decode('utf-8-sig')).encode('utf-8-sig'),'text/csv; charset=utf-8',f'ibd_{kind}.csv')
    def do_POST(self):
        ensure(); pr=urllib.parse.urlparse(self.path); f=self.form(); s=state()
        if pr.path=='/login':
            password=(f.get('password',[''])[0] or '')
            next_url=safe_next(f.get('next',['/latest-brief'])[0])
            viewer=env_password('APP_VIEWER_PASSWORD'); admin=env_password('APP_ADMIN_PASSWORD')
            if admin and secrets.compare_digest(password,admin):
                return self.redir_with_cookie(next_url,new_session('Admin'))
            if viewer and secrets.compare_digest(password,viewer):
                if ROUTE_ALIASES.get(urllib.parse.urlparse(next_url).path,urllib.parse.urlparse(next_url).path) in ADMIN_ROUTES:
                    next_url='/latest-brief'
                return self.redir_with_cookie(next_url,new_session('Viewer'))
            msg='Password is incorrect.' if (viewer or admin) else 'Dashboard passwords are not configured.'
            return self.html(login_page(msg,next_url))
        if pr.path=='/logout':
            sid=cookie_parts(self.headers.get('Cookie','')).get(SESSION_COOKIE,'')
            if sid in SESSIONS: del SESSIONS[sid]
            return self.redir_clear_cookie('/login')
        role=self.auth_role()
        if not role: return self.login_required(pr.path)
        self.apply_auth(s,role)
        if pr.path in ('/update-meeting-date','/admin-signal-override','/run-scan','/set-report-status','/set-role') and role!='Admin':
            return self.redir('/latest-brief','Admin password required.')
        try:
            if pr.path=='/update-meeting-date':
                if current_access_role(s)!='Admin': return self.redir('/admin','Only admins can change the upcoming meeting date.')
                old=period(s); m=pdate((f.get('upcoming_meeting_date') or f.get('meeting_date') or [''])[0]); last=pdate(s.get('last_completed_meeting_date') or s.get('active_report_start_date'))
                if not m or not last or m<=last: raise ValueError('Upcoming meeting date must be after the last completed meeting date.')
                previous=s.get('upcoming_meeting_date') or old.get('meeting','')
                s['upcoming_meeting_date']=m.isoformat(); s['meeting_date']=m.isoformat(); s['active_report_start_date']=s.get('last_completed_meeting_date',''); save_state(s); sync_config(s)
                log_change(s,'meeting_date_change','','Reporting Calendar','Upcoming Meeting Date',previous,m.isoformat(),'Upcoming meeting date changed by admin for postponement.')
                return self.redir('/admin','Upcoming meeting date updated. The report window was recalculated automatically.')
            if pr.path=='/admin-signal-override':
                if current_access_role(s)!='Admin': return self.redir('/admin','Only admins can change signal grouping.')
                selected=f.get('unified_app_id',[''])[0]; signal=f.get('signal_type',['system'])[0]
                if not selected: raise ValueError('Missing game selection.')
                valid={'Strong Market Signal','Watchlist','system'}
                if signal not in valid: raise ValueError('Unsupported signal grouping.')
                base={uid(r):r for r in rows(include_deleted=True)}
                src=base.get(selected,{})
                overrides=ovr(); row=overrides.get(selected,{k:'' for k in OVR_FIELDS})
                old=row.get('override_signal_type','')
                row['unified_app_id']=selected; row['game_title']=src.get('Game Title') or src.get('English Display Title') or row.get('game_title','')
                row['override_signal_type']='' if signal=='system' else signal
                row['updated_at']=now(); overrides[selected]=row; save_ovr(overrides)
                log_change(s,'signal_grouping',selected,row.get('game_title',''),'override_signal_type',old,row.get('override_signal_type',''),'Signal grouping changed in Brief Editor.')
                return self.redir('/admin','Signal grouping updated. Market Brief and exports now use the effective grouping.')
            if pr.path=='/set-role':
                u=f.get('user',['Shauna'])[0]; r=f.get('role',['Viewer'])[0]; s['current_user']=u; s['current_role']='Contributor' if r=='Admin' and u not in ADMINS else r; save_state(s); return self.redir('/market-brief',f"Role switched to {s['current_role']}.")
            if pr.path in ('/bulk-action','/single-action'): return self.redir(self.headers.get('Referer','/launches'),update(s,f.get('selected',[]),f.get('action',[''])[0],f.get('note',[''])[0],f.get('approved_report_note',[''])[0],f.get('manual_english_title',[''])[0],f.get('translation_review_status',[''])[0],f.get('translation_note',[''])[0]))
            if pr.path=='/preview-date-change': return self.redir('/market-timeline?preview_date='+urllib.parse.quote(f.get('meeting_date',[''])[0]))
            if pr.path=='/confirm-date-change':
                if not can(s,'dates'): return self.redir('/calendar','Role cannot edit dates.')
                old=period(s); m=pdate(f.get('meeting_date',[''])[0]); st=pdate(s['active_report_start_date'])
                if not m or m<=st: raise ValueError('Meeting date must be after current report start date.')
                s['meeting_date']=m.isoformat(); s['report_status']='Stale'; save_state(s); sync_config(s); log_change(s,'date_change','','Reporting Calendar','Meeting Date',old['meeting'],m.isoformat(),'Upcoming meeting date changed'); return self.redir('/admin','Meeting date updated. Report marked Stale until rerun.')
            if pr.path=='/run-scan':
                if not can(s,'run'): return self.redir('/admin','Role cannot run scans.')
                return self.redir('/admin',run_scan(s))
            if pr.path=='/set-report-status':
                if not can(s,'finalise'): return self.redir('/admin','Role cannot finalise.')
                val=f.get('status',['Draft'])[0]
                if val=='Finalised':
                    rs=rows(); fn=SNAP/f"portal_report_{period(s)['start']}_to_{period(s)['end']}_rev_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"; wc(fn,rs,list(rs[0].keys()) if rs else []); s['report_status']='Finalised'; save_state(s); log_change(s,'finalise','','Report','Report Status','Ready','Finalised',fn.name); return self.redir('/admin','Finalised snapshot created.')
                s['report_status']=val; save_state(s); return self.redir('/admin',f'Report status set to {val}.')
        except Exception as e: return self.redir('/admin','Error: '+str(e))
        self.redir('/market-brief')
    def log_message(self,fmt,*args): print(fmt%args)

def main():
    ensure(); s=state(); sync_config(s); print(f'IBD Market Intelligence running at http://127.0.0.1:{PORT}'); ThreadingHTTPServer(('127.0.0.1',PORT),App).serve_forever()
# Frontend assets are served from /static/dashboard.css and /static/dashboard.js.

if __name__=='__main__': main()























































