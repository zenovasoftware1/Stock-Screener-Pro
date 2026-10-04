"""Rich console tables + CSV export for the screener output."""

import csv

from rich.console import Console
from rich.table import Table
from rich.text import Text

QUADRANT_COLORS = {
    "Leading": "green",
    "Improving": "cyan",
    "Weakening": "yellow",
    "Lagging": "red",
    "N/A": "dim",
}

BREADTH_COLORS = {
    "Strong": "green",
    "Mixed": "yellow",
    "Weak": "red",
}


def format_scan_table(profiles, title="Sector Rotation Scan", top_n=None):
    console = Console()
    sorted_profiles = sorted(profiles, key=lambda p: p["rotation_score"], reverse=True)
    if top_n:
        sorted_profiles = sorted_profiles[:top_n]

    table = Table(title=title, show_lines=False, pad_edge=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Stock", style="bold", width=12)
    table.add_column("Sector", width=24)
    table.add_column("Quadrant", width=12)
    table.add_column("RS Rank", justify="right", width=8)
    table.add_column("200-DMA", width=12)
    table.add_column("Breadth", justify="right", width=10)
    table.add_column("Score", justify="right", width=7)

    for i, p in enumerate(sorted_profiles, 1):
        quadrant = p.get("quadrant", "N/A")
        quadrant_text = Text(quadrant, style=QUADRANT_COLORS.get(quadrant, "white"))

        rs_pct = p.get("rs_percentile")
        rs_text = f"{rs_pct:.0f}%" if rs_pct is not None else "N/A"

        above = p.get("above_200dma")
        pct_dma = p.get("pct_from_dma")
        if above is not None and pct_dma is not None:
            mark = "[green]✓[/green]" if above else "[red]✗[/red]"
            sign = "+" if pct_dma >= 0 else ""
            dma_text = f"{mark} {sign}{pct_dma:.1f}%"
        else:
            dma_text = "N/A"

        breadth = p.get("sector_breadth_200")
        b_signal = p.get("breadth_signal", "")
        breadth_text = Text(
            f"{breadth:.0f}%" if breadth is not None else "N/A",
            style=BREADTH_COLORS.get(b_signal, "white"),
        )

        score = p.get("rotation_score", 0)
        if score >= 70:
            score_style = "bold green"
        elif score >= 50:
            score_style = "yellow"
        else:
            score_style = "red"

        table.add_row(
            str(i),
            p["symbol"],
            p.get("sector", ""),
            quadrant_text,
            rs_text,
            dma_text,
            breadth_text,
            Text(f"{score:.0f}", style=score_style),
        )

    console.print()
    console.print(table)
    console.print()


def format_sector_table(sector_results, title="Sector Rotation Overview"):
    console = Console()
    table = Table(title=title, show_lines=False, pad_edge=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Sector", style="bold", width=28)
    table.add_column("Quadrant", width=12)
    table.add_column("RS-Ratio", justify="right", width=10)
    table.add_column("RS-Mom", justify="right", width=10)
    table.add_column("Breadth 200", justify="right", width=12)
    table.add_column("Breadth 50", justify="right", width=12)
    table.add_column("Signal", width=8)

    sorted_sectors = sorted(sector_results, key=lambda s: s.get("rotation_score", 0), reverse=True)

    for i, s in enumerate(sorted_sectors, 1):
        quadrant = s.get("quadrant", "N/A")
        b_signal = s.get("breadth_signal", "")
        table.add_row(
            str(i),
            s.get("sector", ""),
            Text(quadrant, style=QUADRANT_COLORS.get(quadrant, "white")),
            f"{s.get('rs_ratio', 0):.2f}" if s.get("rs_ratio") is not None else "N/A",
            f"{s.get('rs_momentum', 0):.2f}" if s.get("rs_momentum") is not None else "N/A",
            f"{s.get('breadth_200', 0):.0f}%" if s.get("breadth_200") is not None else "N/A",
            f"{s.get('breadth_50', 0):.0f}%" if s.get("breadth_50") is not None else "N/A",
            Text(b_signal, style=BREADTH_COLORS.get(b_signal, "white")),
        )

    console.print()
    console.print(table)
    console.print()


def format_stock_detail(profile):
    console = Console()
    console.print()
    console.print(f"[bold]═══ {profile['symbol']} — {profile.get('sector', 'N/A')} ═══[/bold]")
    console.print()

    quadrant = profile.get("quadrant", "N/A")
    q_color = QUADRANT_COLORS.get(quadrant, "white")
    console.print(f"  Rotation Score:  [bold]{profile.get('rotation_score', 'N/A')}[/bold]")
    console.print(f"  RRG Quadrant:    [{q_color}]{quadrant}[/{q_color}] ({profile.get('direction', '')})")
    console.print(f"  RS-Ratio:        {profile.get('rs_ratio', 'N/A')}")
    console.print(f"  RS-Momentum:     {profile.get('rs_momentum', 'N/A')}")
    console.print(f"  RS Percentile:   {profile.get('rs_percentile', 'N/A')}%")

    above = profile.get("above_200dma")
    pct = profile.get("pct_from_dma")
    if above is not None and pct is not None:
        mark = "[green]Above[/green]" if above else "[red]Below[/red]"
        console.print(f"  200-DMA:         {mark} ({'+' if pct >= 0 else ''}{pct:.1f}%)")

    breadth = profile.get("sector_breadth_200")
    if breadth is not None:
        b_signal = profile.get("breadth_signal", "")
        b_color = BREADTH_COLORS.get(b_signal, "white")
        console.print(f"  Sector Breadth:  [{b_color}]{breadth:.0f}% ({b_signal})[/{b_color}]")

    console.print()


def export_csv(profiles, filepath):
    if not profiles:
        return
    fields = [
        "symbol", "sector", "rotation_score", "quadrant", "direction",
        "rs_ratio", "rs_momentum", "rs_percentile",
        "above_200dma", "pct_from_dma",
        "sector_breadth_200", "breadth_signal",
    ]
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for p in sorted(profiles, key=lambda p: p["rotation_score"], reverse=True):
            writer.writerow(p)
