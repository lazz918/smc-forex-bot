# SMC Forex Bot (demo + backtest)

Educational SMC / support-resistance bot for **demo testing and backtesting only**.  
Not financial advice. Do not use on a live account until you have long demo results you accept.

## What you get

| File | Purpose |
|------|---------|
| `smc_bot.py` | Python bot: Yahoo data, SMC signals, backtest, scanner |
| `START.bat` | Double-click to backtest on Windows |
| `SCANNER.bat` | Double-click to scan all pairs |
| `SMC_SR_EA.mq5` | MetaTrader 5 Expert Advisor (demo chart + Strategy Tester) |

Python does **not** place broker orders. Only the MT5 EA can trade, and only if you attach it in MT5.

## 1. Download

https://github.com/lazz918/smc-forex-bot/archive/refs/heads/main.zip

Extract to `C:\SMC_Bot` so you see `smc_bot.py` directly in that folder.

## 2. Python backtest (no MT5)

Needs Python 3.10–3.14 with **Add python.exe to PATH**.

CMD:

```bat
cd /d C:\SMC_Bot
py -m pip install pandas numpy
py smc_bot.py
```

Or double-click `START.bat`.

You should see trades, win rate, net PnL, then `Done.`  
Results also save to `smc_signals.csv`.

### Other commands

```bat
py smc_bot.py scanner
py smc_bot.py loop
```

`loop` rescans every 5 minutes.

### VS Code

File → Open Folder → `C:\SMC_Bot`  
Install Microsoft Python extension  
`Python: Select Interpreter` → 3.14  
Terminal: `py smc_bot.py`

## 3. MT5 Strategy Tester (EA backtest)

1. MT5 → File → Open Data Folder → `MQL5\Experts\`
2. Copy `SMC_SR_EA.mq5` there
3. F4 → open EA → F7 compile (0 errors)
4. Ctrl+R Strategy Tester:
   - Expert: `SMC_SR_EA`
   - Symbol: EURUSD (your broker name)
   - Timeframe: **M15**
   - Dates: 3–6 months
   - Modelling: every tick or 1-minute OHLC
   - Deposit: 10000
   - Optimization: off
5. Start → read Results / Graph / Report

## 4. MT5 demo forward test

1. Open **EURUSD M15**
2. Drag `SMC_SR_EA` onto the chart
3. Allow Algo Trading
4. Toolbar **Algo Trading** = green
5. Use a **Demo** login only

## Strategy (short)

H4/1h bias → M15 liquidity sweep or BOS/CHoCH → Order Block / Breaker / FVG  
Session + killzone + simple news window  
Partial TP at 1R, trail after 1.5R, target 2R

## Disclaimer

Backtests are not live results. Spread, slippage, news and broker rules will differ. You can lose the entire demo or live deposit.
