#!/usr/bin/env python3
"""Read-only Google report reader and local SQL instruction catalog.

Source locators/credentials and live data are never part of this public module.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import urllib.parse

ROOT = Path('/home/hermes/.local/share/msp/approved-reports')
CONFIG = ROOT / 'registry.json'
DB = Path('/opt/mcp/data/msp/msp_report_catalog.sqlite3')
AUTH_MODULE = Path('/home/hermes/.hermes/google-drive/drive_audit.py')


def column_name(number):
    result = ''
    while number:
        number, digit = divmod(number - 1, 26)
        result = chr(65 + digit) + result
    return result


def validate_range(value):
    match = re.fullmatch(r'([A-Z]+)([1-9]\d*):([A-Z]+)([1-9]\d*)', value)
    if not match:
        raise ValueError('Use a bounded cell-only range, for example A1:H20')
    def index(letters):
        total = 0
        for char in letters:
            total = total * 26 + ord(char) - 64
        return total
    a, first, b, last = match.groups()
    width, height = index(b) - index(a) + 1, int(last) - int(first) + 1
    if min(width, height) <= 0 or width * height > 10000:
        raise ValueError('Range reversed or exceeds 10000 cells; read smaller chunks')
    return value


def load_report(path, report_id):
    config = json.loads(Path(path).read_text())
    if report_id == 'orders':
        report_id = 'mp_customer_orders_daily_weekly_monthly'
    matches = [r for r in config['reports'] if r['report_id'] == report_id]
    if len(matches) != 1:
        raise ValueError('Report is not uniquely registered; do not search Drive for substitutes')
    report = matches[0]
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,100}', report['spreadsheet_id']):
        raise ValueError('Invalid registered spreadsheet ID')
    return report


class GoogleReader:
    def __init__(self):
        spec = importlib.util.spec_from_file_location('approved_report_readonly_auth', AUTH_MODULE)
        self.transport = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.transport)
        self.headers = {'Authorization': 'Bearer ' + self.transport.auth()}

    def get(self, spreadsheet_id, suffix='', params=None):
        # Only fixed Google Sheets GET endpoints, using existing readonly auth.
        url = 'https://sheets.googleapis.com/v4/spreadsheets/' + spreadsheet_id + suffix
        if params:
            url += '?' + urllib.parse.urlencode(params, doseq=True)
        return self.transport.call(url, headers=self.headers)

    def metadata(self, report):
        return self.get(report['spreadsheet_id'], params={'fields':
            'spreadsheetId,properties(title,locale,timeZone),sheets(properties(sheetId,title,gridProperties))'})


def resolve_sheet(report, metadata, title):
    allowed = [s for s in report['sheets'] if s['title'] == title]
    live = [s['properties'] for s in metadata['sheets'] if s['properties']['title'] == title]
    if len(allowed) != 1 or len(live) != 1 or live[0]['sheetId'] != allowed[0]['sheet_id']:
        raise ValueError('Sheet not approved, renamed or gid changed; review the registry')
    return live[0]


def read_range(reader, report, title, value_range):
    validate_range(value_range)
    # Deny unknown tabs before credentials/network use whenever possible.
    if title not in {s['title'] for s in report['sheets']}:
        raise ValueError('Sheet is not approved for this report')
    metadata = reader.metadata(report)
    sheet = resolve_sheet(report, metadata, title)
    quoted = "'" + title.replace("'", "''") + "'!" + value_range
    values = reader.get(report['spreadsheet_id'], '/values/' + urllib.parse.quote(quoted, safe=''),
                        {'valueRenderOption': 'FORMATTED_VALUE'})
    return dict(report_id=report['report_id'], sheet_id=sheet['sheetId'],
                sheet=title, timezone=metadata['properties'].get('timeZone'),
                retrieved_at_utc=datetime.now(timezone.utc).isoformat(), data=values,
                note='Retrieval time is not business-data freshness; source was not modified.')


def write_catalog(connection, report, metadata, header_ranges, instructions, verified_at):
    connection.execute('PRAGMA foreign_keys=ON')
    connection.executescript('''
    CREATE TABLE IF NOT EXISTS report_source(
      report_id TEXT PRIMARY KEY,title TEXT,spreadsheet_id TEXT,source_url TEXT,
      timezone TEXT,access_method TEXT,verified_at_utc TEXT,
      data_materialized INTEGER NOT NULL CHECK(data_materialized=0));
    CREATE TABLE IF NOT EXISTS report_sheet(
      report_id TEXT,sheet_id INTEGER,title TEXT,purpose TEXT,fulfillment TEXT,
      grain TEXT,metrics TEXT,grid_rows INTEGER,grid_columns INTEGER,
      PRIMARY KEY(report_id,sheet_id),FOREIGN KEY(report_id) REFERENCES report_source(report_id));
    CREATE TABLE IF NOT EXISTS report_column(
      report_id TEXT,sheet_id INTEGER,column_index INTEGER,column_letter TEXT,header TEXT,
      PRIMARY KEY(report_id,sheet_id,column_index),
      FOREIGN KEY(report_id,sheet_id) REFERENCES report_sheet(report_id,sheet_id));
    CREATE TABLE IF NOT EXISTS report_instruction(
      report_id TEXT,rule_order INTEGER,instruction TEXT,
      PRIMARY KEY(report_id,rule_order),FOREIGN KEY(report_id) REFERENCES report_source(report_id));
    CREATE TABLE IF NOT EXISTS report_guide(
      report_id TEXT PRIMARY KEY,markdown TEXT,
      FOREIGN KEY(report_id) REFERENCES report_source(report_id));
    ''')
    rid = report['report_id']
    with connection:
        connection.execute('INSERT INTO report_source VALUES(?,?,?,?,?,?,?,0) '
                           'ON CONFLICT(report_id) DO UPDATE SET title=excluded.title,spreadsheet_id=excluded.spreadsheet_id,'
                           'source_url=excluded.source_url,timezone=excluded.timezone,access_method=excluded.access_method,'
                           'verified_at_utc=excluded.verified_at_utc',
            (rid, metadata['properties']['title'], report['spreadsheet_id'],
             'https://docs.google.com/spreadsheets/d/' + report['spreadsheet_id'] + '/edit',
             metadata['properties'].get('timeZone'), 'server_service_account_drive_readonly', verified_at))
        for table in ('report_column', 'report_sheet', 'report_instruction', 'report_guide'):
            connection.execute('DELETE FROM ' + table + ' WHERE report_id=?', (rid,))
        for configured, headers in zip(report['sheets'], header_ranges, strict=True):
            live = resolve_sheet(report, metadata, configured['title'])
            grid = live['gridProperties']
            connection.execute('INSERT INTO report_sheet VALUES(?,?,?,?,?,?,?,?,?)',
                (rid, live['sheetId'], live['title'], configured['purpose'], configured['fulfillment'],
                 configured['grain'], configured['metrics'], grid['rowCount'], grid['columnCount']))
            for index, header in enumerate(headers, 1):
                connection.execute('INSERT INTO report_column VALUES(?,?,?,?,?)',
                    (rid, live['sheetId'], index, column_name(index), str(header)))
        for index, rule in enumerate(report['rules'], 1):
            connection.execute('INSERT INTO report_instruction VALUES(?,?,?)', (rid, index, rule))
        connection.execute('INSERT INTO report_guide VALUES(?,?)', (rid, instructions))


def refresh(reader, report, database, instructions):
    meta = reader.metadata(report)
    ranges = []
    for sheet in report['sheets']:
        live = resolve_sheet(report, meta, sheet['title'])
        ranges.append("'" + sheet['title'].replace("'", "''") + "'!A1:" +
                      column_name(live['gridProperties']['columnCount']) + '1')
    response = reader.get(report['spreadsheet_id'], '/values:batchGet',
                          {'ranges': ranges, 'valueRenderOption': 'FORMATTED_VALUE'})
    values = response.get('valueRanges', [])
    if len(values) != len(ranges) or any(not v.get('values') for v in values):
        raise ValueError('Not all approved sheet headers were read; catalog unchanged')
    with closing(sqlite3.connect(database)) as connection:
        write_catalog(connection, report, meta, [v['values'][0] for v in values], instructions,
                      datetime.now(timezone.utc).isoformat())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['list', 'guide', 'read', 'refresh'])
    p.add_argument('--report', default='orders')
    p.add_argument('--config', type=Path, default=CONFIG)
    p.add_argument('--database', type=Path, default=DB)
    p.add_argument('--sheet')
    p.add_argument('--range', dest='value_range')
    p.add_argument('--instructions', type=Path, default=ROOT / 'GUIDE.md')
    a = p.parse_args()
    report = load_report(a.config, a.report)
    if a.command in ('list', 'guide'):
        with closing(sqlite3.connect('file:' + str(a.database) + '?mode=ro', uri=True)) as c:
            c.row_factory = sqlite3.Row
            if a.command == 'list':
                print(json.dumps([dict(v) for v in c.execute('SELECT * FROM report_source')], ensure_ascii=False))
            else:
                row = c.execute('SELECT markdown FROM report_guide WHERE report_id=?', (report['report_id'],)).fetchone()
                if not row:
                    raise ValueError('Report guide not installed in SQL')
                print(row[0])
    elif a.command == 'read':
        if not a.sheet or not a.value_range:
            raise ValueError('Provide --sheet and bounded --range')
        validate_range(a.value_range)
        if a.sheet not in {s['title'] for s in report['sheets']}:
            raise ValueError('Unapproved sheet; do not search for a replacement')
        print(json.dumps(read_range(GoogleReader(), report, a.sheet, a.value_range), ensure_ascii=False))
    else:
        refresh(GoogleReader(), report, a.database, a.instructions.read_text())
        print('VERIFIED_SQL_GUIDE_INSTALLED; GOOGLE_WRITES=0; BUSINESS_ROWS_IMPORTED=0; SCHEDULES_CHANGED=0')


if __name__ == '__main__':
    main()
