# Betual virtual match predictor

The collector updates `data/matches.json` every 30 minutes through GitHub Actions.
The experimental predictor reads that archive and estimates half-time and full-time scores.

## Run

```bash
python predictor.py "Valencia Virtual" "Racing Santander Virtual"
```

For a live match, pass the current minute, score and shot counts:

```bash
python predictor.py "Valencia Virtual" "Racing Santander Virtual" --minute 8 --home-score 0 --away-score 0 --home-shots 9 --away-shots 4
```

The output includes the leading HT/FT score estimates and estimated over 2.5, 3.5 and 4.5 probabilities. Team history is blended with archive averages to reduce overfitting when only a few matches are available.

## Important limitations

- The current public results collector has 38 verified records, with no stable event IDs or event timestamps yet.
- The predictor is a statistical baseline, not a trained or validated high-accuracy model.
- It does not read a live Betual screen by itself. Live minute, score and shots must currently be supplied as command-line arguments.
- Do not use its estimates as guaranteed outcomes or as a basis for risking money.
