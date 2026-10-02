#!/usr/bin/env python3
"""
SMC Forex Bot – Streamlit Dashboard
Run with:  streamlit run smc_dashboard.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from smc_forex_bot_v2 import (
    Config, analyze_pair, run_scanner, backtest,
    calc_lots, send_telegram, format_signal_msg
)

st.set_page_config(
    page_title="SMC Forex Bot Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {font-size: 2.2rem; font-weight: 700; color: #00d4aa;}
    .metric-card {background: #1e1e2f; padding: 1rem; border-radius: 10px;}
    .signal-long {color: #00c853; font-weight: bold;}
    .signal-short {color: #ff1744; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-header">📈 SMC + Support/Resistance Forex Bot</p>', unsafe_allow_html=True)
st.caption("Smart Money Concepts • Order Blocks • FVG • Liquidity • Breakers • Killzones")

# Sidebar
st.sidebar.header("⚙️ Configuration")
mode = st.sidebar.selectbox("Mode", ["Scanner", "Single Pair Backtest", "Signals"])
pair = st.sidebar.selectbox("Pair (for single)", [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "GC=F"
])
risk = st.sidebar.slider("Risk % per trade", 0.5, 3.0, 1.0, 0.1) / 100
min_rr = st.sidebar.slider("Min R:R", 1.5, 4.0, 2.0, 0.5)
use_kz = st.sidebar.checkbox("Killzones", True)
use_pd = st.sidebar.checkbox("Premium/Discount", True)
use_breaker = st.sidebar.checkbox("Breaker Blocks", True)
use_news = st.sidebar.checkbox("News Filter", True)
use_partial = st.sidebar.checkbox("Partial TP", True)
use_trail = st.sidebar.checkbox("Trailing Stop", True)
use_session = st.sidebar.checkbox("Session Filter", True)

cfg = Config()
cfg.RISK_PER_TRADE = risk
cfg.MIN_RR = min_rr
cfg.USE_KILLZONES = use_kz
cfg.USE_PREMIUM_DISCOUNT = use_pd
cfg.USE_BREAKER_BLOCKS = use_breaker
cfg.USE_NEWS_FILTER = use_news
cfg.USE_PARTIAL_TP = use_partial
cfg.USE_TRAILING_STOP = use_trail
cfg.USE_SESSION_FILTER = use_session
cfg.BACKTEST_PAIR = pair

if st.sidebar.button("🔄 Run Analysis", type="primary"):
    with st.spinner("Analyzing markets..."):
        if mode == "Scanner":
            cfg.MODE = "scanner"
            # Run scanner logic inline for dashboard
            all_signals = []
            progress = st.progress(0)
            for idx, p in enumerate(cfg.PAIRS):
                progress.progress((idx + 1) / len(cfg.PAIRS))
                ltf, htf, sr = analyze_pair(p, cfg)
                if ltf is None:
                    continue
                sigs = ltf[ltf["signal"] != 0]
                if not sigs.empty:
                    last = sigs.iloc[-1]
                    side = "long" if last["signal"] == 1 else "short"
                    lots = calc_lots(cfg.ACCOUNT_BALANCE, cfg.RISK_PER_TRADE,
                                     last["entry"], last["sl"], p)
                    all_signals.append({
                        "Pair": p.replace("=X", "").replace("GC=F", "XAUUSD"),
                        "Side": side.upper(),
                        "Entry": round(last["entry"], 5),
                        "SL": round(last["sl"], 5),
                        "TP": round(last["tp"], 5),
                        "Lots": lots,
                        "Reason": last["reason"],
                        "Time": str(last.name)
                    })
            progress.empty()
            st.session_state["scanner_results"] = all_signals
            st.session_state["mode"] = "scanner"

        else:
            cfg.MODE = "backtest" if mode == "Single Pair Backtest" else "signals"
            ltf, htf, sr = analyze_pair(pair, cfg)
            if ltf is not None:
                st.session_state["ltf"] = ltf
                st.session_state["htf"] = htf
                st.session_state["sr"] = sr
                st.session_state["pair"] = pair
                if mode == "Single Pair Backtest":
                    res = backtest(ltf, cfg, pair)
                    st.session_state["bt_results"] = res
                st.session_state["mode"] = mode

# ---- Display Results ----
if "mode" in st.session_state:
    if st.session_state["mode"] == "scanner":
        signals = st.session_state.get("scanner_results", [])
        st.subheader(f"🔍 Multi-Pair Scanner – {len(signals)} active signals")
        if signals:
            df_sig = pd.DataFrame(signals)
            def color_side(val):
                color = "#00c853" if val == "LONG" else "#ff1744"
                return f"color: {color}; font-weight: bold"
            st.dataframe(df_sig.style.map(color_side, subset=["Side"]), use_container_width=True)
        else:
            st.info("No active signals across all pairs right now.")

    elif st.session_state["mode"] == "Single Pair Backtest":
        res = st.session_state.get("bt_results", {})
        pair_name = st.session_state.get("pair", "").replace("=X", "")
        st.subheader(f"📊 Backtest Results – {pair_name}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Trades", res.get("trades", 0))
        c2.metric("Win Rate", f"{res.get('winrate', 0):.1f}%")
        c3.metric("Net PnL", f"${res.get('net_pnl', 0):.2f}")
        c4.metric("Final Balance", f"${res.get('final_balance', 0):.2f}")

        # Equity curve
        if res.get("equity"):
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                y=res["equity"], mode="lines", name="Equity",
                line=dict(color="#00d4aa", width=2)
            ))
            fig.update_layout(
                title="Equity Curve",
                template="plotly_dark",
                height=350,
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig, use_container_width=True)

        # Trade list
        if res.get("trades_list"):
            st.subheader("Trade Log")
            tdf = pd.DataFrame(res["trades_list"])
            cols = [c for c in ["time", "side", "entry", "sl", "tp", "lots", "result", "pnl", "reason"] if c in tdf.columns]
            st.dataframe(tdf[cols], use_container_width=True)

        # Price chart with signals
        ltf = st.session_state.get("ltf")
        if ltf is not None:
            st.subheader("Price Chart + Signals")
            plot_df = ltf.tail(300).copy()
            fig = go.Figure(data=[go.Candlestick(
                x=plot_df.index,
                open=plot_df["open"], high=plot_df["high"],
                low=plot_df["low"], close=plot_df["close"],
                name="Price"
            )])
            # Mark signals
            longs = plot_df[plot_df["signal"] == 1]
            shorts = plot_df[plot_df["signal"] == -1]
            if not longs.empty:
                fig.add_trace(go.Scatter(
                    x=longs.index, y=longs["entry"], mode="markers",
                    marker=dict(symbol="triangle-up", size=12, color="#00c853"),
                    name="Long"
                ))
            if not shorts.empty:
                fig.add_trace(go.Scatter(
                    x=shorts.index, y=shorts["entry"], mode="markers",
                    marker=dict(symbol="triangle-down", size=12, color="#ff1744"),
                    name="Short"
                ))
            # S/R lines
            for z in st.session_state.get("sr", [])[:6]:
                fig.add_hline(y=z["level"], line_dash="dot",
                              line_color="#ffab00" if z["type"] == "resistance" else "#40c4ff",
                              opacity=0.5)
            fig.update_layout(template="plotly_dark", height=500,
                              xaxis_rangeslider_visible=False,
                              margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig, use_container_width=True)

    else:  # Signals
        ltf = st.session_state.get("ltf")
        pair_name = st.session_state.get("pair", "").replace("=X", "")
        st.subheader(f"📡 Latest Signals – {pair_name}")
        if ltf is not None:
            sigs = ltf[ltf["signal"] != 0]
            if sigs.empty:
                st.info("No signals found in recent data.")
            else:
                last = sigs.iloc[-1]
                side = "LONG 🟢" if last["signal"] == 1 else "SHORT 🔴"
                st.markdown(f"### {side}")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Entry", f"{last['entry']:.5f}")
                c2.metric("Stop Loss", f"{last['sl']:.5f}")
                c3.metric("Take Profit", f"{last['tp']:.5f}")
                lots = calc_lots(cfg.ACCOUNT_BALANCE, cfg.RISK_PER_TRADE,
                                 last["entry"], last["sl"], pair_name)
                c4.metric("Lots", lots)
                st.write(f"**Reason:** {last['reason']}")
                st.write(f"**Time:** {last.name}")

                # Chart
                plot_df = ltf.tail(200)
                fig = go.Figure(data=[go.Candlestick(
                    x=plot_df.index, open=plot_df["open"], high=plot_df["high"],
                    low=plot_df["low"], close=plot_df["close"]
                )])
                fig.add_hline(y=last["entry"], line_color="#00d4aa", annotation_text="Entry")
                fig.add_hline(y=last["sl"], line_color="#ff1744", annotation_text="SL")
                fig.add_hline(y=last["tp"], line_color="#00c853", annotation_text="TP")
                fig.update_layout(template="plotly_dark", height=450,
                                  xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👈 Configure settings in the sidebar and click **Run Analysis**")
    st.markdown("""
    ### Features
    - **Scanner** – Scan all major pairs for SMC setups
    - **Backtest** – Full historical simulation with Partial TP + Trailing
    - **Signals** – Latest actionable entry with SL/TP
    - Order Blocks • FVG • Breakers • Liquidity Sweeps
    - Premium/Discount • Killzones • News Filter • S/R
    """)

st.sidebar.markdown("---")
st.sidebar.caption("SMC Forex Bot v2.1 • Educational use only")
