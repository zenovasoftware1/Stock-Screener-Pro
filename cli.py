#!/usr/bin/env python3
"""Sector Rotation Screener (v1) — RRG + RS Ranking + Trend + Breadth.

EOD-only CLI screener for NSE stocks/sectors. CSV export included.
Out of scope for v1 (see README): FII/DII flows, backtesting, web GUI.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from config import (
    SECTORS, TIMEFRAME_CONFIGS, DEFAULT_BENCHMARK, RRG_SCORE_MAP, HISTORY_YEARS, get_all_stocks,
)
from data.fetcher import fetch_stock, fetch_index, fetch_universe
from indicators.rrg import calculate_rrg, resample_close
from indicators.rs_ranking import calculate_rs_score, rank_universe
from indicators.trend_filter import check_trend
from indicators.breadth import calculate_sector_breadth
from scoring.composite import build_stock_profile
from output.formatter import (
    format_scan_table, format_sector_table, format_stock_detail, export_csv,
)

console = Console()


def _get_tf_config(timeframe):
    cfg = TIMEFRAME_CONFIGS.get(timeframe)
    if cfg is None:
        console.print(f"[red]Unknown timeframe: {timeframe}[/red]")
        console.print(f"Valid: {', '.join(TIMEFRAME_CONFIGS.keys())}")
        sys.exit(1)
    return cfg


def _fetch_benchmark(benchmark, years_back=HISTORY_YEARS):
    console.print(f"  Fetching benchmark [bold]{benchmark}[/bold]...")
    df = fetch_index(benchmark, years_back=years_back)
    if df.empty:
        console.print(f"[red]Failed to fetch benchmark '{benchmark}'.[/red]")
        console.print("  [dim]Check the name (e.g. \"NIFTY 50\", \"NIFTY 500\") or your connection.[/dim]")
    return df


def _fetch_universe_with_bar(symbols, years_back=HISTORY_YEARS, force=False, label="Fetching stocks"):
    """Parallel-fetch a deduplicated set of symbols with a live progress bar."""
    unique = sorted(set(symbols))
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task(label, total=len(unique))

        def cb(done, total, sym):
            progress.update(task, completed=done, description=f"{label}: {sym}")

        stock_data, failed = fetch_universe(
            unique, years_back=years_back, force=force, progress_callback=cb,
        )
    return stock_data, failed


def _run_analysis(stock_data, benchmark_df, tf_config, sector_name, sectors_dict):
    freq = tf_config["resample"]
    sma_window = tf_config["sma_window"]
    roc_lookback = tf_config["roc_lookback"]
    rs_periods = tf_config["rs_periods"]

    bench_close = resample_close(benchmark_df, freq)

    rrg_results = {}
    rs_raw = {}
    trend_results = {}

    for sym, df in stock_data.items():
        stock_close = resample_close(df, freq)
        rrg_results[sym] = calculate_rrg(
            stock_close, bench_close, sma_window, roc_lookback, tf_config["tail_length"]
        )
        rs_raw[sym] = calculate_rs_score(stock_close, bench_close, rs_periods)
        trend_results[sym] = check_trend(df["Close"])

    rs_ranked = rank_universe(rs_raw)

    sector_of_sym = {}
    for s_name, s_stocks in sectors_dict.items():
        for st in s_stocks:
            sector_of_sym.setdefault(st, s_name)

    sector_breadths = {}
    for s_name in sectors_dict:
        s_data = {s: stock_data[s] for s in sectors_dict[s_name] if s in stock_data}
        if s_data:
            sector_breadths[s_name] = calculate_sector_breadth(s_data)

    profiles = []
    for sym in stock_data:
        sec = sector_name if sector_name else sector_of_sym.get(sym, "Unknown")
        profiles.append(build_stock_profile(
            sym, sec,
            rrg_results.get(sym),
            rs_ranked.get(sym),
            trend_results.get(sym),
            sector_breadths.get(sec, {}),
        ))

    return profiles, sector_breadths, rrg_results


@click.group()
def cli():
    """Sector Rotation Screener — RRG + RS Ranking + Trend + Breadth (v1, EOD, CLI)."""
    pass


@cli.command()
@click.option("--timeframe", "-t", default="weekly", help="weekly|monthly|quarterly|semi-annual|annual")
@click.option("--top", "-n", default=30, help="Number of top stocks to show")
@click.option("--benchmark", "-b", default=DEFAULT_BENCHMARK, help="Benchmark index")
@click.option("--export", "export_path", default=None, help="Export results to CSV")
def scan(timeframe, top, benchmark, export_path):
    """Full universe scan — top-ranked stocks across all sectors."""
    tf_config = _get_tf_config(timeframe)
    console.print(f"\n[bold]Sector Rotation Scan[/bold] — {timeframe} timeframe")
    console.print(f"Benchmark: {benchmark}\n")

    benchmark_df = _fetch_benchmark(benchmark)
    if benchmark_df.empty:
        return

    all_stocks = get_all_stocks()
    console.print(f"  Fetching {len(all_stocks)} unique stocks...")
    stock_data, failed = _fetch_universe_with_bar(all_stocks, years_back=HISTORY_YEARS)
    console.print(f"  Loaded {len(stock_data)}/{len(all_stocks)} stocks successfully.")
    if not stock_data:
        console.print("[red]No stock data available. Run `update` first or check your connection.[/red]")
        return
    console.print("  Running analysis...")

    profiles, _, _ = _run_analysis(stock_data, benchmark_df, tf_config, None, SECTORS)
    format_scan_table(profiles, title=f"Rotation Scan — {timeframe}", top_n=top)

    if export_path:
        export_csv(profiles, export_path)
        console.print(f"[green]Exported to {export_path}[/green]")


@cli.command()
@click.option("--timeframe", "-t", default="weekly", help="weekly|monthly|quarterly|semi-annual|annual")
@click.option("--benchmark", "-b", default=DEFAULT_BENCHMARK, help="Benchmark index")
def sectors(timeframe, benchmark):
    """Sector rotation overview — each sector's RRG quadrant and breadth."""
    import pandas as pd

    tf_config = _get_tf_config(timeframe)
    console.print(f"\n[bold]Sector Rotation Overview[/bold] — {timeframe} timeframe\n")

    benchmark_df = _fetch_benchmark(benchmark)
    if benchmark_df.empty:
        return

    freq = tf_config["resample"]
    bench_close = resample_close(benchmark_df, freq)

    all_stocks = get_all_stocks()
    console.print(f"  Fetching {len(all_stocks)} unique stocks...")
    universe, failed = _fetch_universe_with_bar(all_stocks, years_back=HISTORY_YEARS)
    console.print(f"  Loaded {len(universe)}/{len(all_stocks)} stocks. Analyzing sectors...\n")
    if not universe:
        console.print("[red]No stock data available. Run `update` first or check your connection.[/red]")
        return

    sector_results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Analyzing sectors", total=len(SECTORS))
        for sector_name, stocks in SECTORS.items():
            progress.update(task, advance=1, description=f"Analyzing {sector_name}")
            stock_data = {s: universe[s] for s in stocks if s in universe}
            if not stock_data:
                continue

            breadth = calculate_sector_breadth(stock_data)

            sector_close_dict = {}
            for sym, df in stock_data.items():
                if "Close" in df.columns and not df["Close"].empty:
                    s = df["Close"].copy()
                    sector_close_dict[sym] = s[~s.index.duplicated(keep="last")]

            rrg = None
            if sector_close_dict:
                combined = pd.DataFrame(sector_close_dict).mean(axis=1).dropna()
                sector_close = resample_close(pd.DataFrame({"Close": combined}), freq)
                rrg = calculate_rrg(
                    sector_close, bench_close,
                    tf_config["sma_window"], tf_config["roc_lookback"], tf_config["tail_length"],
                )

            sector_results.append({
                "sector": sector_name,
                "quadrant": rrg["quadrant"] if rrg else "N/A",
                "rs_ratio": rrg["rs_ratio"] if rrg else None,
                "rs_momentum": rrg["rs_momentum"] if rrg else None,
                "breadth_200": breadth.get("breadth_200"),
                "breadth_50": breadth.get("breadth_50"),
                "breadth_signal": breadth.get("breadth_signal", ""),
                "rotation_score": (
                    (RRG_SCORE_MAP.get((rrg["quadrant"], rrg["direction"]), 50) if rrg else 50) * 0.5
                    + (breadth.get("breadth_200", 50)) * 0.5
                ),
            })

    format_sector_table(sector_results, title=f"Sector Rotation — {timeframe}")


