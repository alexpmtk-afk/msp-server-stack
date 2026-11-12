"""Observation dates are not real-world resolution dates or Google edits."""
from collections import defaultdict
from datetime import datetime
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

SCHEMA='''
CREATE TABLE IF NOT EXISTS defects_observed_entity(
 entity_key TEXT PRIMARY KEY,source TEXT NOT NULL,identity_json TEXT NOT NULL,
 first_observed_at TEXT NOT NULL,last_observed_at TEXT NOT NULL,
 last_seen_run INTEGER NOT NULL,last_status TEXT NOT NULL,last_comment TEXT NOT NULL,
 status_changed_at TEXT,comment_changed_at TEXT);
CREATE TABLE IF NOT EXISTS defects_observed_current(
 source TEXT NOT NULL,source_row INTEGER NOT NULL,entity_key TEXT,
 tracking_quality TEXT NOT NULL,PRIMARY KEY(source,source_row));
CREATE TABLE IF NOT EXISTS defects_status_event(
 id INTEGER PRIMARY KEY,entity_key TEXT NOT NULL,source TEXT NOT NULL,
 source_row INTEGER NOT NULL,run_id INTEGER NOT NULL,event_kind TEXT NOT NULL,
 observed_at_utc TEXT NOT NULL,observed_date_moscow TEXT NOT NULL,
 previous_observed_at TEXT,old_status TEXT,new_status TEXT,
 old_comment TEXT,new_comment TEXT);
CREATE INDEX IF NOT EXISTS idx_defects_status_entity ON defects_status_event(entity_key,id);
'''

def identity(record):
    """Exclude physical row and editable state; do not guess edited identity fields."""
    if not record['internal_article_key'] or not record['received_date'] or not record['complaint'].strip():
        return None
    fields=[record['source'],record['internal_article_key'],record['received_date'],record['complaint']]
    if record['source']=='main':
        fields.extend([record['marketplace_cabinet_raw'],record['production_raw'],record['order_number_raw']])
    payload=json.dumps(fields,ensure_ascii=False,separators=(',',':'))
    return sha256(payload.encode()).hexdigest(),payload

