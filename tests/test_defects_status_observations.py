import copy
from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import unittest
from unittest.mock import patch
from apps.msp_defects_catalog.sync import HEADERS,SCHEMA,parse_rows,store_snapshot,encode,digest

def records(status='',comment='',article='A',offset=0):
    row=['']*14;row[1]='ВБ UW';row[2]='Дерево';row[4]=article
    row[6]='01.11.2026';row[8]='fixture complaint';row[11]=status;row[13]=comment
    return {'main':parse_rows('main',[HEADERS['main'],*([[]]*offset),row]),'laser':[]}

class StatusObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'test.sqlite3'

    def save(self,data,stamp):
        with patch('apps.msp_defects_catalog.sync.now',return_value=stamp):
            return store_snapshot(self.db,data,stamp)

    def events(self):
        with closing(sqlite3.connect(self.db)) as c, c:
            c.row_factory=sqlite3.Row
            return [dict(x) for x in c.execute('select * from defects_status_event order by id')]

    def test_baseline_resolved_is_not_a_dated_resolution(self):
        self.save(records('Решено'),'2026-11-12T06:00:00+00:00')
        e=self.events();self.assertEqual([x['event_kind'] for x in e],['BASELINE'])
        with closing(sqlite3.connect(self.db)) as c, c:
            self.assertIsNone(c.execute('select status_changed_at from defects_observed_entity').fetchone()[0])

    def test_actual_change_has_moscow_date_and_previous_observation_boundary(self):
        self.save(records('Зависло'),'2026-11-12T06:00:00+00:00')
        self.save(records('Решено'),'2026-11-12T22:30:00+00:00')
        e=self.events()[-1]
        self.assertEqual(e['event_kind'],'STATUS_CHANGED')
        self.assertEqual(e['observed_date_moscow'],'2026-11-13')
        self.assertEqual(e['previous_observed_at'],'2026-11-12T06:00:00+00:00')
        self.assertEqual((e['old_status'],e['new_status']),('Зависло','Решено'))

    def test_reorder_and_repeat_do_not_create_status_events(self):
        self.save(records('Решено'),'2026-11-12T06:00:00+00:00')
        self.save(records('Решено',offset=3),'2026-11-13T06:00:00+00:00')
        self.save(records('Решено',offset=3),'2026-11-14T06:00:00+00:00')
        self.assertEqual(len(self.events()),1)

    def test_comment_change_does_not_set_status_change_date(self):
        self.save(records('Решено','old'),'2026-11-12T06:00:00+00:00')
        self.save(records('Решено','new'),'2026-11-13T06:00:00+00:00')
        self.assertEqual(self.events()[-1]['event_kind'],'COMMENT_CHANGED')
        with closing(sqlite3.connect(self.db)) as c, c:
            self.assertIsNone(c.execute('select status_changed_at from defects_observed_entity').fetchone()[0])

    def test_new_row_is_first_seen_not_a_status_transition(self):
        self.save(records('Зависло'),'2026-11-12T06:00:00+00:00')
        self.save(records('Решено',article='B'),'2026-11-13T06:00:00+00:00')
        self.assertEqual(self.events()[-1]['event_kind'],'FIRST_SEEN')

    def test_duplicate_and_reappearance_do_not_infer_change(self):
        data=records('Зависло');dup=copy.deepcopy(data);dup['main'].append(copy.deepcopy(dup['main'][0]));dup['main'][1]['source_row']=3
        self.save(data,'2026-11-12T06:00:00+00:00')
        self.save(dup,'2026-11-13T06:00:00+00:00')
        self.save(records('Решено'),'2026-11-14T06:00:00+00:00')
        self.assertEqual(self.events()[-1]['event_kind'],'TRACKING_RESUMED')
        self.assertFalse(any(x['event_kind']=='STATUS_CHANGED' for x in self.events()))

    def test_existing_catalog_migration_baselines_prior_observation(self):
        data=records('Решено');record=data['main'][0]
        with closing(sqlite3.connect(self.db)) as c, c:
            c.executescript(SCHEMA)
            c.execute("insert into defects_run values(1,?,?, 'success','old',null)",('2026-11-12T06:00:00+00:00','2026-11-12T06:00:01+00:00'))
            c.execute('insert into defects_source_row values(?,?,?,?,1,1)',('main',2,encode(record),digest(record)))
        self.save(data,'2026-11-13T06:00:00+00:00')
        e=self.events()
        self.assertEqual(len(e),1)
        self.assertEqual(e[0]['event_kind'],'BASELINE')
        self.assertEqual(e[0]['observed_at_utc'],'2026-11-12T06:00:01+00:00')

    def test_status_cleared_is_recorded_but_not_resolved(self):
        self.save(records('Решено'),'2026-11-12T06:00:00+00:00')
        self.save(records(''),'2026-11-13T06:00:00+00:00')
        self.assertEqual(self.events()[-1]['new_status'],'')
        self.assertEqual(self.events()[-1]['event_kind'],'STATUS_CHANGED')
