"""Sector Rotation Screener — Streamlit UI.

Cache-first: reads the warmed SQLite cache for instant rendering. A sidebar button
explicitly refreshes EOD prices from NSE. Flow: see all sectors (quadrant + breadth +
score, with an RRG quadrant chart) → click a sector → drill into its ranked stocks.

Run:
    streamlit run app.py        →  http://localhost:8501
"""

import altair as alt
import pandas as pd
import streamlit as st

import screener_core as core

st.set_page_config(page_title="Sector Rotation Screener", page_icon="📊", layout="wide")

QUADRANT_COLOR = {
    "Leading": "#16a34a",     # green
    "Improving": "#0891b2",   # cyan
    "Weakening": "#ca8a04",   # amber
    "Lagging": "#dc2626",     # red
    "N/A": "#6b7280",
}
SIGNAL_COLOR = {"Strong": "#16a34a", "Mixed": "#ca8a04", "Weak": "#dc2626"}


# --------------------------------------------------------------------------- #
# cached compute (keyed on cache version so it refreshes only after a data pull)
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def _sectors(timeframe, benchmark, version):
    return core.compute_sectors(timeframe, benchmark)


@st.cache_data(show_spinner=False)
def _sector_stocks(sector, timeframe, benchmark, version):
    return core.compute_sector_stocks(sector, timeframe, benchmark)


# --------------------------------------------------------------------------- #
# sidebar — controls + explicit refresh
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ Controls")
    timeframe = st.selectbox("Timeframe", core.TIMEFRAMES, index=0)
    benchmark = st.selectbox("Benchmark", core.BENCHMARKS, index=0)

    stats = core.cache_stats()
    st.caption(f"Cache: **{stats['cached']}/{stats['total']}** stocks loaded")

    # Data-quality panel from dual-source reconciliation
    qsum = core.quality_summary()
    if qsum["n"]:
        c = qsum["counts"]
        conf = c.get("CONFIRMED", 0)
        st.caption(
            f"Data quality (yfinance ✓ vs NSE): "
            f":green[{conf} confirmed] · :orange[{c.get('PARTIAL',0)} partial] · "
            f":red[{c.get('SUSPECT',0)} review] · {c.get('SINGLE-SOURCE',0)} single-src"
        )
        with st.expander("What does this mean?"):
            st.markdown(
                "Every stock's prices are fetched from **two independent sources** and "
                "cross-checked day-by-day:\n"
                "- **confirmed** — both sources agree (≥97% of days). High trust.\n"
                "- **partial** — minor disagreements (corporate actions / stale feed).\n"
                "- **review** — sources disagree enough to verify manually before official use.\n"
                "- **single-src** — only one source available (noted, not cross-checked).\n\n"
                "Prices are split/dividend **adjusted**; obvious bad ticks are auto-repaired."
            )

    st.divider()
    st.subheader("🔄 Data")
    st.caption("EOD prices, split/dividend-adjusted. The cache ships pre-loaded — only "
               "refresh when you want the latest closes (takes ~2–3 minutes).")
    if st.button("Refresh prices", type="primary", width="stretch"):
        prog = st.progress(0.0, text="Starting…")

        def cb(done, total, sym):
            prog.progress(done / max(total, 1), text=f"Updating {sym} ({done}/{total})")

        with st.spinner("Fetching latest EOD prices…"):
            summary = core.refresh_cache(progress_cb=cb)
        prog.empty()
        st.cache_data.clear()
        c = summary if isinstance(summary, dict) else {}
        upd, fail = c.get("updated", 0), c.get("failed", 0)
        if c.get("restored_backup"):
            st.warning(
                "A problem was detected during the refresh, so your previous data was "
                "**automatically restored** from a backup. The screener is unaffected — "
                "please try refreshing again later."
            )
        elif upd:
            msg = f"Updated {upd} stocks with the latest prices."
            if fail:
                msg += f" {fail} couldn't be refreshed (their existing data was kept untouched)."
            st.success(msg)
        else:
            st.warning(
                f"Could not fetch new prices right now ({fail} failed) — likely a data-source "
                "or connection issue. Your existing data was kept; the screener still works. "
                "Try again later."
            )
    st.caption("ℹ️ For NSE dual-source cross-validation, run `python cli.py update` in a "
               "terminal (slower, optional).")

    st.divider()
    show_chart = st.toggle("Show RRG quadrant chart", value=True)


