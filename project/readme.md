# CFD Breakout Trading Strategy

A LEAN-based algorithmic trading strategy for IBKR that implements OCO entry orders with dynamic stop-loss adjustments and time-based exits.

## Features

- **OCO Entry Orders**: Simultaneous long/short stop-limit orders at market open (±2% from open)
- **Bracket Exit Orders**: Automatic TP (5%) and SL (3%) placement on fill
- **Dynamic Stop Adjustment**: Moves SL to breakeven+1% when position reaches 4% profit
- **Time-Stop Exit**: Closes positions at D+4 market open
- **Risk Controls**: Daily loss limits, kill-switch, earnings blackout
- **Portfolio Reconciliation**: Detects manual interventions and halts affected tickers

---

## Strategy Logic

### Entry (Market Open - 09:30 ET)
1. Capture official opening price for each ticker
2. Place OCO stop-limit orders:
   - **Long**: Entry at `open × 1.02` (limit at `entry × 1.001`)
   - **Short**: Entry at `open × 0.98` (limit at `entry × 0.999`)
3. First fill cancels the opposite order
4. Bracket orders (TP/SL) automatically placed on fill

### Exit Conditions
1. **Take Profit**: ±5% from entry (limit order)
2. **Stop Loss**: ∓3% from entry (stop-market order for immediate fill)
3. **Capture Point**: At ±4% profit, SL moves to breakeven+1% (stop-market)
4. **Time-Stop**: D+4 market open liquidation (no time-stop during earnings blackout)

### Risk Controls
- **Earnings Blackout (D-2 to D+1)**: No new entries, no time-stop exits
- **Daily Max Loss**: Halts new trades and cancels open orders when limit exceeded
- **Kill-Switch**: Global trading disable via parameter
- **Portfolio Reconciliation**: Detects/halts tickers with manual intervention

---

## File Structure

```
project/
├── main.py               # Main algorithm logic
├── signal_generator.py   # Entry signal calculations
├── order_manager.py      # Order placement and management
├── trade_logger.py       # Logging
└── README.md            # This file
```

---

## Installation & Deployment

### QuantConnect Cloud
1. Create new algorithm project in QuantConnect
2. Upload all `.py` files to project
3. Set parameters (see below)
4. Run backtest or deploy to paper/live

### Local LEAN
```bash
# Clone LEAN engine
git clone https://github.com/QuantConnect/Lean.git

# Place strategy files in
Lean/Algorithm.Python/

# Configure launcher.json with parameters
# Run backtest
lean backtest "CFDBreakoutStrategy"
```

---

## Parameters

Configure via `SetParameter()` in QuantConnect or `config.json` in LEAN CLI:

### Trading Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tickers` | string | `"AAPL,MSFT,GOOGL"` | Comma-separated ticker list |
| `use_cfds` | bool | `false` | Trade CFDs vs equities |
| `position_size` | float | `10000` | Dollar amount per position |
| `long_entry_offset` | float | `0.02` | Long entry offset (2% above open) |
| `short_entry_offset` | float | `0.02` | Short entry offset (2% below open) |

### Exit Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tp_percentage` | float | `0.05` | Take profit % (5%) |
| `sl_percentage` | float | `0.03` | Stop loss % (3%) |
| `capture_point_pct` | float | `0.04` | Profit level to trigger SL adjustment (4%) |
| `breakeven_offset` | float | `0.01` | Breakeven SL offset (1%) |
| `timestop_days` | int | `4` | Days to hold before time-stop (D+4) |

### Risk Controls
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `trading_enabled` | bool | `true` | **Kill-switch**: Disable all trading |
| `max_daily_loss` | float | `2000` | Daily loss limit ($ amount, enter as positive) |

### Earnings Blackout
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `earnings_dates` | string | `""` | Format: `"AAPL:2024-01-25,AAPL:2024-04-25,MSFT:2024-01-30"` |

**Multiple dates per ticker supported.** Blocks new entries and time-stops for D-2 to D+1 window around each date.

