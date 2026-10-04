#!/usr/bin/env python3
"""
SMC + Support/Resistance Forex Bot  —  Windows / Python 3.10–3.14
No yfinance. Fetches Yahoo Finance chart API directly.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Auto-install
# ---------------------------------------------------------------------------
def _ensure_pkgs() -> None:
    missing = []
    for pkg in ("pandas", "numpy"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("Installing:", ", ".join(missing))
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", *missing],
            stdout=sys.stdout,
        )

_ensure_pkgs()

import numpy as np
import pandas as pd
import urllib.request

HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
class C:
    PAIRS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "GC=F"]
    LTF = "15m"
    HTF = "1h"
    RISK = 0.01
    MIN_RR = 2.0
    BALANCE = 10_000.0
    SWING = 5
    OB_MULT = 1.8
    FVG_ATR = 0.35
    LIQ_WICK = 0.30
    SR_PIPS = 8
    COOLDOWN = 16
    USE_KZ = True
    USE_PD = True
    USE_BREAKER = True
    USE_SESSION = True
    USE_NEWS = True
    USE_PARTIAL = True
    PARTIAL_RR = 1.0
    PARTIAL_PCT = 0.50
    USE_TRAIL = True
    TRAIL_RR = 1.5
    TRAIL_PIPS = 10
    MODE = "backtest"  # backtest | scanner | loop
    PAIR = "EURUSD=X"
    LOOP_MIN = 5
    TG_TOKEN = ""
    TG_CHAT = ""
    TG_ON = False


NEWS = [(2, 12, 15), (4, 12, 15), (2, 8, 10), (1, 12, 14)]  # weekday, h0, h1 UTC


# ---------------------------------------------------------------------------
# Yahoo chart API (works without yfinance)
# ---------------------------------------------------------------------------
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_INTERVAL_RANGE = {
    "15m": "60d",
    "1h": "730d",
    "1d": "5y",
    "5m": "60d",
    "30m": "60d",
    "60m": "730d",
}


def fetch(symbol: str, interval: str) -> pd.DataFrame:
    rng = _INTERVAL_RANGE.get(interval, "60d")
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?interval={interval}&range={rng}&includePrePost=false"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    last_err = None
    raw = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    if raw is None:
        raise RuntimeError(f"Yahoo fetch failed for {symbol} {interval}: {last_err}")

    err = (raw.get("chart") or {}).get("error")
    if err:
        raise RuntimeError(f"Yahoo error {symbol}: {err}")
    results = (raw.get("chart") or {}).get("result") or []
    if not results:
        raise RuntimeError(f"No Yahoo data for {symbol} {interval}")

    res = results[0]
    ts = res.get("timestamp") or []
    quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    if not ts:
        raise RuntimeError(f"Empty timestamps for {symbol}")

    df = pd.DataFrame(
        {
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("close"),
            "volume": quote.get("volume"),
        },
        index=pd.to_datetime(ts, unit="s"),
    )
    df = df.dropna(subset=["open", "high", "low", "close"])
    if df.empty:
        raise RuntimeError(f"All NaN bars for {symbol}")
    # resample 1h -> 4h if needed
    return df


def fetch_htf(symbol: str) -> pd.DataFrame:
    h = fetch(symbol, "1h")
    ohlc = h.resample("4h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    return ohlc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def pip_size(price: float) -> float:
    if price > 100:
        return 0.1 if price >= 500 else 0.01
    if price > 20:
        return 0.01
    return 0.0001


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def swings(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    df = df.copy()
    df["swing_high"] = False
    df["swing_low"] = False
    h, l = df["high"].values, df["low"].values
    for i in range(n, len(df) - n):
        if h[i] == max(h[i - n : i + n + 1]):
            df.iloc[i, df.columns.get_loc("swing_high")] = True
        if l[i] == min(l[i - n : i + n + 1]):
            df.iloc[i, df.columns.get_loc("swing_low")] = True
    return df


def structure(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ("bos_bull", "bos_bear", "choch_bull", "choch_bear"):
        df[col] = False
    df["trend"] = 0
    last_sh = last_sl = None
    trend = 0
    for i in range(len(df)):
        row = df.iloc[i]
        if row["swing_high"]:
            if last_sh is not None and row["high"] > last_sh:
                if trend >= 0:
                    df.iloc[i, df.columns.get_loc("bos_bull")] = True
                else:
                    df.iloc[i, df.columns.get_loc("choch_bull")] = True
                trend = 1
            last_sh = row["high"]
        if row["swing_low"]:
            if last_sl is not None and row["low"] < last_sl:
                if trend <= 0:
                    df.iloc[i, df.columns.get_loc("bos_bear")] = True
                else:
                    df.iloc[i, df.columns.get_loc("choch_bear")] = True
                trend = -1
            last_sl = row["low"]
        df.iloc[i, df.columns.get_loc("trend")] = trend
    return df


def detect_sr(df: pd.DataFrame) -> list:
    pip = pip_size(float(df["close"].mean()))
    tol = C.SR_PIPS * pip
    pts = []
    for idx, row in df.iterrows():
        if row.get("swing_high"):
            pts.append(("resistance", row["high"], idx))
        if row.get("swing_low"):
            pts.append(("support", row["low"], idx))
    zones, used = [], set()
    for i, (typ, price, t) in enumerate(pts):
        if i in used:
            continue
        cluster, times = [price], [t]
        for j, (_, p2, t2) in enumerate(pts):
            if j <= i or j in used:
                continue
            if abs(price - p2) <= tol:
                cluster.append(p2)
                times.append(t2)
                used.add(j)
        if len(cluster) >= 2:
            zones.append({"level": float(np.mean(cluster)), "type": typ, "strength": len(cluster)})
        used.add(i)
    return sorted(zones, key=lambda z: z["strength"], reverse=True)[:12]


def near_sr(price, zones, tol):
    for z in zones:
        if abs(price - z["level"]) <= tol:
            return z
    return None


def order_blocks(df: pd.DataFrame) -> list:
    df = df.copy()
    df["atr"] = atr(df)
    obs = []
    for i in range(2, len(df) - 1):
        c, n = df.iloc[i], df.iloc[i + 1]
        a = c["atr"]
        if pd.isna(a) or a == 0:
            continue
        if c["close"] < c["open"]:
            impulse = n["close"] - n["open"]
            if impulse > C.OB_MULT * a and n["close"] > c["high"]:
                obs.append(
                    {
                        "type": "bullish",
                        "top": c["high"],
                        "bottom": c["low"],
                        "mid": (c["high"] + c["low"]) / 2,
                        "time": df.index[i],
                        "mitigated": False,
                        "breaker": False,
                    }
                )
        if c["close"] > c["open"]:
            impulse = n["open"] - n["close"]
            if impulse > C.OB_MULT * a and n["close"] < c["low"]:
                obs.append(
                    {
                        "type": "bearish",
                        "top": c["high"],
                        "bottom": c["low"],
                        "mid": (c["high"] + c["low"]) / 2,
                        "time": df.index[i],
                        "mitigated": False,
                        "breaker": False,
                    }
                )
    for ob in obs:
        after = df.loc[ob["time"] :]
        if len(after) < 3:
            continue
        if ob["type"] == "bullish" and (after["close"] < ob["bottom"]).any():
            ob["mitigated"] = True
            mid = after[after["close"] < ob["bottom"]].index[0]
            later = df.loc[mid:]
            if (later["high"] > ob["top"]).any() and (later["close"] < ob["mid"]).any():
                ob["breaker"] = True
        if ob["type"] == "bearish" and (after["close"] > ob["top"]).any():
            ob["mitigated"] = True
            mid = after[after["close"] > ob["top"]].index[0]
            later = df.loc[mid:]
            if (later["low"] < ob["bottom"]).any() and (later["close"] > ob["mid"]).any():
                ob["breaker"] = True
    return obs


def fvgs(df: pd.DataFrame) -> list:
    df = df.copy()
    df["atr"] = atr(df)
    out = []
    for i in range(2, len(df)):
        c0, c1, c2 = df.iloc[i - 2], df.iloc[i - 1], df.iloc[i]
        a = c1["atr"]
        if pd.isna(a) or a == 0:
            continue
        if c2["low"] > c0["high"]:
            gap = c2["low"] - c0["high"]
            if gap >= C.FVG_ATR * a:
                out.append(
                    {
                        "type": "bullish",
                        "top": c2["low"],
                        "bottom": c0["high"],
                        "time": df.index[i],
                        "mitigated": False,
                    }
                )
        if c2["high"] < c0["low"]:
            gap = c0["low"] - c2["high"]
            if gap >= C.FVG_ATR * a:
                out.append(
                    {
                        "type": "bearish",
                        "top": c0["low"],
                        "bottom": c2["high"],
                        "time": df.index[i],
                        "mitigated": False,
                    }
                )
    for f in out:
        after = df.loc[f["time"] :]
        if f["type"] == "bullish" and (after["low"] <= f["bottom"]).any():
            f["mitigated"] = True
        if f["type"] == "bearish" and (after["high"] >= f["top"]).any():
            f["mitigated"] = True
    return [f for f in out if not f["mitigated"]]


def liquidity(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    df = df.copy()
    df["liq_sweep_high"] = False
    df["liq_sweep_low"] = False
    for i in range(lookback, len(df)):
        w = df.iloc[i - lookback : i]
        rh, rl = w["high"].max(), w["low"].min()
        cur = df.iloc[i]
        rng = cur["high"] - cur["low"]
        if rng == 0:
            continue
        if cur["high"] > rh and cur["close"] < rh:
            wick = cur["high"] - max(cur["open"], cur["close"])
            if wick / rng > C.LIQ_WICK:
                df.iloc[i, df.columns.get_loc("liq_sweep_high")] = True
        if cur["low"] < rl and cur["close"] > rl:
            wick = min(cur["open"], cur["close"]) - cur["low"]
            if wick / rng > C.LIQ_WICK:
                df.iloc[i, df.columns.get_loc("liq_sweep_low")] = True
    return df


def premium_discount(df: pd.DataFrame, n: int = 50) -> pd.DataFrame:
    df = df.copy()
    df["pd_zone"] = "eq"
    for i in range(n, len(df)):
        w = df.iloc[i - n : i]
        mid = (w["high"].max() + w["low"].min()) / 2
        df.iloc[i, df.columns.get_loc("pd_zone")] = (
            "premium" if df.iloc[i]["close"] > mid else "discount"
        )
    return df


def in_kz(ts) -> bool:
    if not C.USE_KZ:
        return True
    h = ts.hour
    return (7 <= h < 10) or (12 <= h < 15) or (15 <= h < 17)


def in_session(ts) -> bool:
    if not C.USE_SESSION:
        return True
    h = ts.hour
    return (7 <= h < 16) or (12 <= h < 21)


def news_block(ts) -> bool:
    if not C.USE_NEWS:
        return False
    wd, h = ts.weekday(), ts.hour
    return any(wd == w and a <= h < b for w, a, b in NEWS)


def generate(ltf, htf, sr_zones):
    ltf = ltf.copy()
    ltf["signal"] = 0
    ltf["entry"] = np.nan
    ltf["sl"] = np.nan
    ltf["tp"] = np.nan
    ltf["reason"] = ""
    htf_tr = htf["trend"].reindex(ltf.index, method="ffill").fillna(0)
    obs = order_blocks(ltf)
    gaps = fvgs(ltf)
    pip = pip_size(float(ltf["close"].mean()))
    tol = C.SR_PIPS * pip
    last = -999
    for i in range(100, len(ltf)):
        if i - last < C.COOLDOWN:
            continue
        row = ltf.iloc[i]
        price = float(row["close"])
        bias = int(htf_tr.iloc[i])
        if bias == 0:
            continue
        ts = row.name.to_pydatetime() if hasattr(row.name, "to_pydatetime") else row.name
        if not in_session(ts) or not in_kz(ts) or news_block(ts):
            continue
        recent = ltf.iloc[max(0, i - 6) : i + 1]
        sw_lo = bool(recent["liq_sweep_low"].any())
        sw_hi = bool(recent["liq_sweep_high"].any())
        bull = bool(recent["choch_bull"].any() or recent["bos_bull"].any())
        bear = bool(recent["choch_bear"].any() or recent["bos_bear"].any())

        zone, ztype = None, ""
        if bias == 1 and (sw_lo or bull):
            if C.USE_PD and row.get("pd_zone") == "premium":
                continue
            for ob in obs:
                if (
                    ob["type"] == "bullish"
                    and not ob["mitigated"]
                    and ob["time"] <= row.name
                    and ob["bottom"] <= price <= ob["top"] * 1.002
                ):
                    zone, ztype = ob, "OB"
                    break
            if zone is None and C.USE_BREAKER:
                for ob in obs:
                    if (
                        ob["type"] == "bearish"
                        and ob["breaker"]
                        and ob["time"] <= row.name
                        and ob["bottom"] <= price <= ob["top"] * 1.002
                    ):
                        zone, ztype = ob, "Breaker"
                        break
            if zone is None:
                for f in gaps:
                    if (
                        f["type"] == "bullish"
                        and f["time"] <= row.name
                        and f["bottom"] <= price <= f["top"] * 1.002
                    ):
                        zone, ztype = f, "FVG"
                        break
            if zone is None:
                continue
            sr = near_sr(price, sr_zones, tol)
            conf = " +S/R" if (sr and sr["type"] == "support") else ""
            if ztype == "FVG" and not sw_lo and not conf:
                continue
            sl = zone["bottom"] - 4 * pip
            risk = price - sl
            if risk < 6 * pip:
                continue
            ltf.iloc[i, ltf.columns.get_loc("signal")] = 1
            ltf.iloc[i, ltf.columns.get_loc("entry")] = price
            ltf.iloc[i, ltf.columns.get_loc("sl")] = sl
            ltf.iloc[i, ltf.columns.get_loc("tp")] = price + C.MIN_RR * risk
            ltf.iloc[i, ltf.columns.get_loc("reason")] = f"LONG {ztype}+Struct{conf}"
            last = i

        elif bias == -1 and (sw_hi or bear):
            if C.USE_PD and row.get("pd_zone") == "discount":
                continue
            for ob in obs:
                if (
                    ob["type"] == "bearish"
                    and not ob["mitigated"]
                    and ob["time"] <= row.name
                    and ob["bottom"] * 0.998 <= price <= ob["top"]
                ):
                    zone, ztype = ob, "OB"
                    break
            if zone is None and C.USE_BREAKER:
                for ob in obs:
                    if (
                        ob["type"] == "bullish"
                        and ob["breaker"]
                        and ob["time"] <= row.name
                        and ob["bottom"] * 0.998 <= price <= ob["top"]
                    ):
                        zone, ztype = ob, "Breaker"
                        break
            if zone is None:
                for f in gaps:
                    if (
                        f["type"] == "bearish"
                        and f["time"] <= row.name
                        and f["bottom"] * 0.998 <= price <= f["top"]
                    ):
                        zone, ztype = f, "FVG"
                        break
            if zone is None:
                continue
            sr = near_sr(price, sr_zones, tol)
            conf = " +S/R" if (sr and sr["type"] == "resistance") else ""
            if ztype == "FVG" and not sw_hi and not conf:
                continue
            sl = zone["top"] + 4 * pip
            risk = sl - price
            if risk < 6 * pip:
                continue
            ltf.iloc[i, ltf.columns.get_loc("signal")] = -1
            ltf.iloc[i, ltf.columns.get_loc("entry")] = price
            ltf.iloc[i, ltf.columns.get_loc("sl")] = sl
            ltf.iloc[i, ltf.columns.get_loc("tp")] = price - C.MIN_RR * risk
            ltf.iloc[i, ltf.columns.get_loc("reason")] = f"SHORT {ztype}+Struct{conf}"
            last = i
    return ltf


def lots(balance, entry, sl, symbol="EURUSD"):
    pip = pip_size(entry)
    rp = abs(entry - sl) / pip
    if rp < 1:
        return 0.01
    pv = 1.0 if "XAU" in symbol or "GC" in symbol else (9.0 if "JPY" in symbol else 10.0)
    return round(max(0.01, min(balance * C.RISK / (rp * pv), 5.0)), 2)


def backtest(df, symbol="EURUSD"):
    bal = C.BALANCE
    trades, pos, eq = [], None, [bal]
    pip = pip_size(float(df["close"].iloc[-1]))
    for i in range(len(df)):
        row = df.iloc[i]
        hi, lo, cl = row["high"], row["low"], row["close"]
        if pos:
            side, entry = pos["side"], pos["entry"]
            risk = abs(entry - pos["isl"]) or pip * 10
            if C.USE_TRAIL and pos.get("trail"):
                d = C.TRAIL_PIPS * pip
                if side == "long":
                    pos["sl"] = max(pos["sl"], cl - d)
                else:
                    pos["sl"] = min(pos["sl"], cl + d)
            hit_sl = (side == "long" and lo <= pos["sl"]) or (side == "short" and hi >= pos["sl"])
            if hit_sl:
                px = pos["sl"]
                pnl = ((px - entry) if side == "long" else (entry - px)) / pip * pos["lots"] * 10
                bal += pnl
                trades.append({**pos, "exit": px, "pnl": pnl, "result": "SL", "exit_time": row.name})
                pos = None
                eq.append(bal)
                continue
            if C.USE_PARTIAL and not pos.get("part"):
                pl = entry + C.PARTIAL_RR * risk if side == "long" else entry - C.PARTIAL_RR * risk
                hit = (side == "long" and hi >= pl) or (side == "short" and lo <= pl)
                if hit:
                    plts = pos["lots"] * C.PARTIAL_PCT
                    pnl = ((pl - entry) if side == "long" else (entry - pl)) / pip * plts * 10
                    bal += pnl
                    trades.append(
                        {
                            **{k: pos[k] for k in ("side", "entry", "time", "reason")},
                            "lots": plts,
                            "exit": pl,
                            "pnl": pnl,
                            "result": "Partial TP",
                            "exit_time": row.name,
                        }
                    )
                    pos["lots"] -= plts
                    pos["part"] = True
                    pos["sl"] = entry
                    if C.USE_TRAIL:
                        pos["trail"] = True
            hit_tp = pos and (
                (side == "long" and hi >= pos["tp"]) or (side == "short" and lo <= pos["tp"])
            )
            if hit_tp:
                px = pos["tp"]
                pnl = ((px - entry) if side == "long" else (entry - px)) / pip * pos["lots"] * 10
                bal += pnl
                trades.append({**pos, "exit": px, "pnl": pnl, "result": "TP", "exit_time": row.name})
                pos = None
            elif pos and C.USE_TRAIL and not pos.get("trail"):
                rnow = ((cl - entry) if side == "long" else (entry - cl)) / risk
                if rnow >= C.TRAIL_RR:
                    pos["trail"] = True
        if pos is None and row["signal"] != 0:
            ts = row.name.to_pydatetime() if hasattr(row.name, "to_pydatetime") else row.name
            if news_block(ts):
                continue
            pos = {
                "side": "long" if row["signal"] == 1 else "short",
                "entry": row["entry"],
                "sl": row["sl"],
                "isl": row["sl"],
                "tp": row["tp"],
                "lots": lots(bal, row["entry"], row["sl"], symbol),
                "time": row.name,
                "reason": row["reason"],
                "part": False,
                "trail": False,
            }
        eq.append(bal)
    if not trades:
        return {"trades": 0, "winrate": 0, "net": 0, "bal": bal, "list": []}
    wins = [t for t in trades if t["pnl"] > 0]
    return {
        "trades": len(trades),
        "wins": len(wins),
        "winrate": 100 * len(wins) / len(trades),
        "net": sum(t["pnl"] for t in trades),
        "bal": bal,
        "list": trades,
        "eq": eq,
    }


def analyze(symbol: str):
    print(f"  Fetching {symbol} 15m + 4h ...")
    ltf = fetch(symbol, "15m")
    htf = fetch_htf(symbol)
    print(f"  Bars: LTF={len(ltf)}  HTF={len(htf)}")
    ltf = swings(ltf, C.SWING)
    htf = swings(htf, C.SWING)
    ltf = structure(ltf)
    htf = structure(htf)
    ltf = liquidity(ltf)
    if C.USE_PD:
        ltf = premium_discount(ltf)
    sr = detect_sr(ltf)
    ltf = generate(ltf, htf, sr)
    return ltf, htf, sr


def telegram(text: str):
    if not C.TG_ON or not C.TG_TOKEN or not C.TG_CHAT:
        return
    try:
        body = json.dumps({"chat_id": C.TG_CHAT, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{C.TG_TOKEN}/sendMessage",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print("Telegram error:", e)


def run_backtest(symbol=None):
    symbol = symbol or C.PAIR
    print("\n" + "=" * 56)
    print(" SMC Forex Bot  |  BACKTEST  | ", symbol)
    print("=" * 56)
    ltf, htf, sr = analyze(symbol)
    sigs = ltf[ltf["signal"] != 0]
    print(f" Signals: {len(sigs)}   S/R zones: {len(sr)}")
    res = backtest(ltf, symbol)
    print("-" * 40)
    print(f" Trades     : {res['trades']}")
    print(f" Win rate   : {res['winrate']:.1f}%")
    print(f" Net PnL    : ${res['net']:.2f}")
    print(f" Final bal  : ${res['bal']:.2f}")
    if res["list"]:
        print("\n Last trades:")
        for t in res["list"][-8:]:
            print(
                f"  {t['time']} {t['side'].upper():5} -> {t['result']:11} "
                f"${t['pnl']:+.2f}  {t.get('reason','')}"
            )
    out = HERE / "smc_signals.csv"
    sigs.to_csv(out)
    print(f"\n Saved {out}")
    print("Done.")
    return res


def run_scanner():
    print("\n" + "=" * 56)
    print(" SMC Forex Bot  |  MULTI-PAIR SCANNER")
    print("=" * 56)
    found = []
    for p in C.PAIRS:
        try:
            ltf, htf, sr = analyze(p)
        except Exception as e:
            print(f"  FAIL {p}: {e}")
            continue
        sigs = ltf[ltf["signal"] != 0]
        name = p.replace("=X", "").replace("GC=F", "XAUUSD")
        if sigs.empty:
            print(f"  - {name}: no signal")
            continue
        last = sigs.iloc[-1]
        side = "LONG" if last["signal"] == 1 else "SHORT"
        lt = lots(C.BALANCE, last["entry"], last["sl"], p)
        rec = {
            "pair": name,
            "side": side,
            "entry": float(last["entry"]),
            "sl": float(last["sl"]),
            "tp": float(last["tp"]),
            "lots": lt,
            "reason": last["reason"],
            "time": str(last.name),
        }
        found.append(rec)
        print(f"  {name} {side} @ {rec['entry']:.5f}  SL {rec['sl']:.5f}  TP {rec['tp']:.5f}  | {rec['reason']}")
        telegram(
            f"<b>{name} {side}</b>\nEntry {rec['entry']:.5f}\nSL {rec['sl']:.5f}\n"
            f"TP {rec['tp']:.5f}\n{rec['reason']}"
        )
    print(f"\n Active signals: {len(found)}")
    if found:
        pd.DataFrame(found).to_csv(HERE / "scanner_signals.csv", index=False)
        print(" Saved scanner_signals.csv")
    print("Done.")
    return found


def run_loop():
    print(f"Loop every {C.LOOP_MIN} minutes. Ctrl+C to stop.")
    while True:
        try:
            run_scanner()
        except KeyboardInterrupt:
            print("Stopped.")
            return
        except Exception:
            traceback.print_exc()
        print(f"Sleeping {C.LOOP_MIN} min ...")
        time.sleep(C.LOOP_MIN * 60)


def main():
    args = [a.lower() for a in sys.argv[1:]]
    print("=" * 56)
    print(" SMC + Support/Resistance Forex Bot")
    print(" Python", sys.version.split()[0], "|", datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 56)
    if "scanner" in args:
        run_scanner()
    elif "loop" in args:
        run_loop()
    else:
        run_backtest()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception:
        traceback.print_exc()
        print("\n*** BOT CRASHED — copy the text above and send it ***")
        try:
            input("Press Enter to close...")
        except Exception:
            time.sleep(8)
        sys.exit(1)