# --------------------------------------------------------------------------- #
# main — sector overview, then drill-down on selection
# --------------------------------------------------------------------------- #
st.title("📊 Sector Rotation Screener")
st.caption(f"Nifty 500 · {timeframe} timeframe · benchmark {benchmark} · "
           "RRG + RS Ranking + 200-DMA Trend + Breadth")

version = core.cache_version()
rows, meta = _sectors(timeframe, benchmark, version)

if meta.get("error"):
    st.error(meta["error"])
    st.info("Use **Refresh data from NSE** in the sidebar to warm the cache.")
    st.stop()
if not rows:
    st.warning("No cached sector data yet. Use **Refresh data from NSE** in the sidebar.")
    st.stop()


# --------------------------------------------------------------------------- #
# stock search — full profile for any Nifty 500 stock
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def _names():
    return core.symbol_names()


with st.container():
    st.subheader("🔎 Search any stock")
    names = _names()
    options = [""] + sorted(
        f"{s} — {names.get(s, '')}" if names.get(s) else s for s in core.get_all_stocks()
    )
    choice = st.selectbox(
        "Type a symbol or company name",
        options, index=0,
        help="Tip: type ONE word — e.g. 'RELIANCE', 'Tata', 'rectifiers'. The list matches "
             "the official NSE name, so '&' or extra words can miss (e.g. Transformers & "
             "Rectifiers is listed as 'TARIL — Transformers And Rectifiers (India) Ltd.').",
    )
    st.caption("💡 Type a single word for best results (e.g. 'rectifiers' finds TARIL).")
    if choice:
        sym = choice.split(" — ")[0].strip()
        s_sector = core.sector_of(sym)
        if s_sector is None:
            st.warning(f"{sym} is not in the Nifty 500 universe.")
        else:
            s_profiles, s_meta = _sector_stocks(s_sector, timeframe, benchmark, version)
            prof = next((p for p in s_profiles if p["symbol"] == sym), None)
            if s_meta.get("error") or prof is None:
                st.warning(s_meta.get("error") or f"No data available for {sym} on this timeframe.")
            else:
                rank = s_profiles.index(prof) + 1
                q = prof.get("quadrant", "N/A")
                q_color = {"Leading": "green", "Improving": "blue",
                           "Weakening": "orange", "Lagging": "red"}.get(q, "gray")
                _QC = {"CONFIRMED": "✅ confirmed", "PARTIAL": "➖ partial",
                       "SUSPECT": "⚠️ review", "SINGLE-SOURCE": "single-source"}
                st.markdown(
                    f"### {sym} — {names.get(sym, '')}  \n"
                    f"**Sector:** {s_sector} (ranked **#{rank} of {len(s_profiles)}** in sector) · "
                    f"**Quadrant:** :{q_color}[{q}] ({prof.get('direction', '')}) · "
                    f"**Data:** {_QC.get(prof.get('qc_status'), '—')}"
                )
                c1, c2, c3, c4, c5 = st.columns(5)
                score = prof.get("rotation_score")
                c1.metric("Rotation Score", f"{score:.0f}/100" if score is not None else "—")
                rsp = prof.get("rs_percentile")
                c2.metric("RS Rank (in sector)", f"{rsp:.0f}%" if rsp is not None else "—")
                above, pct = prof.get("above_200dma"), prof.get("pct_from_dma")
                c3.metric("200-DMA", ("Above ✅" if above else "Below ❌") if above is not None else "—",
                          delta=f"{pct:+.1f}%" if pct is not None else None)
                rsr = prof.get("rs_ratio")
                c4.metric("RS-Ratio", f"{rsr:.2f}" if rsr is not None else "—",
                          help="Above 100 = beating the benchmark")
                rsm = prof.get("rs_momentum")
                c5.metric("RS-Momentum", f"{rsm:.2f}" if rsm is not None else "—",
                          help="Above 100 = the lead is growing")
                b = prof.get("sector_breadth_200")
                bs = prof.get("breadth_signal", "")
                if b is not None:
                    st.caption(f"Sector breadth: {b:.0f}% of {s_sector} stocks above their "
                               f"200-DMA ({bs}). Numbers match the sector drill-down below.")

