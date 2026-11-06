import json,re
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
PAGES=["https://www.vbet.com/uk/sports/pre-match/results","https://m.vbet.am/en/sports/pre-match/results","https://pagebuilderm.vbet.am/en/sports/pre-match/results"]
H={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"}
s=requests.Session();s.headers.update(H)
report={"pages":[],"assets":[],"swarm_hosts":[],"api_candidates":[]}
queue=[];seen=set()
for page in PAGES:
 try:
  r=s.get(page,timeout=30);r.raise_for_status(); soup=BeautifulSoup(r.text,"html.parser")
  assets=[urljoin(page,x.get("href")) for x in soup.select('link[rel="modulepreload"][href]')]
  assets += [urljoin(page,x.get("src")) for x in soup.select('script[src]')]
  report["pages"].append({"url":page,"status":r.status_code,"assets":len(set(assets))})
  queue.extend(assets)
 except Exception as e:report["pages"].append({"url":page,"error":str(e)[:160]})
terms=["eu-swarm-newm","betual","results","events","eventdispatcher","sportsbook","apiurl","baseurl","getevents","geteventlist","competition","tournament"]
while queue and len(seen)<260:
 u=queue.pop(0)
 if u in seen:continue
 seen.add(u)
 try:
  r=s.get(u,timeout=20)
  if r.status_code!=200 or len(r.content)>5_000_000:continue
  body=r.text
  hits={}
  for term in terms:
   pos=[m.start() for m in re.finditer(re.escape(term),body,re.I)][:8]
   if pos:hits[term]=[body[max(0,i-220):i+500] for i in pos[:4]]
  if hits:report["assets"].append({"url":u,"bytes":len(r.content),"hits":hits})
  # Follow relative JS imports and preload chunks recursively.
  for path in re.findall(r'(?:from|import\s*\()\s*["\']([^"\']+\.js)["\']',body):
   queue.append(urljoin(u,path))
  for path in re.findall(r'["\']([^"\']+\.js)["\']',body):
   if path.startswith(("/assets/","./")):queue.append(urljoin(u,path))
  for v in re.findall(r'https?://[^\s<>"]+',body):
   v=v.rstrip(");,")
   if any(k in v.lower() for k in ["swarm","api","betconstruct"]) and v not in report["swarm_hosts"]:report["swarm_hosts"].append(v)
  for v in re.findall(r'["\'](/[^"\']{2,160})["\']',body):
   if any(k in v.lower() for k in ["event","result","sport","match","competition"]) and v not in report["api_candidates"]:report["api_candidates"].append(v)
 except Exception as e:report["assets"].append({"url":u,"error":str(e)[:120]})
Path("data/api_research.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"pages":len(report["pages"]),"assets_scanned":len(seen),"interesting_assets":len(report["assets"]),"swarm_hosts":report["swarm_hosts"][:30],"api_candidates":report["api_candidates"][:80]},ensure_ascii=False,indent=2))
