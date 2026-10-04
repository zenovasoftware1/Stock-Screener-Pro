# 📊 Sector Rotation Screener — Setup Guide

A free desktop tool that screens all **NSE Nifty 500** stocks and sectors and ranks them
by a blend of momentum, relative strength, trend and breadth. It runs **on your own
computer** — your data stays private, and there's nothing to pay or sign up for.

> ⚠️ **This is an educational/research screener, not financial advice.** It shows "what
> looks strong now," it does not predict prices or guarantee returns. Do your own research
> and consider a SEBI-registered adviser before investing.

---

## Before you start (one-time, 2 minutes)

You need **Python 3.11 or newer** (free).

- **Check if you have it:**
  - **Mac:** open the **Terminal** app and type `python3 --version`
  - **Windows:** open **Command Prompt** and type `python --version`
- **If you don't have it (or it's older than 3.11):** download it from
  **https://www.python.org/downloads/** and install.
  - **Windows users:** on the first install screen, **tick the box "Add Python to PATH."**

That's the only thing you ever need to install yourself. Everything else is automatic.

---

## Setup — pick ONE of these three ways

### ✅ Option A — Easiest: double-click to start (recommended)

1. Make sure the whole **`Market Move`** folder is saved somewhere on your computer
   (e.g. your Desktop).
2. Open the folder and **double-click**:
   - **Mac:** `Start Screener (Mac).command`
   - **Windows:** `Start Screener (Windows).bat`
3. The first time, it sets everything up automatically (about 1–2 minutes). When it's
   done, your browser opens the screener at **http://localhost:8501**.
4. To use it again later, just double-click the same file — it starts in seconds.

> **Mac tip (one time only):** the first time, macOS will warn *"Apple could not verify
> … is free of malware."* This is Apple's standard notice for any app downloaded from the
> internet — nothing is wrong. Click **Done** (not "Move to Bin"), then open
> **System Settings → Privacy & Security**, scroll to the **Security** section, and click
> **"Open Anyway"**. Double-click the launcher again → **Open**. Done forever.
> (On macOS 14 or older, the shortcut is: right-click the file → **Open** → **Open**.)
> Full steps with pictures-level detail: see **"If Mac Blocks the App — READ THIS.txt"**
> in this folder.

> **To stop the app:** close the black Terminal/Command window that opened.

---

### 🤖 Option B — Let an AI assistant do it (great if you have Claude Code)

1. Open **Claude Code** inside the `Market Move` folder.
2. Open the file **`SETUP_PROMPT.txt`**, copy everything in it, and paste it into Claude.
3. It will install everything and launch the app for you, fixing any errors itself.

---

### 🧑‍💻 Option C — Manual (for the technically comfortable)

Open a terminal **inside the `Market Move` folder** and run:

**Mac / Linux**
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py --server.port 8501
```

**Windows**
```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\streamlit run app.py --server.port 8501
```

Then open **http://localhost:8501** in your browser.

---

## How to use it

The price data is **already included**, so the app works the moment it opens.

1. **Sectors first.** The home page shows all 20 sectors with their rotation quadrant,
   breadth and score, plus a rotation chart. Green/top-right = leading.
2. **Click any sector row** to drill into its ranked stocks.
3. **Sidebar:** change the timeframe (weekly → annual) and benchmark; results update
   instantly. The **data-quality panel** shows how trustworthy each stock's prices are.
4. **Updating prices:** the data is a snapshot from when this was packaged. To pull the
   latest closing prices, click **"Refresh prices"** in the sidebar (~2–3 minutes, needs
   internet). You don't need to do this to try the tool.

Reading the numbers: **RS-Ratio** = is the stock beating the index (above 100 = yes);
**RS-Mom** = is that lead growing (above 100 = yes); **200-DMA** ✅ = in an uptrend;
**Score** = the overall 0–100 rotation rank.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Python is not installed" | Install Python 3.11+ from python.org (Windows: tick *Add to PATH*), then re-run. |
| The browser didn't open | Open it yourself and go to **http://localhost:8501**. |
| "Port 8501 in use" | Another copy is already running — use that browser tab, or close it and restart. |
| Mac blocks the app ("could not verify… malware") | Normal Apple warning, one time only. Click **Done** → System Settings → **Privacy & Security** → **"Open Anyway"** → launch again. See *"If Mac Blocks the App — READ THIS.txt"*. |
| Page says "no data" | Click **Refresh prices** in the sidebar (needs internet). |
| Still stuck | Use **Option B** and let Claude Code fix it, or re-copy the whole folder fresh. |

---

## What's in the folder (you don't need to touch any of this)

`app.py` (the web app) · `cli.py` (command-line version) · `config.py` (settings &
universe) · `indicators/`, `scoring/`, `data/` (the engine) · `data/cache.db` (the
pre-loaded prices) · `requirements.txt` (the package list).

Enjoy — and invest responsibly. 📈
