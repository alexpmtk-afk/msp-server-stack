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
    vals={1:"21.10.2026",2:"5,0. млн. руб.",3:"0,2. млн. руб.",
          4:"1 234 567",5:"1 200 000",6:"🟡 +4%",8:"50 000",
          9:"🟡 +1%",12:"2,0. млн. руб.",13:"300 тыс. руб.",
          14:"1 100 000",15:"1 000 000",16:"🟢 +10%",
          18:"-25 000",19:"🔴 -1%",25:"3 400 000",
          26:"99 000",28:"2 100 000",29:"-20 000"}
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
            self.assertEqual(m.latest(conn,"2026-10-21")[1]["cells"]["B18"],"-25 000")
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            changed=rows();changed[3][1]="1 234 568"
            self.assertEqual(m.save(conn,m.snapshot(changed))["revision"],2)
    def test_unicode_space_amounts(self):
        data=rows()
        data[3][1]="1\u00a0234\u202f567"
        parsed=m.snapshot(data)
        self.assertEqual(m.num(parsed["cells"]["B4"]),1234567)
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
        self.assertNotIn("laser_30_margin_pct",a["unknown"])
    def test_laser_30_day_margin_formula(self):
        a=m.snapshot(rows())
        c=a["cells"]
        margin=round(m.num(c["B29"])/m.num(c["B28"])*100)
        self.assertEqual(margin,-1)
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(m.render(a,Path(d)/"with_margin.png").is_file())
if __name__=="__main__":unittest.main()
