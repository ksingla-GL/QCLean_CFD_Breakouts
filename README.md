# CFD Breakout Strategy - LEAN Python Implementation

## Project Structure
- `main.py` - Core algorithm with QCAlgorithm implementation
- `signal_generator.py` - Signal generation logic (separated from execution)
- `order_manager.py` - Order execution handler (IBKR-ready architecture)
- `trade_logger.py` - Logging and trade recording system

## Setup Instructions

### 1. Upload to QuantConnect
- Create new Python algorithm in QC
- Upload all files from `src/` folder
- Set main.py as primary algorithm file

### 2. Configure Parameters
Set the following parameters in QC UI:
- `tickers`: "AAPL,MSFT,GOOGL" (comma-separated list)
- `long_entry_offset`: 0.02
- `short_entry_offset`: 0.02
- `tp_percentage`: 0.05
- `sl_percentage`: 0.03

### 3. Run Backtest
- Set date range as needed
- Click "Run Backtest"
- Verify initialization logs appear

## Architecture Notes
- Strategy logic is completely separated from execution
- Parameters are externalized for easy modification
- Same code structure will work for both backtest and live trading
- IBKR CFD-specific implementations will be added in OrderManager