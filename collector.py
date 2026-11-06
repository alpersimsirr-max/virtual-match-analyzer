import json,re
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
PAGES=["https://www.vbet.com/uk/sports/pre-match/results","https://m.vbet.am/en/sports/pre-match/results","https://pagebuilderm.vbet.am/en/sports/pre-match/results"]
H={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"}
s=requests.Session();s.headers.update(H)
report={"pages":[],"assets":[],"swarm_hosts":["https://eu-swarm-newm.vbet.am"],"api_candidates":[]}
seen=set()
for page in PAGES:
 try:
  r=s.get(page,timeout=30);r.raise_for_status(); soup=BeautifulSoup(r.text,"html.parser")
  assets=[urljoin(page,x.get("href")) for x in soup.select('link[rel="modulepreload"][href]')]
  assets += [urljoin(page,x.get("src")) for x in soup.select('script[src]')]
  report["pages"].append({"url":page,"status":r.status_code,"assets":len(set(assets))})
  for u in set(assets):
   if u in seen: continue
   seen.add(u)
   try:
    cr=s.get(u,timeout=25);body=cr.text
    if cr.status_code!=200: continue
    hits={}
    for term in ["eu-swarm-newm","Betual","betual","results","events","ApiController","baseURL","apiUrl","getEvents","GetEvents"]:
     positions=[m.start() for m in re.finditer(re.escape(term),body,re.I)][:8]
     if positions:hits[term]=[body[max(0,i-180):i+400] for i in positions[:3]]
    if hits: report["assets"].append({"url":u,"bytes":len(body),"hits":hits})
    for v in re.findall(r'https?://[^\s<>"]+',body):
     v=v.rstrip(");,")
     if "swarm" in v.lower() and v not in report["swarm_hosts"]:report["swarm_hosts"].append(v)
    for v in re.findall(r'["\'](/[^"\']{2,120})["\']',body):
     if any(k in v.lower() for k in ["event","result","sport","match"]) and v not in report["api_candidates"]:report["api_candidates"].append(v)
   except Exception as e: report["assets"].append({"url":u,"error":str(e)[:160]})
 except Exception as e:report["pages"].append({"url":page,"error":str(e)[:160]})
Path("data/api_research.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"pages":len(report["pages"]),"assets_scanned":len(seen),"interesting_assets":len(report["assets"]),"swarm_hosts":report["swarm_hosts"],"api_candidates":report["api_candidates"][:50]},ensure_ascii=False,indent=2))