def observe(con,records,*,run,observed_at,previous_run,baseline=False):
    stamp=datetime.fromisoformat(observed_at.replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('OBSERVATION_TIMEZONE_REQUIRED')
    day=stamp.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
    previous_quality={x[0]:x[1] for x in con.execute(
        "select entity_key,tracking_quality from defects_observed_current where entity_key is not null")}
    con.execute('delete from defects_observed_current')
    for source,rows in records.items():
        grouped=defaultdict(list)
        for r in rows:
            key=identity(r)
            if key is None:
                con.execute('insert into defects_observed_current values(?,?,null,?)',(source,r['source_row'],'INCOMPLETE_IDENTITY'))
            else:grouped[key].append(r)
        for (key,payload),matches in grouped.items():
            if len(matches)!=1:
                for r in matches:con.execute('insert into defects_observed_current values(?,?,?,?)',(source,r['source_row'],key,'AMBIGUOUS_IDENTITY'))
                continue
            r=matches[0];status=(r['status_raw'] or '').strip();comment=r['status_comment_raw'] or ''
            old=con.execute('select first_observed_at,last_observed_at,last_seen_run,last_status,last_comment,status_changed_at,comment_changed_at from defects_observed_entity where entity_key=?',(key,)).fetchone()
            kind=None;status_change=None;comment_change=None
            if old is None:
                kind='BASELINE' if baseline else 'FIRST_SEEN'
                first=observed_at
            else:
                first=old[0]
                continuous=old[2]==previous_run and previous_quality.get(key)=='UNIQUE'
                status_change,comment_change=old[5],old[6]
                if not continuous:
                    kind='TRACKING_RESUMED'
                    # After duplicate/reappearance gaps do not date the current state
                    # from a potentially different member of the same identity group.
                    status_change=None;comment_change=None
                elif status!=old[3]:
                    kind='STATUS_CHANGED';status_change=observed_at
                    if comment!=old[4]:comment_change=observed_at
                elif comment!=old[4]:
                    kind='COMMENT_CHANGED';comment_change=observed_at
            if kind:
                con.execute('insert into defects_status_event(entity_key,source,source_row,run_id,event_kind,observed_at_utc,observed_date_moscow,previous_observed_at,old_status,new_status,old_comment,new_comment) values(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (key,source,r['source_row'],run,kind,observed_at,day,old[1] if old else None,old[3] if old else None,status,old[4] if old else None,comment))
            con.execute('insert into defects_observed_entity values(?,?,?,?,?,?,?,?,?,?) on conflict(entity_key) do update set last_observed_at=excluded.last_observed_at,last_seen_run=excluded.last_seen_run,last_status=excluded.last_status,last_comment=excluded.last_comment,status_changed_at=excluded.status_changed_at,comment_changed_at=excluded.comment_changed_at',
                (key,source,payload,first,observed_at,run,status,comment,status_change,comment_change))
            con.execute('insert into defects_observed_current values(?,?,?,?)',(source,r['source_row'],key,'UNIQUE'))

def initialize_baseline(con):
    """Seed the installed catalog from its last known successful observation.

    Does not reconstruct past transitions or backdate 'resolved'.
    """
    if con.execute('select count(*) from defects_observed_current').fetchone()[0]:return
    previous=con.execute("select id,finished_at from defects_run where status='success' order by id desc limit 1").fetchone()
    if not previous:return
    records={'main':[],'laser':[]}
    for source,payload in con.execute('select source,record_json from defects_source_row where is_current=1'):
        records[source].append(json.loads(payload))
    observe(con,records,run=previous[0],observed_at=previous[1],previous_run=None,baseline=True)

def history_for_row(con,source,row):
    r=con.execute('select entity_key,tracking_quality from defects_observed_current where source=? and source_row=?',(source,row)).fetchone()
    if not r:return {'tracking_quality':'UNAVAILABLE','status_changed_at':None,'events':[]}
    if r[1]!='UNIQUE':return {'tracking_quality':r[1],'status_changed_at':None,'events':[]}
    old_factory=con.row_factory;con.row_factory=None
    try:
        entity=con.execute('select first_observed_at,last_observed_at,status_changed_at,comment_changed_at from defects_observed_entity where entity_key=?',(r[0],)).fetchone()
        cols=['event_kind','observed_at_utc','observed_date_moscow','previous_observed_at','old_status','new_status','old_comment','new_comment']
        events=[dict(zip(cols,x)) for x in con.execute('select '+','.join(cols)+' from defects_status_event where entity_key=? order by id',(r[0],))]
    finally:con.row_factory=old_factory
    changed=entity[2]
    day=datetime.fromisoformat(changed.replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat() if changed else None
    return {'tracking_quality':'UNIQUE','first_observed_at':entity[0],'last_observed_at':entity[1],
        'status_changed_at':changed,'status_change_observed_date_moscow':day,
        'comment_changed_at':entity[3],'actual_resolution_date_known':False,'events':events}

def verify_observations(con,records,run):
    expected={(source,r['source_row']) for source,rows in records.items() for r in rows}
    assert set(con.execute('select source,source_row from defects_observed_current'))==expected
    for source,rows in records.items():
        groups=defaultdict(list)
        for r in rows:
            key=identity(r)
            if key:groups[key[0]].append(r)
        for r in rows:
            key=identity(r)
            quality='INCOMPLETE_IDENTITY' if key is None else ('UNIQUE' if len(groups[key[0]])==1 else 'AMBIGUOUS_IDENTITY')
            actual=con.execute('select entity_key,tracking_quality from defects_observed_current where source=? and source_row=?',(source,r['source_row'])).fetchone()
            assert actual==(key[0] if key else None,quality)
            if quality=='UNIQUE':
                state=con.execute('select last_seen_run,last_status,last_comment from defects_observed_entity where entity_key=?',(key[0],)).fetchone()
                assert state==(run,(r['status_raw'] or '').strip(),r['status_comment_raw'] or '')
