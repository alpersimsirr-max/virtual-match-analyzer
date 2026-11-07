#!/usr/bin/env python3
"""Inspect one user-supplied public Betual live match URL with Playwright.

Only the allow-listed Milyoner host is opened. No credentials/cookies are stored.
The script writes a structured diagnostic and, only when score + clock + period
are all verified in rendered page text, a live-state record and an experimental
forecast. A 15-minute-half clock is normalized to a 90-minute model clock.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from types import SimpleNamespace

URL = os.environ.get("MATCH_URL", "").strip()
OUT = Path("data")
OUT.mkdir(exist_ok=True)


def fail(status, message, **extra):
    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "message": message,
        **extra,
    }
    (OUT / "live_link_probe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False))
    return payload


def main():
    if not URL:
        return fail("missing_url", "MATCH_URL workflow input was empty.")
    parsed = urlparse(URL)
    if parsed.scheme != "https" or parsed.hostname != "m.milyoner549.com":
        return fail("rejected_url", "Only https://m.milyoner549.com URLs are allowed.")

    from playwright.sync_api import sync_playwright

    page_text = ""
    page_title = ""
    response_status = None
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 412, "height": 915},
            user_agent=("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36")
        )
        page.on("requestfailed", lambda req: errors.append(
            {"url": req.url[:240], "error": (req.failure or "")[:160]}
        ))
        try:
            response = page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            response_status = response.status if response else None
            page.wait_for_timeout(7000)
            page_title = page.title()
            page_text = page.locator("body").inner_text(timeout=15000)
        except Exception as exc:
            browser.close()
            return fail("page_load_failed", str(exc)[:500],
                        http_status=response_status, request_errors=errors[:12])
        browser.close()

    # Keep only public rendered text needed for diagnosis; do not persist HTML,
    # cookies, headers, local storage, or account details.
    compact = re.sub(r"\s+", " ", page_text).strip()
    clock_match = re.search(r"(\d{1,2})\s*['’]\s*(?:15\s*dakikalık\s*)?(1\.\s*Yarı|2\.\s*Yarı)", compact, re.I)
    if not clock_match:
        clock_match = re.search(r"(\d{1,2})\s*['’].{0,45}(1\.\s*Yarı|2\.\s*Yarı)", compact, re.I)

    # Team/score block: two virtual-team labels followed by their displayed scores.
    team_score = re.search(
        r"([A-ZÀ-ÖØ-Þ][\wÀ-ÿ.'() -]{1,55}?Virtual)\s+(\d{1,2})\s+"
        r"([A-ZÀ-ÖØ-Þ][\wÀ-ÿ.'() -]{1,55}?Virtual)\s+(\d{1,2})",
        page_text, re.I
    )
    # Backup to URL slug when rendered names are split by layout elements.
    home = away = None
    hs = aws = None
    if team_score:
        home, hs, away, aws = team_score.group(1).strip(), int(team_score.group(2)), team_score.group(3).strip(), int(team_score.group(4))

    period = None
    elapsed = None
    if clock_match:
        elapsed = int(clock_match.group(1))
        period = "first_half" if "1." in clock_match.group(2) else "second_half"

    # The score line is a separate compact signal and must agree with team block.
    score_line = re.search(
        r"(\d{1,2})\s*:\s*(\d{1,2})\s*,\s*\(\s*\d+\s*:\s*\d+\s*\)",
        compact
    )
    score_line_ok = bool(score_line and hs is not None and
                         int(score_line.group(1)) == hs and int(score_line.group(2)) == aws)

    if not (home and away and hs is not None and aws is not None and elapsed is not None and period):
        return fail(
            "waiting_for_verified_live_data",
            "Page loaded but a complete team/score/clock/period tuple was not confidently parsed.",
            http_status=response_status, page_title=page_title,
            page_text_sample=compact[:2200], request_errors=errors[:12]
        )

    # Betual clock is 15 minutes per half (30 total); convert to 90-minute scale.
    elapsed_total = elapsed if period == "first_half" else 15 + elapsed
    normalized_minute = round(elapsed_total * 3)
    normalized_minute = max(0, min(89, normalized_minute))
    record = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "live_state_verified",
        "source_url": URL,
        "game_id": parsed.path.rstrip("/").split("/")[-1],
        "home_team": home, "away_team": away,
        "home_score": hs, "away_score": aws,
        "display_clock_minute": elapsed,
        "period": period,
        "model_minute_90_scale": normalized_minute,
        "score_line_agrees": score_line_ok,
        "http_status": response_status,
        "page_title": page_title,
        "page_text_sample": compact[:1200],
        "request_errors": errors[:12],
    }

    # Produce a forecast only after live state is parsed. Existing archive is small;
    # keep the low-confidence warning from the predictor visible.
    try:
        from predictor import predict
        archive = OUT / "matches.json"
        args = SimpleNamespace(
            home=home, away=away, data=str(archive),
            minute=normalized_minute, home_score=hs, away_score=aws,
            home_shots=None, away_shots=None
        )
        record["experimental_prediction"] = predict(args)
        record["prediction_status"] = "experimental_small_archive"
    except Exception as exc:
        record["prediction_status"] = "unavailable"
        record["prediction_error"] = str(exc)[:300]

    (OUT / "manual_live_match.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "live_link_probe.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "status": record["status"], "match": f"{home} - {away}",
        "score": f"{hs}-{aws}", "period": period,
        "display_minute": elapsed, "model_minute": normalized_minute,
        "prediction_status": record.get("prediction_status")
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