@cli.command()
@click.argument("sector_name")
@click.option("--timeframe", "-t", default="weekly", help="weekly|monthly|quarterly|semi-annual|annual")
@click.option("--benchmark", "-b", default=DEFAULT_BENCHMARK, help="Benchmark index")
def sector(sector_name, timeframe, benchmark):
    """Drill into a specific sector — ranked stocks within it."""
    tf_config = _get_tf_config(timeframe)

    matched = next((s for s in SECTORS if sector_name.lower() in s.lower()), None)
    if not matched:
        console.print(f"[red]Sector '{sector_name}' not found.[/red]")
        console.print(f"Available: {', '.join(sorted(SECTORS.keys()))}")
        return

    console.print(f"\n[bold]{matched}[/bold] — {timeframe} timeframe\n")

    benchmark_df = _fetch_benchmark(benchmark)
    if benchmark_df.empty:
        return

    stock_data, failed = _fetch_universe_with_bar(SECTORS[matched], years_back=HISTORY_YEARS)
    if failed:
        console.print(f"  [yellow]Failed to fetch: {', '.join(failed)}[/yellow]")
    console.print(f"  Loaded {len(stock_data)} stocks. Running analysis...")
    if not stock_data:
        console.print("[red]No stock data available for this sector.[/red]")
        return

    profiles, _, _ = _run_analysis(
        stock_data, benchmark_df, tf_config, matched, {matched: SECTORS[matched]},
    )
    format_scan_table(profiles, title=f"{matched} — {timeframe}")


