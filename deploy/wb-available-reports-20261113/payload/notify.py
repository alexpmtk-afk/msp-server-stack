"""One fixed text notice to the established Remote Server finance topic.

Called as hermes, not root. Does not poll updates, modify Gateway or use models.
"""
import hashlib,json,os,re,sys,urllib.request,urllib.parse
from pathlib import Path
CHAT=-1002485321031
THREAD=758
NAMES={'wb_dmitrieva':'ИП Дмитриева','wb_novokshenov':'ИП Новокшенов','wb_laser_master':'Лазер-мастер'}
def message(period,cabinet,start,end,attempts,missing):
    import datetime
    if cabinet not in NAMES or period not in ('daily','weekly') or attempts!=(3 if period=='daily' else 10) or missing not in ('1','2','1,2'):raise ValueError('notice scope')
    if datetime.date.fromisoformat(start)>datetime.date.fromisoformat(end):raise ValueError('notice period')
    if period=='daily' and start!=end:raise ValueError('daily scope')
    types=', '.join('основной' if t=='1' else 'выкупы WB' for t in missing.split(','))
    reason='не получено ни одного готового отчёта за период' if missing=='1,2' else ('основной отчёт указан в списке WB, но его загрузка не завершена' if missing=='1' else 'отчёт по выкупам указан в списке WB, но его загрузка не завершена')
    return ('Wildberries — '+NAMES[cabinet]+': '+('дневной' if period=='daily' else 'недельный')+' отчёт за '+start+(' — '+end if start!=end else '')+' не скачан ('+types+'): '+reason+'. Проверок: '+str(attempts)+'. Готовые отчёты сохранены; загрузчик перешёл в ожидание следующего запуска.')

def token():
    # Read only token assignments, never shell-evaluate the env file or expose it.
    values={}
    for line in (Path('/home/hermes/.hermes/.env').read_text()).splitlines():
        key,sep,value=line.strip().removeprefix('export ').partition('=')
        if sep and key in ('MSP_ALERT_BOT_TOKEN','TELEGRAM_BOT_TOKEN'):
            value=value.strip()
            if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
            values[key]=value
    out=values.get('MSP_ALERT_BOT_TOKEN') or values.get('TELEGRAM_BOT_TOKEN','')
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+',out):raise ValueError('bot credential unavailable')
    return out

def send(period,cabinet,start,end,attempts,missing,*,opener=None,bot_token=None):
    text=message(period,cabinet,start,end,attempts,missing)
    payload={'chat_id':str(CHAT),'message_thread_id':str(THREAD),'text':text,'disable_web_page_preview':'true','disable_notification':'false','protect_content':'false'}
    req=urllib.request.Request('https://api.telegram.org/bot'+(bot_token or token())+'/sendMessage',data=urllib.parse.urlencode(payload).encode(),method='POST')
    try:
        with (opener or urllib.request.urlopen)(req,timeout=25) as reply:answer=json.load(reply)
    except Exception:raise RuntimeError('delivery outcome uncertain; no blind retry') from None
    result=answer.get('result',{})
    if answer.get('ok') is not True or result.get('chat',{}).get('id')!=CHAT or result.get('message_thread_id')!=THREAD or result.get('text')!=text or type(result.get('message_id')) is not int:raise ValueError('delivery not verified; do not resend')
    return {'status':'SENT','chat_id':CHAT,'thread_id':THREAD,'message_id':result['message_id'],'text_sha256':hashlib.sha256(text.encode()).hexdigest()}

if __name__=='__main__':
    try:
        if sys.argv[1:]==['--check'] and os.geteuid()==1001:
            token();print(json.dumps({'credentials_available':True,'chat_id':CHAT,'thread_id':THREAD}));raise SystemExit(0)
        if len(sys.argv)!=7 or os.geteuid()!=1001:raise ValueError('fixed Hermes sender only')
        print(json.dumps(send(sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5]),sys.argv[6])))
    except Exception as exc:
        print(json.dumps({'status':'DELIVERY_UNCERTAIN','error_type':type(exc).__name__}));raise SystemExit(2)
