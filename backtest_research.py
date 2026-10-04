"""STANDALONE research backtest — deliberately NOT part of the screener tool.

v1 of the tool is a screener, not a backtester. This script is a separate, point-in-time
research harness to estimate how the documented framework (top-down, top-20 by rotation
score, 200-DMA filter, quarterly rebalance) would have performed on the *validated* data
we now have.

IMPORTANT — read before trusting any number this prints:
  * SURVIVORSHIP BIAS (upward): the universe is TODAY's Nifty 500. Stocks are here because
    they survived/grew into the current index; an investor in the past didn't know that.
    This inflates results. A true test needs point-in-time index membership (not available).
  * WINDOW: ~6 years of data, not 10. Numbers are NOT a 10-year figure.
  * Costs modelled, but slippage/impact and exact taxes are approximations.
  * Past performance != future returns. This is research, not advice.

Run:  python backtest_research.py
"""

import numpy as np
import pandas as pd

from config import SECTORS, TIMEFRAME_CONFIGS, get_all_stocks
from data.cache import get_connection, load_ohlcv
from indicators.rrg import calculate_rrg
from indicators.rs_ranking import calculate_rs_score, rank_universe
from indicators.trend_filter import check_trend
from indicators.breadth import calculate_sector_breadth
from scoring.composite import compute_rotation_score

_SECTOR_OF = {s: name for name, syms in SECTORS.items() for s in syms}


def _load_panel(min_days=260):
    conn = get_connection()
    try:
        daily = {}
        for s in get_all_stocks():
            d = load_ohlcv(conn, s)
            if d.empty:
                continue
            c = d["Close"]
            c = c[~c.index.duplicated(keep="last")].sort_index().dropna()
            if len(c) >= min_days:
                daily[s] = c
        bench = load_ohlcv(conn, "IDX:NIFTY 500")["Close"]
        bench = bench[~bench.index.duplicated(keep="last")].sort_index().dropna()
    finally:
        conn.close()
    return daily, bench


def _metrics(equity, ppy):
    equity = equity.dropna()
    if len(equity) < 2:
        return {}
    total = float(equity.iloc[-1] / equity.iloc[0] - 1)
    years = max((len(equity) - 1) / ppy, 1e-9)
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)
    rets = equity.pct_change().dropna()
    vol = float(rets.std() * np.sqrt(ppy)) if len(rets) > 1 else 0.0
    sharpe = float((rets.mean() * ppy) / (rets.std() * np.sqrt(ppy))) if len(rets) > 1 and rets.std() > 0 else 0.0
    dd = float((equity / equity.cummax() - 1).min())
    return {"total": total * 100, "cagr": cagr * 100, "vol": vol * 100,
            "sharpe": sharpe, "maxdd": dd * 100, "years": years}