@cli.command()
@click.argument("symbol")
@click.option("--timeframe", "-t", default="weekly", help="weekly|monthly|quarterly|semi-annual|annual")
@click.option("--benchmark", "-b", default=DEFAULT_BENCHMARK, help="Benchmark index")
def stock(symbol, timeframe, benchmark):
    """Full rotation profile for a single stock."""
    tf_config = _get_tf_config(timeframe)
    symbol = symbol.upper()

    console.print(f"\n[bold]Stock Analysis: {symbol}[/bold] — {timeframe} timeframe\n")

    benchmark_df = _fetch_benchmark(benchmark)
    if benchmark_df.empty:
        return

    df = fetch_stock(symbol, years_back=HISTORY_YEARS)
    if df.empty:
        console.print(f"[red]Failed to fetch data for {symbol}[/red]")
        return

    stock_sector = next((s for s, syms in SECTORS.items() if symbol in syms), "Unknown")

    freq = tf_config["resample"]
    bench_close = resample_close(benchmark_df, freq)
    stock_close = resample_close(df, freq)

    rrg = calculate_rrg(stock_close, bench_close, tf_config["sma_window"],
                        tf_config["roc_lookback"], tf_config["tail_length"])
    rs = calculate_rs_score(stock_close, bench_close, tf_config["rs_periods"])
    rs_ranked = rank_universe({symbol: rs}) if rs else {}
    trend = check_trend(df["Close"])

    breadth = {}
    if stock_sector != "Unknown":
        s_data, _ = _fetch_universe_with_bar(SECTORS[stock_sector], years_back=HISTORY_YEARS, label="Sector breadth")
        if s_data:
            breadth = calculate_sector_breadth(s_data)

    profile = build_stock_profile(symbol, stock_sector, rrg, rs_ranked.get(symbol), trend, breadth)
    format_stock_detail(profile)


