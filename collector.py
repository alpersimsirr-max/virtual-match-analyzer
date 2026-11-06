import json, re, hashlib
from datetime import datetime, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

URLS = [
    "https://www.vbet.com/uk/sports/pre-match/results",
    "https://m.vbet.am/en/sports/pre-match/results",
    "https://pagebuilderm.vbet.am/en/sports/pre-match/results",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VirtualMatchAnalyzer/1.0)"}
SCORE = re.compile(r"^(\d{1,2})\s*:\s*(\d{1,2})\s*\(\s*(\d{1,2})\s*:\s*(\d{1,2})\s*\)$")
DATE = re.compile(r"^\d{2}\.\d{2}\.\d{4}\s*\d{2}:\d{2}$")
def clean(s):
    return re.sub(r"\s+", " ", s).strip()
def parse(html, source):
    soup = BeautifulSoup(html, "html.parser")
    lines = [clean(x) for x in soup.stripped_strings if clean(x)]
    rows, league = [], "Bilinmeyen lig"
    for i, line in enumerate(lines):
        if "Betual" in line and ("Virtual" in line or "Sanal" in line):
            league = line
        m = SCORE.match(line)
        if not m or i < 4:
            continue
        # Results pages render home/away names and scores immediately before score summary.
        candidates = lines[max(0, i-5):i]
        nums = [j for j,x in enumerate(candidates) if re.fullmatch(r"\d{1,2}", x)]
        if len(nums) < 2:
            continue
        n1, n2 = nums[-2], nums[-1]
        if n1 == 0 or n2 <= n1:
            continue
        home = candidates[n1-1] if n1-1 >= 0 else ""
        away = candidates[n2-1] if n2-1 >= 0 else ""
        if not home or not away or home == away:
            continue
        date = lines[i+1] if i+1 < len(lines) and DATE.match(lines[i+1]) else ""
        row = {"league": league, "home": home, "away": away,
               "home_score": int(m.group(1)), "away_score": int(m.group(2)),
               "ht_home": int(m.group(3)), "ht_away": int(m.group(4)),
               "date": date, "source": source}
        rows.append(row)
    return rows, soup.title.get_text(" ", strip=True) if soup.title else ""

all_rows, diagnostics = {}, []
for url in URLS:
    try:
        response = requests.get(url, headers=HEADERS, timeout=35)
        response.raise_for_status()
        rows, title = parse(response.text, url)
        diagnostics.append({"url": url, "http": response.status_code, "title": title,
                            "html_bytes": len(response.content), "parsed_matches": len(rows)})
        for row in rows:
            key = hashlib.sha1(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            all_rows[key] = row
    except Exception as exc:
        diagnostics.append({"url": url, "error": str(exc)[:300]})

records = sorted(all_rows.values(), key=lambda x: x.get("date",""), reverse=True)
payload = {"updated_at": datetime.now(timezone.utc).isoformat(),
           "match_count": len(records), "sources": diagnostics, "matches": records}
Path("data").mkdir(exist_ok=True)
Path("data/matches.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"match_count": len(records), "sources": diagnostics}, ensure_ascii=False, indent=2))
