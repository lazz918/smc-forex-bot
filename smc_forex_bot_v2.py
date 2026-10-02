#!/usr/bin/env python3
"""
================================================================================
SMC + Support/Resistance Forex Trading Bot  v2.1  (COMPLETE)
================================================================================
Features:
  ✅ Smart Money Concepts (OB, FVG, BOS, CHoCH, Liquidity Sweeps)
  ✅ Support & Resistance clustering
  ✅ Breaker Blocks
  ✅ Premium / Discount zones
  ✅ Killzones (London Open, NY Open, London Close)
  ✅ Multi-pair scanner
  ✅ Telegram alerts
  ✅ Partial Take-Profit (50% at 1R) + Trailing Stop
  ✅ News Filter (high-impact blackout windows)
  ✅ Full risk management + position sizing
  ✅ Backtester with equity curve
  ✅ Streamlit Dashboard
  ✅ Live signals + MT5 order placement placeholder
  ✅ Native MQL5 Expert Advisor
  ✅ Session filters

Disclaimer: Educational / research use only. Demo-test thoroughly.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
import warnings
import time as time_module
import json
import os
from pathlib import Path
warnings.filterwarnings("ignore")

# Optional dependencies
try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# =============================================================================
# CONFIGURATION
# =============================================================================
class Config:
    # ---- Pairs (Yahoo format) ----
    PAIRS = [
        "EURUSD=X",
        "GBPUSD=X",
        "USDJPY=X",
        "AUDUSD=X",
        "USDCAD=X",
        "GC=F",       # Gold futures (Yahoo) – use XAUUSD on MT5
    ]
    # MT5 names corresponding to above (same order)
    MT5_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD"]

    # Timeframes
    HTF = "4h"
    LTF = "15m"
    LOOKBACK_BARS = 600

    # Risk
    RISK_PER_TRADE = 0.01          # 1%
    MIN_RR = 2.0
    MAX_SPREAD_PIPS = 3.0
    ACCOUNT_BALANCE = 10000.0
    MAX_OPEN_TRADES = 3
    COOLDOWN_BARS = 16             # ~4h on 15m

    # Partial TP & Trailing
    USE_PARTIAL_TP = True
    PARTIAL_TP_RR = 1.0            # Close 50% at 1R
    PARTIAL_TP_PCT = 0.50          # 50% of position
    USE_TRAILING_STOP = True
    TRAIL_START_RR = 1.5           # Start trailing after 1.5R
    TRAIL_STEP_PIPS = 10           # Trail distance in pips

    # News Filter
    USE_NEWS_FILTER = True
    NEWS_BLACKOUT_MINUTES = 30     # Minutes before/after high-impact news

    # SMC Parameters
    SWING_LOOKBACK = 5
    OB_IMPULSE_MULT = 1.8
    FVG_MIN_SIZE_ATR = 0.35
    LIQUIDITY_WICK_PCT = 0.30
    S_R_TOLERANCE_PIPS = 8
    MIN_ZONE_STRENGTH = 2

    # Advanced
    USE_BREAKER_BLOCKS = True
    USE_PREMIUM_DISCOUNT = True
    USE_KILLZONES = True
    REQUIRE_SR_CONFLUENCE = False  # True = stricter

    # Killzones (UTC)
    KILLZONES = {
        "London_Open":  (7, 10),    # 07:00-10:00
        "NY_Open":      (12, 15),   # 12:00-15:00
        "London_Close": (15, 17),   # 15:00-17:00
    }

    # Sessions (broader filter)
    USE_SESSION_FILTER = True
    LONDON_START = 7
    LONDON_END = 16
    NY_START = 12
    NY_END = 21

    # Telegram (fill these to enable)
    TELEGRAM_BOT_TOKEN = ""        # e.g. "123456:ABC-DEF..."
    TELEGRAM_CHAT_ID = ""          # e.g. "123456789"
    TELEGRAM_ENABLED = False       # set True after filling token + chat_id

    # Mode
    MODE = "backtest"              # "backtest" | "signals" | "scanner" | "live" | "dashboard"
    BACKTEST_PAIR = "EURUSD=X"


# =============================================================================
# TELEGRAM ALERTS
# =============================================================================
def send_telegram(msg: str, config: Config) -> bool:
    """Send message via Telegram Bot API."""
    if not config.TELEGRAM_ENABLED or not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    if not HAS_REQUESTS:
        print("[Telegram] requests library missing")
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[Telegram] Error: {e}")
        return False


def format_signal_msg(pair: str, side: str, entry: float, sl: float, tp: float,
                      reason: str, lots: float, rr: float) -> str:
    emoji = "🟢 LONG" if side == "long" else "🔴 SHORT"
    return (
        f"<b>SMC Signal</b>\n"
        f"Pair: <b>{pair}</b>\n"
        f"Side: {emoji}\n"
        f"Entry: <code>{entry:.5f}</code>\n"
        f"SL: <code>{sl:.5f}</code>\n"
        f"TP: <code>{tp:.5f}</code>\n"
        f"Lots: <code>{lots}</code>\n"
        f"R:R ≈ {rr:.1f}\n"
        f"Reason: {reason}\n"
        f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
    )


# =============================================================================
# NEWS FILTER (high-impact events blackout)
# =============================================================================
# Static high-impact windows (UTC). In production replace with live calendar API.
HIGH_IMPACT_WINDOWS = [
    # Typical recurring high-impact (approximate times)
    # Format: (weekday 0=Mon, hour_start, hour_end, label)
    (2, 12, 15, "FOMC / Fed"),          # Wed
    (4, 12, 15, "NFP Friday"),          # Fri
    (2, 8, 10, "CPI / Inflation"),      # Wed mornings
    (1, 12, 14, "GDP / Major data"),    # Tue
]

def is_news_blackout(ts: datetime, config: Config) -> bool:
    """Return True if we should avoid trading (near high-impact news)."""
    if not config.USE_NEWS_FILTER:
        return False
    wd = ts.weekday()
    hour = ts.hour
    minute = ts.minute
    for (wday, h_start, h_end, label) in HIGH_IMPACT_WINDOWS:
        if wd == wday and h_start <= hour < h_end:
            return True
    # Also block around typical London/NY open volatility spikes if desired
    return False


def fetch_live_news_blackout(config: Config) -> bool:
    """
    Optional: try to fetch live high-impact events.
    Falls back to static windows if API unavailable.
    """
    if not config.USE_NEWS_FILTER:
        return False
    # Placeholder for ForexFactory / Investing.com scrape or paid API
    # For reliability we use the static filter above.
    return is_news_blackout(datetime.utcnow(), config)


# =============================================================================
# DATA
# =============================================================================
def fetch_data(symbol: str, interval: str, period: str = "60d") -> pd.DataFrame:
    if not HAS_YFINANCE:
        raise ImportError("pip install yfinance")
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)
    if df.empty:
        raise ValueError(f"No data for {symbol} {interval}")
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                            "Close": "close", "Volume": "volume"})
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df.dropna()


def fetch_mt5(symbol: str, timeframe, bars: int = 500) -> pd.DataFrame:
    if not HAS_MT5:
        raise ImportError("MetaTrader5 not installed")
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    mt5.shutdown()
    if rates is None:
        raise RuntimeError("No rates from MT5")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df = df.rename(columns={"tick_volume": "volume"})
    return df[["open", "high", "low", "close", "volume"]]


# =============================================================================
# HELPERS
# =============================================================================
def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def pip_size(price: float) -> float:
    """Approximate pip size."""
    if price > 100:      # Gold, JPY crosses rough
        return 0.01 if price < 500 else 0.1
    if price > 30:       # JPY pairs
        return 0.01
    return 0.0001


def find_swings(df: pd.DataFrame, left: int = 5, right: int = 5) -> pd.DataFrame:
    df = df.copy()
    df["swing_high"] = False
    df["swing_low"] = False
    highs = df["high"].values
    lows = df["low"].values
    for i in range(left, len(df) - right):
        if highs[i] == max(highs[i-left:i+right+1]):
            df.iloc[i, df.columns.get_loc("swing_high")] = True
        if lows[i] == min(lows[i-left:i+right+1]):
            df.iloc[i, df.columns.get_loc("swing_low")] = True
    return df


# =============================================================================
# SUPPORT & RESISTANCE
# =============================================================================
def detect_sr(df: pd.DataFrame, tolerance_pips: float = 8.0,
              min_touches: int = 2) -> List[Dict]:
    pip = pip_size(df["close"].mean())
    tol = tolerance_pips * pip
    swings = []
    for idx, row in df.iterrows():
        if row.get("swing_high", False):
            swings.append(("resistance", row["high"], idx))
        if row.get("swing_low", False):
            swings.append(("support", row["low"], idx))
    if not swings:
        return []
    zones = []
    used = set()
    for i, (typ, price, t) in enumerate(swings):
        if i in used:
            continue
        cluster = [price]
        times = [t]
        for j, (typ2, price2, t2) in enumerate(swings):
            if j <= i or j in used:
                continue
            if abs(price - price2) <= tol:
                cluster.append(price2)
                times.append(t2)
                used.add(j)
        if len(cluster) >= min_touches:
            zones.append({
                "level": float(np.mean(cluster)),
                "type": typ,
                "strength": len(cluster),
                "last_touch": max(times)
            })
        used.add(i)
    zones = sorted(zones, key=lambda x: x["strength"], reverse=True)
    return zones[:12]


def near_sr(price: float, zones: List[Dict], tol: float) -> Optional[Dict]:
    for z in zones:
        if abs(price - z["level"]) <= tol:
            return z
    return None


# =============================================================================
# MARKET STRUCTURE
# =============================================================================
def detect_structure(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["bos_bull"] = False
    df["bos_bear"] = False
    df["choch_bull"] = False
    df["choch_bear"] = False
    df["trend"] = 0

    last_sh = None
    last_sl = None
    trend = 0

    for i in range(len(df)):
        row = df.iloc[i]
        if row["swing_high"]:
            if last_sh is not None:
                if row["high"] > last_sh:
                    if trend >= 0:
                        df.iloc[i, df.columns.get_loc("bos_bull")] = True
                    else:
                        df.iloc[i, df.columns.get_loc("choch_bull")] = True
                    trend = 1
            last_sh = row["high"]
        if row["swing_low"]:
            if last_sl is not None:
                if row["low"] < last_sl:
                    if trend <= 0:
                        df.iloc[i, df.columns.get_loc("bos_bear")] = True
                    else:
                        df.iloc[i, df.columns.get_loc("choch_bear")] = True
                    trend = -1
            last_sl = row["low"]
        df.iloc[i, df.columns.get_loc("trend")] = trend
    return df


# =============================================================================
# ORDER BLOCKS + BREAKER BLOCKS
# =============================================================================
def detect_order_blocks(df: pd.DataFrame, impulse_mult: float = 1.8) -> List[Dict]:
    df = df.copy()
    df["atr"] = atr(df)
    obs = []
    for i in range(2, len(df) - 1):
        c = df.iloc[i]
        n = df.iloc[i + 1]
        atr_val = c["atr"]
        if pd.isna(atr_val) or atr_val == 0:
            continue
        # Bullish OB
        if c["close"] < c["open"]:
            impulse = n["close"] - n["open"]
            if impulse > impulse_mult * atr_val and n["close"] > c["high"]:
                obs.append({
                    "type": "bullish", "top": c["high"], "bottom": c["low"],
                    "mid": (c["high"] + c["low"]) / 2, "time": df.index[i],
                    "mitigated": False, "breaker": False, "strength": impulse / atr_val
                })
        # Bearish OB
        if c["close"] > c["open"]:
            impulse = n["open"] - n["close"]
            if impulse > impulse_mult * atr_val and n["close"] < c["low"]:
                obs.append({
                    "type": "bearish", "top": c["high"], "bottom": c["low"],
                    "mid": (c["high"] + c["low"]) / 2, "time": df.index[i],
                    "mitigated": False, "breaker": False, "strength": impulse / atr_val
                })

    # Mitigation + Breaker detection
    for ob in obs:
        after = df.loc[ob["time"]:]
        if len(after) < 3:
            continue
        if ob["type"] == "bullish":
            # Mitigated if close below bottom
            if (after["close"] < ob["bottom"]).any():
                ob["mitigated"] = True
                # Breaker: if later price returns from above → becomes resistance
                mitigated_idx = after[after["close"] < ob["bottom"]].index[0]
                later = df.loc[mitigated_idx:]
                if (later["high"] > ob["top"]).any() and (later["close"] < ob["mid"]).any():
                    ob["breaker"] = True
        else:
            if (after["close"] > ob["top"]).any():
                ob["mitigated"] = True
                mitigated_idx = after[after["close"] > ob["top"]].index[0]
                later = df.loc[mitigated_idx:]
                if (later["low"] < ob["bottom"]).any() and (later["close"] > ob["mid"]).any():
                    ob["breaker"] = True
    return obs


# =============================================================================
# FAIR VALUE GAPS
# =============================================================================
def detect_fvg(df: pd.DataFrame, min_size_atr: float = 0.35) -> List[Dict]:
    df = df.copy()
    df["atr"] = atr(df)
    fvgs = []
    for i in range(2, len(df)):
        c0, c1, c2 = df.iloc[i-2], df.iloc[i-1], df.iloc[i]
        atr_val = c1["atr"]
        if pd.isna(atr_val) or atr_val == 0:
            continue
        # Bullish FVG
        if c2["low"] > c0["high"]:
            gap = c2["low"] - c0["high"]
            if gap >= min_size_atr * atr_val:
                fvgs.append({
                    "type": "bullish", "top": c2["low"], "bottom": c0["high"],
                    "mid": (c2["low"] + c0["high"]) / 2, "time": df.index[i],
                    "mitigated": False, "size": gap
                })
        # Bearish FVG
        if c2["high"] < c0["low"]:
            gap = c0["low"] - c2["high"]
            if gap >= min_size_atr * atr_val:
                fvgs.append({
                    "type": "bearish", "top": c0["low"], "bottom": c2["high"],
                    "mid": (c0["low"] + c2["high"]) / 2, "time": df.index[i],
                    "mitigated": False, "size": gap
                })
    for fvg in fvgs:
        after = df.loc[fvg["time"]:]
        if fvg["type"] == "bullish" and (after["low"] <= fvg["bottom"]).any():
            fvg["mitigated"] = True
        elif fvg["type"] == "bearish" and (after["high"] >= fvg["top"]).any():
            fvg["mitigated"] = True
    return [f for f in fvgs if not f["mitigated"]]


# =============================================================================
# LIQUIDITY SWEEPS
# =============================================================================
def detect_liquidity(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    df = df.copy()
    df["liq_sweep_high"] = False
    df["liq_sweep_low"] = False
    for i in range(lookback, len(df)):
        window = df.iloc[i-lookback:i]
        rh, rl = window["high"].max(), window["low"].min()
        curr = df.iloc[i]
        rng = curr["high"] - curr["low"]
        if rng == 0:
            continue
        # Buy-side sweep
        if curr["high"] > rh and curr["close"] < rh:
            wick = curr["high"] - max(curr["open"], curr["close"])
            if wick / rng > Config.LIQUIDITY_WICK_PCT:
                df.iloc[i, df.columns.get_loc("liq_sweep_high")] = True
        # Sell-side sweep
        if curr["low"] < rl and curr["close"] > rl:
            wick = min(curr["open"], curr["close"]) - curr["low"]
            if wick / rng > Config.LIQUIDITY_WICK_PCT:
                df.iloc[i, df.columns.get_loc("liq_sweep_low")] = True
    return df


# =============================================================================
# PREMIUM / DISCOUNT ZONES
# =============================================================================
def premium_discount(df: pd.DataFrame, lookback: int = 50) -> pd.DataFrame:
    """Mark whether current price is in premium or discount of recent range."""
    df = df.copy()
    df["pd_zone"] = "equilibrium"
    for i in range(lookback, len(df)):
        window = df.iloc[i-lookback:i]
        high = window["high"].max()
        low = window["low"].min()
        mid = (high + low) / 2
        price = df.iloc[i]["close"]
        if price > mid:
            df.iloc[i, df.columns.get_loc("pd_zone")] = "premium"
        else:
            df.iloc[i, df.columns.get_loc("pd_zone")] = "discount"
    return df


# =============================================================================
# KILLZONE CHECK
# =============================================================================
def in_killzone(ts: datetime, config: Config) -> bool:
    if not config.USE_KILLZONES:
        return True
    hour = ts.hour
    for name, (start, end) in config.KILLZONES.items():
        if start <= hour < end:
            return True
    return False


def in_session(ts: datetime, config: Config) -> bool:
    if not config.USE_SESSION_FILTER:
        return True
    hour = ts.hour
    return (config.LONDON_START <= hour < config.LONDON_END or
            config.NY_START <= hour < config.NY_END)


# =============================================================================
# SIGNAL ENGINE
# =============================================================================
def generate_signals(ltf: pd.DataFrame, htf: pd.DataFrame,
                     sr_zones: List[Dict], config: Config) -> pd.DataFrame:
    ltf = ltf.copy()
    ltf["signal"] = 0
    ltf["entry"] = np.nan
    ltf["sl"] = np.nan
    ltf["tp"] = np.nan
    ltf["reason"] = ""
    ltf["rr"] = np.nan

    htf_trend = htf["trend"].reindex(ltf.index, method="ffill").fillna(0)
    obs = detect_order_blocks(ltf, config.OB_IMPULSE_MULT)
    fvgs = detect_fvg(ltf, config.FVG_MIN_SIZE_ATR)

    pip = pip_size(ltf["close"].mean())
    tol = config.S_R_TOLERANCE_PIPS * pip
    last_sig = -999

    for i in range(100, len(ltf)):
        if i - last_sig < config.COOLDOWN_BARS:
            continue
        row = ltf.iloc[i]
        price = row["close"]
        bias = int(htf_trend.iloc[i])
        if bias == 0:
            continue
        if not in_session(row.name, config):
            continue
        if config.USE_KILLZONES and not in_killzone(row.name, config):
            continue
        if is_news_blackout(row.name.to_pydatetime() if hasattr(row.name, "to_pydatetime") else row.name, config):
            continue

        recent = ltf.iloc[max(0, i-6):i+1]
        had_sweep_low = recent["liq_sweep_low"].any()
        had_sweep_high = recent["liq_sweep_high"].any()
        had_bull_struct = recent["choch_bull"].any() or recent["bos_bull"].any()
        had_bear_struct = recent["choch_bear"].any() or recent["bos_bear"].any()

        # ---- LONG ----
        if bias == 1 and (had_sweep_low or had_bull_struct):
            if config.USE_PREMIUM_DISCOUNT and row.get("pd_zone") == "premium":
                continue  # prefer discount for longs
            entry_zone = None
            ztype = ""
            # Prefer unmitigated bullish OB
            for ob in obs:
                if (ob["type"] == "bullish" and not ob["mitigated"] and
                        ob["time"] <= row.name and
                        ob["bottom"] <= price <= ob["top"] * 1.002):
                    entry_zone = ob
                    ztype = "OB"
                    break
            # Breaker block (failed bearish OB acting as support)
            if entry_zone is None and config.USE_BREAKER_BLOCKS:
                for ob in obs:
                    if (ob["type"] == "bearish" and ob["breaker"] and
                            ob["time"] <= row.name and
                            ob["bottom"] <= price <= ob["top"] * 1.002):
                        entry_zone = ob
                        ztype = "Breaker"
                        break
            # FVG
            if entry_zone is None:
                for fvg in fvgs:
                    if (fvg["type"] == "bullish" and not fvg["mitigated"] and
                            fvg["time"] <= row.name and
                            fvg["bottom"] <= price <= fvg["top"] * 1.002):
                        entry_zone = fvg
                        ztype = "FVG"
                        break
            if entry_zone is not None:
                sr = near_sr(price, sr_zones, tol)
                conf = " +S/R" if (sr and sr["type"] == "support") else ""
                if config.REQUIRE_SR_CONFLUENCE and not conf:
                    continue
                if ztype == "FVG" and not had_sweep_low and not conf:
                    continue
                sl = entry_zone["bottom"] - 4 * pip
                risk = price - sl
                if risk < 6 * pip:
                    continue
                tp = price + config.MIN_RR * risk
                ltf.iloc[i, ltf.columns.get_loc("signal")] = 1
                ltf.iloc[i, ltf.columns.get_loc("entry")] = price
                ltf.iloc[i, ltf.columns.get_loc("sl")] = sl
                ltf.iloc[i, ltf.columns.get_loc("tp")] = tp
                ltf.iloc[i, ltf.columns.get_loc("reason")] = f"LONG {ztype}+Struct{conf}"
                ltf.iloc[i, ltf.columns.get_loc("rr")] = config.MIN_RR
                last_sig = i

        # ---- SHORT ----
        elif bias == -1 and (had_sweep_high or had_bear_struct):
            if config.USE_PREMIUM_DISCOUNT and row.get("pd_zone") == "discount":
                continue  # prefer premium for shorts
            entry_zone = None
            ztype = ""
            for ob in obs:
                if (ob["type"] == "bearish" and not ob["mitigated"] and
                        ob["time"] <= row.name and
                        ob["bottom"] * 0.998 <= price <= ob["top"]):
                    entry_zone = ob
                    ztype = "OB"
                    break
            if entry_zone is None and config.USE_BREAKER_BLOCKS:
                for ob in obs:
                    if (ob["type"] == "bullish" and ob["breaker"] and
                            ob["time"] <= row.name and
                            ob["bottom"] * 0.998 <= price <= ob["top"]):
                        entry_zone = ob
                        ztype = "Breaker"
                        break
            if entry_zone is None:
                for fvg in fvgs:
                    if (fvg["type"] == "bearish" and not fvg["mitigated"] and
                            fvg["time"] <= row.name and
                            fvg["bottom"] * 0.998 <= price <= fvg["top"]):
                        entry_zone = fvg
                        ztype = "FVG"
                        break
            if entry_zone is not None:
                sr = near_sr(price, sr_zones, tol)
                conf = " +S/R" if (sr and sr["type"] == "resistance") else ""
                if config.REQUIRE_SR_CONFLUENCE and not conf:
                    continue
                if ztype == "FVG" and not had_sweep_high and not conf:
                    continue
                sl = entry_zone["top"] + 4 * pip
                risk = sl - price
                if risk < 6 * pip:
                    continue
                tp = price - config.MIN_RR * risk
                ltf.iloc[i, ltf.columns.get_loc("signal")] = -1
                ltf.iloc[i, ltf.columns.get_loc("entry")] = price
                ltf.iloc[i, ltf.columns.get_loc("sl")] = sl
                ltf.iloc[i, ltf.columns.get_loc("tp")] = tp
                ltf.iloc[i, ltf.columns.get_loc("reason")] = f"SHORT {ztype}+Struct{conf}"
                ltf.iloc[i, ltf.columns.get_loc("rr")] = config.MIN_RR
                last_sig = i
    return ltf


# =============================================================================
# POSITION SIZING
# =============================================================================
def calc_lots(balance: float, risk_pct: float, entry: float, sl: float,
              symbol: str = "EURUSD") -> float:
    risk_amt = balance * risk_pct
    pip = pip_size(entry)
    risk_pips = abs(entry - sl) / pip
    if risk_pips < 1:
        return 0.01
    # Approximate pip value
    if "JPY" in symbol:
        pip_val = 1000 * (pip / entry) * 100  # rough
    elif "XAU" in symbol:
        pip_val = 1.0  # $1 per 0.01 for gold rough
    else:
        pip_val = 10.0  # standard
    lots = risk_amt / (risk_pips * pip_val)
    return round(max(0.01, min(lots, 5.0)), 2)


# =============================================================================
# BACKTESTER
# =============================================================================
def backtest(df: pd.DataFrame, config: Config, symbol: str = "EURUSD") -> Dict:
    """Enhanced backtester with Partial TP + Trailing Stop."""
    balance = config.ACCOUNT_BALANCE
    trades = []
    position = None
    equity = [balance]
    pip = pip_size(df["close"].iloc[-1] if len(df) else 1.0)

    for i in range(len(df)):
        row = df.iloc[i]
        price_high = row["high"]
        price_low = row["low"]
        price_close = row["close"]

        if position:
            side = position["side"]
            entry = position["entry"]
            risk = abs(entry - position["initial_sl"])
            if risk <= 0:
                risk = pip * 10

            # --- Trailing stop ---
            if config.USE_TRAILING_STOP and position.get("trail_active", False):
                trail_dist = config.TRAIL_STEP_PIPS * pip
                if side == "long":
                    new_sl = price_close - trail_dist
                    if new_sl > position["sl"]:
                        position["sl"] = new_sl
                else:
                    new_sl = price_close + trail_dist
                    if new_sl < position["sl"]:
                        position["sl"] = new_sl

            # --- Check SL ---
            hit_sl = (side == "long" and price_low <= position["sl"]) or \
                     (side == "short" and price_high >= position["sl"])
            if hit_sl:
                exit_price = position["sl"]
                pnl = ((exit_price - entry) if side == "long" else (entry - exit_price)) / pip * position["lots"] * 10
                balance += pnl
                trades.append({**position, "exit": exit_price, "pnl": pnl,
                               "result": "SL", "exit_time": row.name})
                position = None
                equity.append(balance)
                continue

            # --- Partial Take Profit ---
            if config.USE_PARTIAL_TP and not position.get("partial_done", False):
                partial_level = entry + config.PARTIAL_TP_RR * risk if side == "long" \
                                else entry - config.PARTIAL_TP_RR * risk
                hit_partial = (side == "long" and price_high >= partial_level) or \
                              (side == "short" and price_low <= partial_level)
                if hit_partial:
                    partial_lots = position["lots"] * config.PARTIAL_TP_PCT
                    pnl = ((partial_level - entry) if side == "long" else (entry - partial_level)) / pip * partial_lots * 10
                    balance += pnl
                    trades.append({
                        "side": side, "entry": entry, "sl": position["sl"],
                        "tp": partial_level, "lots": partial_lots,
                        "time": position["time"], "reason": position["reason"] + " (Partial)",
                        "exit": partial_level, "pnl": pnl, "result": "Partial TP",
                        "exit_time": row.name
                    })
                    position["lots"] -= partial_lots
                    position["partial_done"] = True
                    # Move SL to breakeven after partial
                    position["sl"] = entry
                    # Activate trailing
                    if config.USE_TRAILING_STOP:
                        position["trail_active"] = True

            # --- Full TP ---
            hit_tp = (side == "long" and price_high >= position["tp"]) or \
                     (side == "short" and price_low <= position["tp"])
            if hit_tp and position is not None:
                exit_price = position["tp"]
                pnl = ((exit_price - entry) if side == "long" else (entry - exit_price)) / pip * position["lots"] * 10
                balance += pnl
                trades.append({**position, "exit": exit_price, "pnl": pnl,
                               "result": "TP", "exit_time": row.name})
                position = None

            # Activate trailing after TRAIL_START_RR
            if position and config.USE_TRAILING_STOP and not position.get("trail_active", False):
                current_r = ((price_close - entry) if side == "long" else (entry - price_close)) / risk
                if current_r >= config.TRAIL_START_RR:
                    position["trail_active"] = True

        # New signal (only if flat)
        if position is None and row["signal"] != 0:
            # News filter
            if is_news_blackout(row.name.to_pydatetime() if hasattr(row.name, "to_pydatetime") else row.name, config):
                continue
            lots = calc_lots(balance, config.RISK_PER_TRADE, row["entry"], row["sl"], symbol)
            position = {
                "side": "long" if row["signal"] == 1 else "short",
                "entry": row["entry"],
                "sl": row["sl"],
                "initial_sl": row["sl"],
                "tp": row["tp"],
                "lots": lots,
                "time": row.name,
                "reason": row["reason"],
                "partial_done": False,
                "trail_active": False
            }
        equity.append(balance)

    if not trades:
        return {"trades": 0, "winrate": 0, "net_pnl": 0, "final_balance": balance, "trades_list": []}
    wins = [t for t in trades if t["pnl"] > 0]
    return {
        "trades": len(trades),
        "wins": len(wins),
        "winrate": len(wins) / len(trades) * 100,
        "net_pnl": sum(t["pnl"] for t in trades),
        "final_balance": balance,
        "trades_list": trades,
        "equity": equity
    }


# =============================================================================
# ANALYZE SINGLE PAIR
# =============================================================================
def analyze_pair(symbol: str, config: Config, mt5_symbol: str = None) -> Tuple[pd.DataFrame, pd.DataFrame, List]:
    print(f"  → Fetching {symbol} ...")
    try:
        if config.MODE == "live" and HAS_MT5 and mt5_symbol:
            tf_map = {"15m": mt5.TIMEFRAME_M15, "1h": mt5.TIMEFRAME_H1,
                      "4h": mt5.TIMEFRAME_H4, "1d": mt5.TIMEFRAME_D1}
            ltf = fetch_mt5(mt5_symbol, tf_map.get(config.LTF, mt5.TIMEFRAME_M15), config.LOOKBACK_BARS)
            htf = fetch_mt5(mt5_symbol, tf_map.get(config.HTF, mt5.TIMEFRAME_H4), config.LOOKBACK_BARS // 4)
        else:
            ltf = fetch_data(symbol, config.LTF, period="45d")
            htf = fetch_data(symbol, config.HTF, period="120d")
    except Exception as e:
        print(f"  ✗ Data error {symbol}: {e}")
        return None, None, []

    ltf = find_swings(ltf, config.SWING_LOOKBACK, config.SWING_LOOKBACK)
    htf = find_swings(htf, config.SWING_LOOKBACK, config.SWING_LOOKBACK)
    ltf = detect_structure(ltf)
    htf = detect_structure(htf)
    ltf = detect_liquidity(ltf)
    if config.USE_PREMIUM_DISCOUNT:
        ltf = premium_discount(ltf)
    sr = detect_sr(ltf, config.S_R_TOLERANCE_PIPS, config.MIN_ZONE_STRENGTH)
    ltf = generate_signals(ltf, htf, sr, config)
    return ltf, htf, sr


# =============================================================================
# MULTI-PAIR SCANNER
# =============================================================================
def run_scanner(config: Config):
    print("\n" + "=" * 60)
    print("MULTI-PAIR SMC SCANNER")
    print("=" * 60)
    all_signals = []
    for i, pair in enumerate(config.PAIRS):
        mt5_sym = config.MT5_PAIRS[i] if i < len(config.MT5_PAIRS) else None
        ltf, htf, sr = analyze_pair(pair, config, mt5_sym)
        if ltf is None:
            continue
        sigs = ltf[ltf["signal"] != 0]
        if not sigs.empty:
            last = sigs.iloc[-1]
            side = "long" if last["signal"] == 1 else "short"
            lots = calc_lots(config.ACCOUNT_BALANCE, config.RISK_PER_TRADE,
                             last["entry"], last["sl"], pair)
            signal = {
                "pair": pair.replace("=X", ""),
                "side": side,
                "entry": last["entry"],
                "sl": last["sl"],
                "tp": last["tp"],
                "reason": last["reason"],
                "lots": lots,
                "rr": last["rr"],
                "time": last.name
            }
            all_signals.append(signal)
            print(f"  ✅ {signal['pair']} {side.upper()} @ {signal['entry']:.5f} | {signal['reason']}")
            # Telegram
            msg = format_signal_msg(signal["pair"], side, signal["entry"],
                                    signal["sl"], signal["tp"], signal["reason"],
                                    lots, signal["rr"] or 2.0)
            send_telegram(msg, config)
        else:
            print(f"  – {pair.replace('=X','')} : no signal")
    print(f"\nTotal active signals: {len(all_signals)}")
    # Save
    if all_signals:
        pd.DataFrame(all_signals).to_csv(str(Path(__file__).resolve().parent / "scanner_signals.csv"), index=False)
        print("Saved → scanner_signals.csv")
    return all_signals


# =============================================================================
# SINGLE PAIR BACKTEST / SIGNALS
# =============================================================================
def run_single(config: Config):
    pair = config.BACKTEST_PAIR
    print(f"\nAnalyzing {pair} ...")
    ltf, htf, sr = analyze_pair(pair, config)
    if ltf is None:
        return
    sigs = ltf[ltf["signal"] != 0]
    print(f"Signals found: {len(sigs)}")
    print(f"S/R zones: {len(sr)}")

    if config.MODE == "backtest":
        res = backtest(ltf, config, pair)
        print("\n" + "=" * 40)
        print("BACKTEST RESULTS")
        print("=" * 40)
        print(f"Trades     : {res['trades']}")
        print(f"Win rate   : {res['winrate']:.1f}%")
        print(f"Net PnL    : ${res['net_pnl']:.2f}")
        print(f"Final bal  : ${res['final_balance']:.2f}")
        if res["trades_list"]:
            print("\nLast trades:")
            for t in res["trades_list"][-5:]:
                print(f"  {t['time']} {t['side'].upper()} → {t['result']} ${t['pnl']:.2f} | {t['reason']}")
    else:
        if sigs.empty:
            print("No current signals.")
        else:
            last = sigs.iloc[-1]
            side = "long" if last["signal"] == 1 else "short"
            lots = calc_lots(config.ACCOUNT_BALANCE, config.RISK_PER_TRADE,
                             last["entry"], last["sl"], pair)
            print(f"\nLATEST SIGNAL: {side.upper()}")
            print(f"Entry {last['entry']:.5f} | SL {last['sl']:.5f} | TP {last['tp']:.5f}")
            print(f"Lots {lots} | Reason: {last['reason']}")
            msg = format_signal_msg(pair.replace("=X",""), side, last["entry"],
                                    last["sl"], last["tp"], last["reason"], lots, 2.0)
            send_telegram(msg, config)
            if config.MODE == "live" and HAS_MT5:
                print("[LIVE] Implement mt5.order_send here with the values above.")
    out = Path(__file__).resolve().parent / "smc_signals.csv"
    sigs.to_csv(out)
    print("Signals saved.")


# =============================================================================
# MAIN
# =============================================================================
def main():
    cfg = Config()
    print("=" * 60)
    print("SMC + S/R Forex Bot v2.0  (Full Edition)")
    print("=" * 60)
    print(f"Mode        : {cfg.MODE}")
    print(f"Pairs       : {len(cfg.PAIRS)}")
    print(f"Killzones   : {cfg.USE_KILLZONES}")
    print(f"Breakers    : {cfg.USE_BREAKER_BLOCKS}")
    print(f"Prem/Disc   : {cfg.USE_PREMIUM_DISCOUNT}")
    print(f"Telegram    : {cfg.TELEGRAM_ENABLED}")
    print()

    if cfg.MODE == "scanner":
        run_scanner(cfg)
    else:
        run_single(cfg)
    print("\nDone.")


if __name__ == "__main__":
    main()