@cli.command()
@click.option("--years", default=HISTORY_YEARS, help="Years of historical data to fetch")
def update(years):
    """Rebuild the cache via dual-source reconciliation (purge + NSE + Yahoo + validate)."""
    from data.reconcile import rebuild_universe

    console.print(f"\n[bold]Rebuilding cache[/bold] — dual-source reconciliation ({years}y)\n")
    all_stocks = get_all_stocks()
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task("Reconciling", total=len(all_stocks))

        def cb(done, total, sym):
            progress.update(task, completed=done, description=f"Reconciling {sym}")

        summary = rebuild_universe(all_stocks, DEFAULT_BENCHMARK, years_back=years, progress_cb=cb)

    console.print(
        f"\n  [green]✓ {summary.get('CONFIRMED',0)} confirmed[/green] · "
        f"[yellow]{summary.get('PARTIAL',0)} partial[/yellow] · "
        f"[red]{summary.get('SUSPECT',0)} to review[/red] · "
        f"{summary.get('SINGLE-SOURCE',0)} single-source · "
        f"{summary.get('FAILED',0)} failed\n"
    )


@cli.command()
@click.option("--status", default=None, help="Filter: CONFIRMED|PARTIAL|SUSPECT|SINGLE-SOURCE")
def quality(status):
    """Data-quality report from the dual-source reconciliation."""
    from data.cache import get_connection, load_quality
    from rich.table import Table

    conn = get_connection()
    recs = load_quality(conn)
    conn.close()
    if not recs:
        console.print("[yellow]No QC records. Run `update` first.[/yellow]")
        return

    from collections import Counter
    counts = Counter(r["status"] for r in recs)
    console.print(f"\n[bold]Data Quality[/bold] — {len(recs)} symbols, dual-source validated\n")
    console.print(
        f"  [green]{counts.get('CONFIRMED',0)} confirmed[/green] · "
        f"[yellow]{counts.get('PARTIAL',0)} partial[/yellow] · "
        f"[red]{counts.get('SUSPECT',0)} review[/red] · "
        f"{counts.get('SINGLE-SOURCE',0)} single-source\n"
    )

    shown = [r for r in recs if (not status or r["status"] == status.upper())]
    # default view: show the ones that need attention
    if not status:
        shown = [r for r in recs if r["status"] in ("SUSPECT", "SINGLE-SOURCE")]
        console.print("  [dim]Showing SUSPECT + SINGLE-SOURCE (use --status to filter).[/dim]\n")
    shown.sort(key=lambda r: (r["agree_pct"] is None, r["agree_pct"] or 0))

    t = Table(show_lines=False)
    t.add_column("Symbol", style="bold")
    t.add_column("Status")
    t.add_column("Sources")
    t.add_column("Agree%", justify="right")
    t.add_column("Common", justify="right")
    t.add_column("Repaired", justify="right")
    t.add_column("Last date")
    color = {"CONFIRMED": "green", "PARTIAL": "yellow", "SUSPECT": "red", "SINGLE-SOURCE": "cyan"}
    for r in shown[:60]:
        t.add_row(
            r["symbol"],
            f"[{color.get(r['status'],'white')}]{r['status']}[/]",
            r["sources"] or "—",
            f"{r['agree_pct']:.1f}" if r["agree_pct"] is not None else "—",
            str(r["n_common"]),
            str(r["ticks_repaired"]),
            r["last_date"] or "—",
        )
    console.print(t)
    console.print()


if __name__ == "__main__":
    cli()
