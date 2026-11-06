import json, re, hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

URLS = [
 "https://www.vbet.com/uk/sports/pre-match/results",
 "https://www.vbet.com/ru/sports/results",
 "https://m.vbet.am/en/sports/pre-match/results",
 "https://pagebuilderm.vbet.am/en/sports/pre-match/results",
 "https://m.vbet.com/uk/sports/pre-match/results",
]
HEADERS={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
SCORE=re.compile(r"^(\d{1,2})\s*:\s*(\d{1,2})\s*\(\s*(\d{1,2})\s*:\s*(\d{1,2})\s*\)$")
DATE=re.compile(r"^\d{2}\.\d{2}\.\d{4}\s*\d{2}:\d{2}$")
def clean(s): return re.sub(r"\s+"," ",s).strip()
def parse_visible(html,source):
 soup=BeautifulSoup(html,"html.parser"); lines=[clean(x) for x in soup.stripped_strings if clean(x)]
 rows=[]; league="Unknown"
 for i,line in enumerate(lines):
  if "Betual" in line: league=line
  m=SCORE.match(line)
  if not m: continue
  # Team labels and scores appear in sequence; infer from nearest text nodes.
  nums=[j for j in range(max(0,i-8),i) if re.fullmatch(r"\d{1,2}",lines[j])]
  if len(nums)<2: continue
  n1,n2=nums[-2:]; home=lines[n1-1] if n1>0 else ""; away=lines[n2-1] if n2>0 else ""
  if not home or not away or home==away: continue
  date=lines[i+1] if i+1<len(lines) and DATE.match(lines[i+1]) else ""
  rows.append({"league":league,"home":home,"away":away,"home_score":int(m[1]),"away_score":int(m[2]),"ht_home":int(m[3]),"ht_away":int(m[4]),"date":date,"source":source})
 return rows,soup
session=requests.Session();session.headers.update(HEADERS)
all_rows={}; diagnostics=[]; probes=[]
for url in URLS:
 try:
  res=session.get(url,timeout=35); res.raise_for_status()
  rows,soup=parse_visible(res.text,url)
  scripts=[urljoin(url,x.get("src")) for x in soup.find_all("script") if x.get("src")]
  probes.append({"url":url,"http":res.status_code,"title":soup.title.get_text(" ",strip=True) if soup.title else "", "bytes":len(res.content),"script_urls":scripts[:30],"html_sample":res.text[:1800]})
  diagnostics.append({"url":url,"http":res.status_code,"bytes":len(res.content),"parsed_matches":len(rows)})
  for row in rows:
   key=hashlib.sha1(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest();all_rows[key]=row
 except Exception as e: diagnostics.append({"url":url,"error":str(e)[:250]})
# Inspect frontend bundles for API route hints (do not call unknown endpoints).
assets=set(u for p in probes for u in p.get("script_urls",[]))
api_hints=[]
for asset in list(assets)[:20]:
 try:
  r=session.get(asset,timeout=20); body=r.text[:2_000_000]
  hints=sorted(set(re.findall(r"""(?:https?://[^"'\s<>]+|/(?:api|sports|results|event|v\d)[^"'\s<>]{0,140})""",body,re.I)))
  if hints: api_hints.append({"asset":asset,"http":r.status_code,"hints":hints[:120]})
 except Exception as e: api_hints.append({"asset":asset,"error":str(e)[:150]})
records=sorted(all_rows.values(),key=lambda x:x.get("date",""),reverse=True)
Path("data").mkdir(exist_ok=True)
Path("data/matches.json").write_text(json.dumps({"updated_at":datetime.now(timezone.utc).isoformat(),"match_count":len(records),"sources":diagnostics,"matches":records},ensure_ascii=False,indent=2),encoding="utf-8")
Path("data/source_probe.json").write_text(json.dumps({"pages":probes,"javascript_api_hints":api_hints},ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"match_count":len(records),"sources":diagnostics,"pages_probed":len(probes),"js_assets_inspected":len(assets),"api_hint_assets":len(api_hints)},ensure_ascii=False,indent=2))
