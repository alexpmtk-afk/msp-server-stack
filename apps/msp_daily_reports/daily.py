#!/usr/bin/env python3
"""Daily read-only report snapshot from Google Sheet План-Факт A1:B30.

Only persists in /opt/mcp/data; Telegram emission is manually gated.
"""
import argparse,csv,hashlib,io,json,os,re,sqlite3,urllib.request
from datetime import datetime,timezone
from pathlib import Path

SHEET_ID=os.environ.get("MSP_REPORT_SHEET_ID","")
GID=int(os.environ.get("MSP_REPORT_GID","0"))
DB=os.environ.get("MSP_REPORT_DB","/opt/mcp/data/reports/msp_reports.sqlite3")
REQUIRED=(1,2,3,4,5,6,8,9,12,13,14,15,16,18,19,25,26,28,29)
SCHEMA="""
CREATE TABLE IF NOT EXISTS report_snapshot(
 id INTEGER PRIMARY KEY,report_date TEXT NOT NULL,revision INTEGER NOT NULL,
 collected_utc TEXT NOT NULL,source_sheet_id TEXT NOT NULL,source_gid INTEGER NOT NULL,
 digest TEXT NOT NULL,payload TEXT NOT NULL,
 UNIQUE(report_date,revision),UNIQUE(report_date,digest));
CREATE TABLE IF NOT EXISTS report_delivery(
 snapshot_id INTEGER NOT NULL REFERENCES report_snapshot(id),
 chat_id TEXT NOT NULL,thread_id INTEGER NOT NULL,message_id INTEGER NOT NULL,
 sent_utc TEXT NOT NULL,PRIMARY KEY(snapshot_id,chat_id,thread_id));
"""

def dbopen(path=DB):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(p);db.row_factory=sqlite3.Row
 db.execute("PRAGMA foreign_keys=ON");db.executescript(SCHEMA);os.chmod(p,0o600)
 return db