---

## Parameter Examples

### Example 1: Basic Configuration
```python
self.set_parameter("tickers", "AAPL,MSFT,GOOGL")
self.set_parameter("position_size", "10000")
self.set_parameter("tp_percentage", "0.05")
self.set_parameter("sl_percentage", "0.03")
```

### Example 2: With Risk Controls
```python
self.set_parameter("trading_enabled", "true")
self.set_parameter("max_daily_loss", "1500")  # Stop trading after -$1500 loss
```

### Example 3: Earnings Blackout (Multiple Dates)
```python
# AAPL Q1-Q4 2024 earnings
self.set_parameter("earnings_dates", "AAPL:2024-02-01,AAPL:2024-05-02,AAPL:2024-08-01,AAPL:2024-11-01")
```

### Example 4: Emergency Kill-Switch
```python
self.set_parameter("trading_enabled", "false")  # Stops all new entries immediately
```

---

## Running the Strategy

### Backtest (QuantConnect)
1. Set date range in `initialize()`:
   ```python
   self.set_start_date(2024, 1, 1)
   self.set_end_date(2024, 12, 31)
   ```
2. Configure parameters via `SetParameter()` or UI
3. Click "Run Backtest"

### Paper Trading (QuantConnect)
1. Configure parameters
2. Deploy to Paper Trading
3. Monitor via Logs tab

### Live Trading (IBKR)
1. Connect IBKR account in QuantConnect
2. Configure parameters (especially `trading_enabled`, `max_daily_loss`)
3. **Test with small position sizes first**
4. Deploy to Live Trading

---

## Risk Management

### Daily Loss Limit
When daily loss exceeds `max_daily_loss` (e.g., -$2000 when limit is 2000):
1. Halts all new entry orders
2. Cancels all pending OCO orders
3. Allows existing positions to exit via TP/SL/timestop
4. Resets next trading day

### Kill-Switch
Set `trading_enabled = "false"` to:
- Block all new OCO orders at market open
- Cancel pending OCO orders
- Allow existing positions to continue
- Useful for: market volatility, news events, manual override

### Earnings Blackout
D-2 to D+1 around earnings (4 trading days total):
- **No new entries** - Skips OCO placement
- **No time-stop exits** - Positions held through earnings
- TP/SL exits still active
- Supports multiple earnings dates per ticker

### Portfolio Reconciliation
Runs at market open and after every order event:
- Compares bot's expected state vs IBKR actual positions
- Detects manual trades (e.g., closing position via TWS)
- Halts affected ticker to prevent unintended shorts/longs

---

## Troubleshooting

### No Orders Placed
1. Check `trading_enabled = "true"`
2. Verify daily loss limit not exceeded
3. Check earnings blackout dates
4. Ensure ticker not already traded today

### Orders Not Filling
- Long stop-limits trigger above open; shorts below
- Check market volatility (price may jump past stop+limit)
- Review order logs for `Invalid` status

### Duplicate Trades Same Day
- Should not happen - file bug report if seen
- `traded_today` set prevents re-entry after exit

### Manual Intervention Halt
- Bot detected position mismatch with IBKR
- Halted ticker will not trade until next restart
- Check TWS for manual trades

---

## Changelog

**Milestone 5 (Current)**
- Added daily max loss limits
- Added kill-switch parameter
- Fixed earnings blackout to support multiple dates per ticker

**Milestone 4**
- Implemented capture point stop-loss adjustment
- Added D+4 time-stop exit
- Added earnings blackout (D-2 to D+1)
- Added portfolio reconciliation safeguard

**Milestone 3**
- OCO entry orders with bracket exits
- Tick rounding for IBKR compatibility
- Stop-market orders for reliable exits

**Milestone 2**
- LEAN scheduling for market open detection
- Session handling and production safety

**Milestone 1**
- Project skeleton with parameter externalization
- Core strategy logic separation

---

## License

Proprietary - Client Use Only
