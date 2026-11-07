import json,re
from datetime import datetime,timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

URL="https://pagebuilderm.vbet.am/en/sports/pre-match/results"
SCORE=re.compile(r"^(\d{1,2})\s*:\s*(\d{1,2})\s*\(\s*(\d{1,2})\s*:\s*(\d{1,2})\s*\)$")
DATE=re.compile(r"^\d{2}\.\d{2}\.\d{4}")
def clean(s): return re.sub(r"\s+"," ",s).strip()
def main():
    diag={"status":"started","url":URL,"pages":0,"parsed_count":0,"more_clicks":0,"score_lines":0,"errors":[]}
    records={}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(locale="en-US")
        try:
            page.goto(URL,wait_until="domcontentloaded",timeout=90000)
            page.wait_for_timeout(12000)
            # The results page exposes a More control for older fixtures.
            # Load as many historical result batches as the public page exposes.
            # Stop when the control disappears or a click no longer adds score rows.
            previous_scores=0
            for _ in range(40):
                try:
                    more=page.get_by_text("More",exact=True).last
                    if not more.is_visible(): break
                    more.click(timeout=4000)
                    page.wait_for_timeout(1200)
                    current_text=page.locator("body").inner_text(timeout=30000)
                    current_scores=len(SCORE.findall(current_text))
                    diag["more_clicks"]+=1
                    if current_scores<=previous_scores:
                        break
                    previous_scores=current_scores
                except Exception:
                    break
            lines=[clean(x) for x in page.locator("body").inner_text(timeout=30000).splitlines()]
            diag["pages"]=1
            diag["body_chars"]=sum(map(len,lines))
            diag["virtual_markers"]=sum("Virtual Matches" in x for x in lines)
            diag["score_lines"]=sum(bool(SCORE.match(x)) for x in lines)
            diag["sample_lines"]=lines[:35]
            # Scores are rendered as FT (HT); associate with the two closest preceding virtual teams.
            recent=[]
            for i,line in enumerate(lines):
                if "Virtual" in line and not line.lower().startswith("image:"):
                    if not recent or recent[-1]!=line: recent.append(line)
                    recent=recent[-6:]
                m=SCORE.match(line)
                if not m: continue
                teams=recent[-2:]
                if len(teams)!=2 or not all("Virtual" in t for t in teams): continue
                # Require an explicit Betual virtual competition in the page, and retain league label.
                comp=""
                for prev in reversed(lines[:i]):
                    if "Betual" in prev and "Virtual Matches" in prev:
                        comp=prev; break
                if not comp: continue
                fh,fa,hh,ha=map(int,m.groups())
                item={"home_team":teams[0],"away_team":teams[1],"ft_home":fh,"ft_away":fa,
                      "ht_home":hh,"ht_away":ha,"date":None,"game_id":"",
                      "competition":comp,"source":"VBET rendered results page",
                      "source_url":URL}
                key=(comp,teams[0],teams[1],fh,fa,hh,ha)
                records[key]=item
            diag["parsed_count"]=len(records)
            diag["sample"]=list(records.values())[:8]
            diag["status"]="success" if records else "no_verified_matches"
            Path("data").mkdir(exist_ok=True)
            oldfile=Path("data/matches.json")
            old=json.loads(oldfile.read_text(encoding="utf-8")) if oldfile.exists() else {}
            merged={}
            for x in old.get("matches",[])+list(records.values()):
                key=str(x.get("game_id") or (x.get("competition"),x.get("date"),x.get("home_team"),
                     x.get("away_team"),x.get("ft_home"),x.get("ft_away"),x.get("ht_home"),x.get("ht_away")))
                merged[key]=x
            all_matches=sorted(merged.values(),key=lambda x:str(x.get("date") or ""))
            oldfile.write_text(json.dumps({"updated_at":datetime.now(timezone.utc).isoformat(),
                "match_count":len(all_matches),"sources":[{"url":URL,"method":"playwright_rendered_results",
                "filter":"Betual competition + virtual teams + FT/HT score"}],"matches":all_matches},
                ensure_ascii=False,indent=2),encoding="utf-8")
            Path("data/browser_results_probe.json").write_text(json.dumps(diag,ensure_ascii=False,indent=2),encoding="utf-8")
        except Exception as e:
            diag["status"]="failed";diag["errors"].append(str(e)[:1000])
            Path("data/browser_results_probe.json").write_text(json.dumps(diag,ensure_ascii=False,indent=2),encoding="utf-8")
        finally: browser.close()
    print("BROWSER_RESULTS="+json.dumps({k:v for k,v in diag.items() if k not in ("sample_lines","sample")},ensure_ascii=False))
if __name__=="__main__": main()
