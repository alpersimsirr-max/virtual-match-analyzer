import json,re
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

PAGES=["https://www.vbet.com/uk/sports/pre-match/results","https://m.vbet.am/en/sports/pre-match/results","https://pagebuilderm.vbet.am/en/sports/pre-match/results"]
H={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"}
s=requests.Session();s.headers.update(H)
report={"pages":[],"chunks":[],"matches_found":0}
for page in PAGES:
 try:
  r=s.get(page,timeout=30);r.raise_for_status(); soup=BeautifulSoup(r.text,"html.parser")
  scripts=[urljoin(page,x.get("src")) for x in soup.select("script[src]")]
  report["pages"].append({"url":page,"status":r.status_code,"scripts":scripts})
  for u in scripts:
   try:
    js=s.get(u,timeout=25).text
    base=u.rsplit("/",1)[0]+"/"
    paths=set(re.findall(r'["\']([^"\']*(?:ApiController|SportsBook|EventDispatcher)[^"\']*\.js)["\']',js))
    for path in paths:
     chunk=urljoin(base,path)
     try:
      cr=s.get(chunk,timeout=25); body=cr.text
      needles=["eu-swarm-newm","Betual","betual","results","events","apiUrl","baseURL","swarm"]
      found={n:[m.start() for m in re.finditer(re.escape(n),body,re.I)][:8] for n in needles if re.search(re.escape(n),body,re.I)}
      report["chunks"].append({"url":chunk,"status":cr.status_code,"bytes":len(body),"matches":found,
       "snippets":{n:[body[max(0,i-180):i+350] for i in pos[:3]] for n,pos in found.items()}})
     except Exception as e: report["chunks"].append({"url":chunk,"error":str(e)[:200]})
   except Exception as e: report["chunks"].append({"url":u,"error":str(e)[:200]})
 except Exception as e: report["pages"].append({"url":page,"error":str(e)[:200]})
Path("data").mkdir(exist_ok=True)
Path("data/api_research.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"pages":len(report["pages"]),"chunks":len(report["chunks"]),"report":"data/api_research.json"},ensure_ascii=False))