st.divider()

df = pd.DataFrame(rows)
# Coerce numerics so missing values render as blank (not the string "None") and
# NumberColumn formatting works.
for _c in ["rs_ratio", "rs_momentum", "breadth_200", "breadth_50", "rotation_score"]:
    df[_c] = pd.to_numeric(df[_c], errors="coerce")

# ---- RRG quadrant scatter (sectors) ----
if show_chart:
    cdf = df.dropna(subset=["rs_ratio", "rs_momentum"]).copy()
    if cdf.empty:
        st.info(
            f"No RRG available at the **{timeframe}** timeframe yet — the longer timeframes "
            "need several years of history. Use **Refresh data from NSE** (sidebar) to pull "
            f"{core.HISTORY_YEARS}y of data, or use **weekly/monthly**. The sector table below "
            "still ranks by breadth and trend."
        )
    else:
        # Zoom tightly to the data (RRG values cluster near 100) and always include the
        # 100/100 crosshair. zero=False/nice=False stop Altair from snapping the axis to 0.
        xs = list(cdf["rs_ratio"]) + [100.0]
        ys = list(cdf["rs_momentum"]) + [100.0]
        pad = 0.6
        xscale = alt.Scale(domain=[min(xs) - pad, max(xs) + pad], zero=False, nice=False)
        yscale = alt.Scale(domain=[min(ys) - pad, max(ys) + pad], zero=False, nice=False)
        pts = alt.Chart(cdf).mark_circle(size=300, opacity=0.85, stroke="white", strokeWidth=1).encode(
            x=alt.X("rs_ratio:Q", scale=xscale, title="RS-Ratio  (→ stronger vs benchmark)"),
            y=alt.Y("rs_momentum:Q", scale=yscale, title="RS-Momentum  (↑ improving)"),
            color=alt.Color("quadrant:N",
                            scale=alt.Scale(domain=list(QUADRANT_COLOR), range=list(QUADRANT_COLOR.values())),
                            legend=alt.Legend(title="Quadrant")),
            tooltip=[alt.Tooltip("sector:N", title="Sector"),
                     alt.Tooltip("quadrant:N", title="Quadrant"),
                     alt.Tooltip("rs_ratio:Q", title="RS-Ratio", format=".2f"),
                     alt.Tooltip("rs_momentum:Q", title="RS-Mom", format=".2f"),
                     alt.Tooltip("breadth_200:Q", title="Breadth 200", format=".0f"),
                     alt.Tooltip("rotation_score:Q", title="Score", format=".0f")],
        )
        vline = alt.Chart(pd.DataFrame({"x": [100.0]})).mark_rule(
            strokeDash=[4, 4], color="#888").encode(x=alt.X("x:Q", scale=xscale))
        hline = alt.Chart(pd.DataFrame({"y": [100.0]})).mark_rule(
            strokeDash=[4, 4], color="#888").encode(y=alt.Y("y:Q", scale=yscale))
        st.altair_chart((vline + hline + pts).properties(height=440).interactive(), width="stretch")
        st.caption("Top-right **Leading** · top-left **Improving** · bottom-right **Weakening** · "
                   "bottom-left **Lagging**. Dashed lines = benchmark (100). Hover a point for the "
                   "sector name (points cluster near 100 by design — the axes are zoomed in).")

