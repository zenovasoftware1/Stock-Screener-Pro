# Sector Rotation Screener (v1)

A **Python CLI tool** that screens Indian (NSE) stocks and sectors by combining four
complementary layers of analysis into one ranked output:

1. **RRG** (Relative Rotation Graph) — JdK RS-Ratio & RS-Momentum, the macro rotation view
2. **RS Ranking** — multi-timeframe relative-strength composite, the quantitative rank
3. **Absolute Trend Filter** — 200-DMA check, kills the "leading-in-a-downtrend" trap
4. **Sector Breadth** — % of constituents above 50/200-DMA, confirms real participation

Each stock gets a composite **Rotation Score (0-100)**; stocks are sorted descending, so the
top of the list is the action set.

> **Why this combination:** RRG alone is purely *relative* and can flag a sector as
> "outperforming" while it's actually falling (just less than the benchmark). Layering RS
> ranking + absolute trend + breadth removes that trap.

It tells you **"what looks good now"** — it is a *screener*, not a backtester.

---

## Setup

```bash
cd "/Users/siddharthagarwal/Desktop/Market Move"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

No API keys required — data comes from `jugaad-data` (NSE, primary) with a `yfinance`
(`.NS` suffix) fallback. All EOD data is cached in `data/cache.db` (SQLite).

**Universe:** the official **NSE Nifty 500**, grouped by NSE's own "Industry"
classification into 20 macro-sectors. The constituent list lives in
[`data/nifty500_constituents.csv`](data/nifty500_constituents.csv) and is loaded at import.
Refresh it any time with:

```bash
.venv/bin/python data/refresh_universe.py    # re-downloads the latest Nifty 500 list
```

## Usage

```bash
# Warm the cache once (parallel fetch; first cold run is the slow one).
.venv/bin/python cli.py update

# Top stocks across all sectors
.venv/bin/python cli.py scan --timeframe weekly --top 30
.venv/bin/python cli.py scan -t weekly -n 50 --export out.csv      # + CSV export

# Sector-level rotation map
.venv/bin/python cli.py sectors --timeframe monthly

# Drill into one sector (partial names match, e.g. "Defence", "Bank")
.venv/bin/python cli.py sector "Nifty Bank" -t weekly

# Single-stock full profile
.venv/bin/python cli.py stock RELIANCE -t weekly

# Override the benchmark on any command
.venv/bin/python cli.py scan -b "NIFTY 50"
```

**Timeframes:** `weekly | monthly | quarterly | semi-annual | annual`
**Output:** colour-coded Rich tables (green=Leading, cyan=Improving, yellow=Weakening,
red=Lagging) plus optional CSV export for Excel/Google Sheets.

## Web UI

A Streamlit dashboard (cache-first — reads the warmed SQLite cache for instant rendering):

```bash
.venv/bin/streamlit run app.py        #  →  http://localhost:8501
```

Flow: the landing page shows all 20 sectors with their rotation quadrant, breadth, and
score (table + an RRG quadrant scatter) — **click a sector row to drill into its ranked
stocks.** Timeframe/benchmark live in the sidebar, along with a **"Refresh data from NSE"**
button that re-warms the cache (EOD data, so it changes once a day after market close).
The UI never fetches on its own — it reads the cache, so it's instant.

---

## How the math works

| Layer | Formula (summary) |
|-------|-------------------|
| RRG | `raw_rs = stock/bench * 100`; `rs_ratio = 100 + (raw_rs − SMA)/Std`; momentum is the same z-score applied to the ratio's rate-of-change. Quadrant from (ratio, momentum) vs 100. |
| RS Rank | Weighted multi-lookback `(stock_ret − bench_ret)`, then percentile-ranked across the universe (0-100). |
| Trend | `above_200dma = close > SMA(close, 200)`; score 100/0. |
| Breadth | `% of sector constituents above their N-DMA` for N in {50, 200}. ≥70 Strong, 40-69 Mixed, <40 Weak. |
| Composite | `0.25·RRG + 0.35·RS_pct + 0.20·Trend + 0.20·Breadth_200`. |

Tunables live in [`config.py`](config.py): `TIMEFRAME_CONFIGS`, `COMPOSITE_WEIGHTS`,
`RRG_SCORE_MAP`, and the `SECTORS` universe.

---

## Project structure

```
Market Move/
├── config.py              # universe loader (CSV-driven), timeframe windows, weights, score map
├── cli.py                 # Click CLI: scan / sectors / sector / stock / update
├── requirements.txt
├── data/
│   ├── nifty500_constituents.csv  # official Nifty 500 list (the universe)
│   ├── refresh_universe.py        # re-download the Nifty 500 list
│   ├── cache.py           # SQLite cache (WAL mode, thread-safe parallel writes)
│   └── fetcher.py         # jugaad → yfinance fallback; parallel fetch_universe()
├── indicators/
│   ├── rrg.py             # RS-Ratio / RS-Momentum / quadrant / direction
│   ├── rs_ranking.py      # multi-timeframe RS composite + percentile rank
│   ├── trend_filter.py    # 200-DMA check
│   └── breadth.py         # % above 50/200-DMA
├── scoring/composite.py   # Rotation Score (0-100) + stock profile
└── output/formatter.py    # Rich tables + CSV export
```

---

## Scope (v1) and the v2 roadmap

**v1 is intentionally a CLI EOD screener.** The following are deliberately *out of scope*
for v1, by design:

- **FII/DII flow integration** — sector-wise FII data requires scraping NSDL/SEBI reports
  whose format changes frequently. Deferred to **v2**.
- **Backtesting engine** — this is a screener, not a backtester. It tells you "what looks
  good now," not "how would this have performed." Out of scope by design.
- **GUI / web dashboard** — CLI only, with CSV export for anyone who wants to visualize in
  Excel / Google Sheets.

## Notes / current limitations

- The universe is the **full NSE Nifty 500** grouped into 20 NSE-defined industry sectors,
  so breadth % is over true index membership (not a sample). The benchmark defaults to
  NIFTY 500, so universe and benchmark match.
- A small number of symbols may occasionally fail to fetch (rename/delisting between index
  rebalances). The CLI reports these and continues — they don't affect the rest of the run.
  Re-run `data/refresh_universe.py` after an index rebalance to pick up changes.
- First cold run is network-bound (~500 stocks); subsequent runs read from SQLite in
  seconds. Fetching is parallelised (`FETCH_MAX_WORKERS` in `config.py`) with a 20s
  socket-timeout backstop so a hung request can't stall the run.
- **NSE throttling:** hammering NSE with a full `update --force` of all 500 at once can get
  rate-limited mid-run. The cache is incremental, so the simplest warm is to just *use* the
  tool — `scan`/`sectors`/`sector` fetch only the symbols they still need (no force) and
  cache them. Re-running fills in any that were throttled. Off-peak hours fetch fastest.
