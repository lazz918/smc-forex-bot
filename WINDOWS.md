# How to run on Windows

1. Click **Code** (green button) on this GitHub page → **Download ZIP**
2. Right-click the zip → Extract All → extract to `C:\SMC_Bot`
3. Open `C:\SMC_Bot` and make sure you see `smc_forex_bot_v2.py` and `START.bat`
4. Double-click **START.bat**

Or in Command Prompt:

```
cd /d C:\SMC_Bot
py -m pip install pandas numpy yfinance requests streamlit plotly
py smc_forex_bot_v2.py
```