def source_rows():
 """Google Sheets read-only via existing authorized CSV export or protected Sheets API.
 Do not open private spreadsheets to the public just to satisfy this importer.
 """
 url=os.environ.get("MSP_REPORT_SOURCE_URL")
 if url:
  req=urllib.request.Request(url,headers={"User-Agent":"msp-daily-reports/1.0"})
  with urllib.request.urlopen(req,timeout=40) as response:
   mime=response.headers.get("Content-Type","").lower()
   body=response.read(8_000_001)
  if len(body)>8_000_000 or b"<html" in body[:1000].lower() or "text/html" in mime:
   raise RuntimeError("Missing authorization, bad CSV content, or oversized source")
  return list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))[:30]
 credentials=os.environ.get("MSP_REPORT_GOOGLE_CREDENTIALS_FILE")
 if not credentials:raise RuntimeError("Need existing authorized CSV URL or read-only service-account credentials")
 try:
  from google.oauth2 import service_account
  from google.auth.transport.requests import Request
 except ImportError as e:
  raise RuntimeError("google-auth is required for service-account mode") from e
 creds=service_account.Credentials.from_service_account_file(
  credentials,scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
 creds.refresh(Request())
 from urllib.parse import quote
 endpoint="https://sheets.googleapis.com/v4/spreadsheets/"+quote(SHEET_ID)+"/values/"+quote("'План-Факт'!A1:B30",safe="")+"?valueRenderOption=FORMATTED_VALUE"
 req=urllib.request.Request(endpoint,headers={"Authorization":"Bearer "+creds.token})
 with urllib.request.urlopen(req,timeout=35) as response:
  return json.load(response).get("values",[])

def norm(value):
 return "" if value is None else str(value).strip()

def snapshot(rows):
 if len(rows)<29:raise ValueError("A1:B30 source incomplete")
 def get(row):
  return norm(rows[row-1][1]) if len(rows[row-1])>1 else ""
 for row in REQUIRED:
  if not get(row):raise ValueError("missing B"+str(row))
 try:date=datetime.strptime(get(1),"%d.%m.%Y").date().isoformat()
 except ValueError as e:raise ValueError("bad B1 date") from e
 for row in (4,5,8,14,15,18,25,26,28,29):
  if not re.fullmatch(r"-?[0-9]+",re.sub(r"[\s\u00a0\u202f]","",get(row))):raise ValueError("bad numeric B"+str(row))
 for row in (6,9,16,19):
  if not re.search(r"[+-]?\d+%$",get(row)):raise ValueError("bad percentage B"+str(row))
 return {"date":date,"source":{"id":SHEET_ID,"gid":GID,"range":"A1:B30"},
         "cells":{"B"+str(i):get(i) for i in range(1,31)},
         "unknown":["laser_30_plan_fact_pct","laser_30_margin_pct"]}

def save(db,payload):
 body=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"))
 digest=hashlib.sha256(body.encode()).hexdigest();date=payload["date"]
 with db:
  existing=db.execute("SELECT id,revision FROM report_snapshot WHERE report_date=? AND digest=?",(date,digest)).fetchone()
  if existing:return {"status":"unchanged","date":date,"revision":existing["revision"]}
  rev=db.execute("SELECT COALESCE(MAX(revision),0)+1 FROM report_snapshot WHERE report_date=?",(date,)).fetchone()[0]
  db.execute("INSERT INTO report_snapshot(report_date,revision,collected_utc,source_sheet_id,source_gid,digest,payload) VALUES(?,?,?,?,?,?,?)",
   (date,rev,datetime.now(timezone.utc).isoformat(),SHEET_ID,GID,digest,body))
 return {"status":"inserted","date":date,"revision":rev}

def latest(db,date=None):
 if date:
  row=db.execute("SELECT * FROM report_snapshot WHERE report_date=? ORDER BY revision DESC LIMIT 1",(date,)).fetchone()
 else:
  row=db.execute("SELECT * FROM report_snapshot ORDER BY report_date DESC,revision DESC LIMIT 1").fetchone()
 if row is None:raise RuntimeError("Snapshot not found")
 return row,json.loads(row["payload"])

def num(v):
 """Numeric cells of daily source, with non-breaking spaces."""
 return int(re.sub(r"[\s\u00a0\u202f]","",str(v)))
def unit(v):
 s=str(v).strip()
 m=re.search(r"(-?\d+[,.]?\d*)\.?\s*(млн|тыс)",s)
 if m:return round(float(m.group(1).replace(",","."))*(1000000 if m.group(2)=="млн" else 1000))
 return num(s)
def money(n):return f"{n:,}".replace(","," ")

def render(data,dest):
 from PIL import Image,ImageDraw,ImageFont
 font_root=Path("/usr/share/fonts/truetype/liberation2")
 if not font_root.is_dir():font_root=Path("/usr/share/fonts/truetype/liberation")
 if not font_root.is_dir():font_root=Path("/usr/share/fonts/truetype/dejavu")
 dejavu="dejavu" in str(font_root)
 fonts={"r":"DejaVuSans.ttf" if dejavu else "LiberationSans-Regular.ttf",
        "b":"DejaVuSans-Bold.ttf" if dejavu else "LiberationSans-Bold.ttf",
        "i":"DejaVuSans-Oblique.ttf" if dejavu else "LiberationSans-Italic.ttf"}
 font={k:ImageFont.truetype(str(font_root/f),16 if k!="r" else 17) for k,f in fonts.items()}
 im=Image.new("RGB",(643,533),"white");d=ImageDraw.Draw(im)
 for x in (0,247,408,443,639,642):d.line((x,0,x,532),fill="#dedede")
 for y in (0,31,61,91,121,151,180,210,239,268,297,327,358,386,415,446,475,505,532):d.line((0,y,642,y),fill="#dedede")
 d.rectangle((408,0,443,209),fill="#686868");d.rectangle((0,210,639,239),fill="#686868")
 def txt(value,y,x=5,style="r",right=None,center=None,color="black"):
  v=str(value);length=d.textbbox((0,0),v,font=font[style])[2]
  if right is not None:x=right-length
  if center is not None:x=center-length/2
  d.text((int(x),y),v,font=font[style],fill=color)
 def pct(value,y,center):
  m=re.search(r"([🟡🟢🔴])\s*([+-]?\d+%)",str(value))
  if not m:txt("—",y,center=center,style="b");return
  span=d.textbbox((0,0),m.group(2),font=font["b"])[2]
  left=int(center-(span+33)/2)
  d.ellipse((left,y-2,left+20,y+18),fill={"🟡":"#fff000","🟢":"#15a568","🔴":"#ed1c24"}[m.group(1)],outline="black",width=2)
  txt(m.group(2),y-2,x=left+26,style="b")
 c=data["cells"];v=lambda n:c.get("B"+str(n),"")
 date=datetime.strptime(data["date"],"%Y-%m-%d")
 txt(date.strftime("%d.%m.%Y"),6,style="b",right=404,color="#990000")
 txt("Динамика 30 дней",6,x=456,style="b",color="#990000")
 txt("Реализация факт:",39);txt(money(num(v(4))),39,right=403,style="b")
 txt("План на дату:",69);txt(money(num(v(5))),69,right=403)
 d.rectangle((0,90,407,180),outline="black",width=2)
 txt("Прогноз на конец месяца:",98,style="b")
 txt("Прибыль;",128);txt(money(num(v(8))),128,style="b",right=360)
 txt("Рентабельность:",158);pct(v(9),154,328)
 txt("р."+money(num(v(25))),39,style="b",center=543)
 txt("р."+money(unit(v(2))),69,center=543)
 d.rectangle((443,90,638,180),outline="black",width=2)
 txt(money(num(v(26))),128,style="b",center=543)
 margin=round(num(v(26))/num(v(25))*100) if num(v(25)) else None
 pct(("🟡 " if margin is not None and margin>=0 else "🔴 ")+str(margin)+"%" if margin is not None else None,154,543)
 months="январь февраль март апрель май июнь июль август сентябрь октябрь ноябрь декабрь".split()
 txt("План Л-М на "+months[date.month-1],245,style="i")
 compact=lambda n:f"{n/1e6:.1f}".replace(".",",")+" млн. руб." if n>=1000000 else f"{n//1000} тыс. руб."
 txt(compact(unit(v(12))),245,right=403,style="i")
 txt("Прибыль",275,style="i");txt(compact(unit(v(13))),275,right=403,style="i")
 txt("К перечислению факт:",305);txt(money(num(v(14))),305,style="b",right=403)
 txt("План на дату:",335);txt(money(num(v(15))),335,right=403)
 txt("План-факт:",364);pct(v(16),362,352)
 d.rectangle((0,386,407,475),outline="black",width=2)
 txt("Прогноз на конец месяца:",394,style="b")
 txt("Прибыль;",423);txt(money(num(v(18))),423,style="b",right=362)
 txt("Рентабельность:",452);pct(v(19),451,352)
 txt(compact(unit(v(12))),245,style="i",center=543)
 txt(compact(unit(v(13))),275,style="i",center=543)
 txt("р."+money(num(v(28))),305,style="b",center=543)
 txt("р."+money(unit(v(12))),335,center=543)
 txt("—",363,style="b",center=543)
 d.rectangle((443,386,638,475),outline="black",width=2)
 txt(money(num(v(29))),423,style="b",center=543)
 txt("—",452,style="b",center=543)
 dst=Path(dest);dst.parent.mkdir(parents=True,exist_ok=True);im.save(dst,"PNG")
 return dst

def send_manual(db,row,path,chat,thread,token,confirm=False):
 if not confirm:raise RuntimeError("Explicit --confirm required")
 if not token:raise RuntimeError("No protected bot token")
 if db.execute("SELECT 1 FROM report_delivery WHERE snapshot_id=? AND chat_id=? AND thread_id=?",(row["id"],str(chat),int(thread))).fetchone():
  return {"status":"already_sent"}
 boundary="--msp-report"
 fields={"chat_id":str(chat),"message_thread_id":str(thread),"disable_notification":"true"}
 body=b""
 for key,val in fields.items():
  body+=(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{val}\r\n").encode()
 body+=(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"report.png\"\r\nContent-Type: image/png\r\n\r\n").encode()+Path(path).read_bytes()+b"\r\n"
 body+=(f"--{boundary}--\r\n").encode()
 req=urllib.request.Request("https://api.telegram.org/bot"+token+"/sendPhoto",data=body,
  headers={"Content-Type":"multipart/form-data; boundary="+boundary},method="POST")
 try:
  with urllib.request.urlopen(req,timeout=35) as resp:result=json.load(resp)
 except Exception:raise RuntimeError("Telegram delivery error (secret redacted)") from None
 if not result.get("ok") or str(result.get("result",{}).get("chat",{}).get("id"))!=str(chat):
  raise RuntimeError("Telegram chat not confirmed")
 mid=int(result["result"]["message_id"])
 with db:
  db.execute("INSERT INTO report_delivery VALUES(?,?,?,?,?)",(row["id"],str(chat),int(thread),mid,datetime.now(timezone.utc).isoformat()))
 return {"status":"sent","message_id":mid}

def main():
 p=argparse.ArgumentParser()
 p.add_argument("command",choices=("sync","render","history","send"))
 p.add_argument("--date");p.add_argument("--out",default="/opt/mcp/data/reports/report.png")
 p.add_argument("--source-json");p.add_argument("--chat-id");p.add_argument("--thread-id",type=int)
 p.add_argument("--confirm",action="store_true")
 args=p.parse_args();db=dbopen()
 if args.command=="sync":
  rows=json.load(open(args.source_json,encoding="utf8"))["values"] if args.source_json else source_rows()
  print(json.dumps(save(db,snapshot(rows)),ensure_ascii=False))
 else:
  row,data=latest(db,args.date)
  if args.command=="history":print(json.dumps({"date":row["report_date"],"revision":row["revision"],"cells":data["cells"]},ensure_ascii=False))
  elif args.command=="render":print(json.dumps({"path":str(render(data,args.out))},ensure_ascii=False))
  else:
   if not args.chat_id or args.thread_id is None:raise RuntimeError("Explicit target required")
   path=render(data,args.out)
   print(json.dumps(send_manual(db,row,path,args.chat_id,args.thread_id,os.environ.get("MSP_REPORT_TELEGRAM_TOKEN"),args.confirm)))
if __name__=="__main__":main()
