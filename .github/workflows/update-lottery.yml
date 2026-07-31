#!/usr/bin/env python3
import json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36'
def get(url):
    req=Request(url,headers={'User-Agent':UA,'Accept':'application/json,text/html,*/*','Referer':url})
    with urlopen(req,timeout=30) as r:return r.read().decode('utf-8','ignore')
def valid(nums):return len(nums)==5 and len(set(nums))==5 and all(1<=n<=39 for n in nums)
def date_iso(s):
    for f in ('%Y-%m-%dT%H:%M:%S','%Y-%m-%d','%m/%d/%Y','%Y/%m/%d','%B %d, %Y','%A, %B %d, %Y'):
        try:return datetime.strptime(s.strip().split('.')[0],f).strftime('%Y/%m/%d')
        except:pass
    m=re.search(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})',s)
    return f'{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}' if m else s.strip()

def fantasy5():
    errors=[]
    # Official API: probe likely game ids; accept only a 5/39 result.
    for gid in (9,10,7,8,11,13,14,15):
        try:
            j=json.loads(get(f'https://www.calottery.com/api/DrawGameApi/DrawGamePastDrawResults/{gid}/1/5'))
            for d in j.get('PreviousDraws',[]):
                nums=[int(x.get('Number')) for x in d.get('WinningNumbers',[]) if str(x.get('Number','')).isdigit()]
                if valid(nums):return {'date':date_iso(str(d.get('DrawDate',''))),'issue':str(d.get('DrawNumber','')),'nums':sorted(nums),'source':'California Lottery API'}
        except Exception as e: errors.append(str(e))
    # Official draw-games page fallback.
    try:
        t=get('https://www.calottery.com/en/draw-games')
        m=re.search(r'FANTASY\s*5.{0,1200}?Last Draw:\s*([^<\n]+).{0,500}?((?:\b(?:0?[1-9]|[12]\d|3[0-9])\b\D*){5})',t,re.I|re.S)
        if m:
            nums=[int(x) for x in re.findall(r'\b(?:0?[1-9]|[12]\d|3[0-9])\b',m.group(2))[:5]]
            if valid(nums):return {'date':date_iso(m.group(1)),'issue':'','nums':sorted(nums),'source':'California Lottery'}
    except Exception as e: errors.append(str(e))
    # Public fallback.
    t=get('https://www.lotteryusa.com/california/fantasy-5/')
    dm=re.search(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})',t)
    blocks=re.findall(r'ball[^>]*>\s*(\d{1,2})\s*<',t,re.I)
    nums=[int(x) for x in blocks[:5]]
    if valid(nums):return {'date':date_iso(dm.group(0) if dm else ''),'issue':'','nums':sorted(nums),'source':'LotteryUSA fallback'}
    raise RuntimeError('Fantasy 5 sources failed: '+' | '.join(errors[-3:]))

def lotto539():
    errors=[]
    sources=['https://www.taiwanlottery.com/','https://www.pilio.idv.tw/lto539/drawlist/drawlist.asp']
    for url in sources:
        try:
            t=get(url)
            # Locate 539 vicinity then take plausible date and five ball values.
            pos=max(t.lower().find('今彩539'),t.lower().find('lotto 539'))
            chunk=t[pos:pos+12000] if pos>=0 else t[:20000]
            dates=re.findall(r'20\d{2}[/-]\d{1,2}[/-]\d{1,2}',chunk)
            # Prefer numbers appearing in ball/result elements, then general 01-39 tokens.
            vals=re.findall(r'(?:ball|number|result)[^>]{0,120}>\s*0?([1-9]|[12]\d|3[0-9])\s*<',chunk,re.I)
            if len(vals)<5: vals=re.findall(r'(?<!\d)(0?[1-9]|[12]\d|3[0-9])(?!\d)',re.sub(r'20\d{2}[/-]\d{1,2}[/-]\d{1,2}',' ',chunk))
            for i in range(max(1,len(vals)-4)):
                nums=[int(x) for x in vals[i:i+5]]
                if valid(nums):return {'date':date_iso(dates[0] if dates else ''),'issue':'','nums':sorted(nums),'source':url}
        except Exception as e: errors.append(str(e))
    raise RuntimeError('539 sources failed: '+' | '.join(errors[-3:]))

def main():
    old={}
    p=Path('latest-draws.json')
    if p.exists():
        try:old=json.loads(p.read_text(encoding='utf-8'))
        except:pass
    games={}
    failures=[]
    for key,fn in [('539',lotto539),('dayday',fantasy5)]:
        try:games[key]=fn()
        except Exception as e:
            failures.append(f'{key}: {e}')
            if old.get('games',{}).get(key):games[key]=old['games'][key]
    if len(games)<2: raise SystemExit('\n'.join(failures))
    data={'updated_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'games':games,'warnings':failures}
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(data,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