def run(timeframe="weekly", top_n=20, cost_bps=30.0, require_uptrend=True, stcg=0.20):
    tf = TIMEFRAME_CONFIGS[timeframe]
    freq = tf["resample"]
    daily, bench = _load_panel()
    if not daily or bench.empty:
        return {"error": "no data"}

    bidx = bench.index
    qends = pd.date_range(bidx.min(), bidx.max(), freq="QE")
    rebal = []
    for q in qends:
        sub = bidx[bidx <= q]
        if len(sub):
            rebal.append(sub[-1])
    rebal = sorted(set(rebal))
    rebal = [t for t in rebal if bench.loc[:t].shape[0] >= 260]  # ~1y history before first trade
    if len(rebal) < 5:
        return {"error": "not enough history"}

    period_rets, bench_rets, holdings = [], [], []
    prev = set()
    for i in range(len(rebal) - 1):
        t, tn = rebal[i], rebal[i + 1]
        bres = bench.loc[:t].resample(freq).last().dropna()
        if len(bres) < tf["sma_window"] + 5:
            continue

        # point-in-time RS rank across the universe
        rs_raw, res_cache, daily_cache = {}, {}, {}
        for s, c in daily.items():
            cd = c.loc[:t].dropna()
            if cd.shape[0] < 260:
                continue
            cr = cd.resample(freq).last().dropna()
            res_cache[s], daily_cache[s] = cr, cd
            rs = calculate_rs_score(cr, bres, tf["rs_periods"])
            if rs:
                rs_raw[s] = rs
        rs_ranked = rank_universe(rs_raw)

        breadth = {}
        for name, syms in SECTORS.items():
            sd = {s: pd.DataFrame({"Close": daily_cache[s]}) for s in syms if s in daily_cache}
            if sd:
                breadth[name] = calculate_sector_breadth(sd)

        scored = []
        for s in res_cache:
            rrg = calculate_rrg(res_cache[s], bres, tf["sma_window"], tf["roc_lookback"], tf["tail_length"])
            trend = check_trend(daily_cache[s])
            score = compute_rotation_score(rrg, rs_ranked.get(s), trend, breadth.get(_SECTOR_OF.get(s, ""), {}))
            above = trend["above_200dma"] if trend else False
            if require_uptrend and not above:
                continue
            scored.append((s, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        picks = [s for s, _ in scored[:top_n]]

        bench_rets.append(float(bench.loc[tn] / bench.loc[t] - 1))
        if not picks:
            period_rets.append(0.0)
            holdings.append({"date": t, "n": 0})
            prev = set()
            continue

        rr = []
        for s in picks:
            cs = daily[s]
            p0 = cs.loc[:t]
            p1 = cs.loc[:tn]
            if len(p0) and len(p1):
                rr.append(float(p1.iloc[-1] / p0.iloc[-1] - 1))
        gross = float(np.mean(rr)) if rr else 0.0
        newset = set(picks)
        turnover = len(newset.symmetric_difference(prev)) / max(len(newset), 1)
        net = gross - turnover * (cost_bps / 10000.0)
        prev = newset
        period_rets.append(net)
        holdings.append({"date": t, "n": len(picks)})

    if not period_rets:
        return {"error": "no periods"}

    ppy = 4  # quarterly
    strat_eq = pd.Series(np.cumprod([1.0] + [1 + r for r in period_rets]))
    bench_eq = pd.Series(np.cumprod([1.0] + [1 + r for r in bench_rets]))
    # indicative post-tax: tax positive quarterly net gains at STCG (conservative, overtaxes)
    post = [r - stcg * max(r, 0) for r in period_rets]
    post_eq = pd.Series(np.cumprod([1.0] + [1 + r for r in post]))

    sm, bm, pm = _metrics(strat_eq, ppy), _metrics(bench_eq, ppy), _metrics(post_eq, ppy)
    wins = sum(1 for a, b in zip(period_rets, bench_rets) if a > b)
    pos = sum(1 for r in period_rets if r > 0)
    return {
        "timeframe": timeframe, "top_n": top_n, "cost_bps": cost_bps,
        "n_q": len(period_rets), "start": rebal[0].date().isoformat(),
        "end": rebal[len(period_rets)].date().isoformat(),
        "strategy": sm, "benchmark": bm, "post_tax": pm,
        "alpha_cagr": round(sm["cagr"] - bm["cagr"], 2),
        "win_rate": round(100 * wins / len(period_rets), 1),
        "pos_q": round(100 * pos / len(period_rets), 1),
    }


def _fmt(r):
    if r.get("error"):
        return f"  ERROR: {r['error']}"
    s, b, p = r["strategy"], r["benchmark"], r["post_tax"]
    return (
        f"\n  Timeframe: {r['timeframe']}  |  top-{r['top_n']}  |  quarterly rebalance  |  "
        f"cost {r['cost_bps']:.0f}bps/turnover\n"
        f"  Period: {r['start']} -> {r['end']}  ({r['n_q']} quarters, {s['years']:.1f} yrs)\n"
        f"  {'metric':<16}{'STRATEGY':>12}{'NIFTY 500':>12}\n"
        f"  {'CAGR':<16}{s['cagr']:>11.1f}%{b['cagr']:>11.1f}%\n"
        f"  {'Total return':<16}{s['total']:>11.1f}%{b['total']:>11.1f}%\n"
        f"  {'Max drawdown':<16}{s['maxdd']:>11.1f}%{b['maxdd']:>11.1f}%\n"
        f"  {'Volatility':<16}{s['vol']:>11.1f}%{b['vol']:>11.1f}%\n"
        f"  {'Sharpe':<16}{s['sharpe']:>12.2f}{b['sharpe']:>12.2f}\n"
        f"  Alpha (CAGR vs bench): {r['alpha_cagr']:+.1f}%   |   quarters beating bench: {r['win_rate']}%   |   positive quarters: {r['pos_q']}%\n"
        f"  Indicative POST-TAX CAGR (20% STCG, conservative): {p['cagr']:.1f}%   vs benchmark {b['cagr']:.1f}%\n"
    )


if __name__ == "__main__":
    print("=" * 78)
    print("RESEARCH BACKTEST — survivorship-biased (upward), ~6yr window, NOT advice")
    print("=" * 78)
    for tfname in ["weekly", "monthly"]:
        print(_fmt(run(timeframe=tfname)))
    print("Reminder: today's-Nifty-500 universe overstates returns vs a true point-in-time test.")