st.subheader("Sectors")
st.caption("Click a row to drill into that sector's stocks.")

# ---- sector table with row selection ----
table = df.assign(
    Cached=df.apply(lambda r: f"{r['n_cached']}/{r['n_total']}", axis=1),
)[["sector", "quadrant", "rotation_score", "rs_ratio", "rs_momentum",
   "breadth_200", "breadth_50", "breadth_signal", "Cached"]]

event = st.dataframe(
    table,
    width="stretch",
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "sector": "Sector",
        "quadrant": "Quadrant",
        "rotation_score": st.column_config.ProgressColumn(
            "Score", min_value=0, max_value=100, format="%d"),
        "rs_ratio": st.column_config.NumberColumn("RS-Ratio", format="%.2f"),
        "rs_momentum": st.column_config.NumberColumn("RS-Mom", format="%.2f"),
        "breadth_200": st.column_config.NumberColumn("Breadth 200", format="%d%%"),
        "breadth_50": st.column_config.NumberColumn("Breadth 50", format="%d%%"),
        "breadth_signal": "Signal",
        "Cached": "Cached",
    },
)

sel_rows = event.selection.rows if event and event.selection else []
if not sel_rows:
    st.info("⬆️ Select a sector above to see its ranked stocks.")
    st.stop()

sector = df.iloc[sel_rows[0]]["sector"]

# --------------------------------------------------------------------------- #
# drill-down — ranked stocks in the chosen sector
# --------------------------------------------------------------------------- #
st.divider()
st.subheader(f"🔍 {sector}")

profiles, pmeta = _sector_stocks(sector, timeframe, benchmark, version)
if pmeta.get("error"):
    st.warning(pmeta["error"])
    st.stop()

pdf = pd.DataFrame(profiles)
for _c in ["rotation_score", "rs_percentile", "rs_ratio", "rs_momentum", "pct_from_dma"]:
    pdf[_c] = pd.to_numeric(pdf[_c], errors="coerce")
pdf["DMA"] = pdf.apply(
    lambda r: ("✅ " if r["above_200dma"] else "❌ ") +
              (f"{r['pct_from_dma']:+.1f}%" if r["pct_from_dma"] is not None else "—")
    if r["above_200dma"] is not None else "—",
    axis=1,
)
_QC_BADGE = {"CONFIRMED": "✅ confirmed", "PARTIAL": "➖ partial",
             "SUSPECT": "⚠️ review", "SINGLE-SOURCE": "1-source"}
pdf["Data"] = pdf.get("qc_status").map(lambda s: _QC_BADGE.get(s, "—")) \
    if "qc_status" in pdf.columns else "—"
view = pdf[["symbol", "quadrant", "rotation_score", "rs_percentile", "rs_ratio",
            "rs_momentum", "DMA", "Data"]]

st.dataframe(
    view,
    width="stretch",
    hide_index=True,
    column_config={
        "symbol": "Stock",
        "quadrant": "Quadrant",
        "rotation_score": st.column_config.ProgressColumn(
            "Score", min_value=0, max_value=100, format="%d"),
        "rs_percentile": st.column_config.NumberColumn(
            "RS Rank (in sector)", format="%d%%",
            help="Percentile rank of relative strength WITHIN this sector (not the whole index)."),
        "rs_ratio": st.column_config.NumberColumn("RS-Ratio", format="%.2f"),
        "rs_momentum": st.column_config.NumberColumn("RS-Mom", format="%.2f"),
        "DMA": "200-DMA",
        "Data": st.column_config.TextColumn(
            "Data", help="Dual-source validation status for this stock's prices."),
    },
)

# quick distribution of quadrants within the sector
counts = pdf["quadrant"].value_counts()
cols = st.columns(len(counts))
for col, (q, n) in zip(cols, counts.items()):
    col.metric(q, n)
