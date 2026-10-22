import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
import sys

source=Path(__file__).resolve().parents[1]/"apps/msp_daily_reports/daily.py"
spec=importlib.util.spec_from_file_location("msp_daily_report",source)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def rows():
    a=[["",""] for _ in range(30)]
    vals={1:"21.10.2026",2:"9,0. млн. руб.",3:"0,5. млн. руб.",
          4:"6 341 181",5:"6 096 774",6:"🟡 +4%",8:"76 811",
          9:"🟡 +1%",12:"3,0. млн. руб.",13:"700 тыс. руб.",
          14:"1 583 188",15:"2 032 258",16:"🔴 -22%",
          18:"-211 184",19:"🔴 -9%",25:"9 946 142",
          26:"299 851",28:"2 362 147",29:"-188 357"}
    for k,v in vals.items():a[k-1][1]=v
    return a

class TestReports(unittest.TestCase):
    def test_capture_and_idempotency(self):
        with tempfile.TemporaryDirectory() as d:
            conn=m.dbopen(Path(d)/"report.sqlite3")
            snap=m.snapshot(rows())
            self.assertEqual(snap["date"],"2026-10-21")
            self.assertEqual(m.save(conn,snap)["status"],"inserted")
            self.assertEqual(m.save(conn,snap)["status"],"unchanged")
            self.assertEqual(m.latest(conn,"2026-10-21")[1]["cells"]["B18"],"-211 184")
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            changed=rows();changed[3][1]="6 341 182"
            self.assertEqual(m.save(conn,m.snapshot(changed))["revision"],2)
    def test_unicode_space_amounts(self):
        data=rows()
        data[3][1]="6\u00a0341\u202f181"
        parsed=m.snapshot(data)
        self.assertEqual(m.num(parsed["cells"]["B4"]),6341181)
    def test_missing_required(self):
        a=rows();a[13][1]=""
        with self.assertRaisesRegex(ValueError,"B14"):
            m.snapshot(a)
    def test_render(self):
        with tempfile.TemporaryDirectory() as d:
            p=m.render(m.snapshot(rows()),Path(d)/"preview.png")
            from PIL import Image
            with Image.open(p) as image:
                self.assertEqual(image.size,(643,533))
    def test_no_unknown_percent_invented(self):
        a=m.snapshot(rows())
        self.assertIn("laser_30_plan_fact_pct",a["unknown"])
        self.assertIn("laser_30_margin_pct",a["unknown"])
if __name__=="__main__":unittest.main()
