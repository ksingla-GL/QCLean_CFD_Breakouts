# CFD Breakout Strategy - LEAN Python Implementation

> **Status**: Milestone 1 Complete  
> **Compatibility**: QuantConnect LEAN + IBKR CFDs  
> **Trading Style**: Breakout strategy with OCO entries and bracket exits

## Overview

This project implements a CFD breakout trading strategy for IBKR, designed to:
- Trade CFD instruments using breakout methodology
- Place OCO (One-Cancels-Other) entry orders at market open
- Execute bracket orders (TP/SL) on fills
- Support both backtesting and live trading environments

## Project Structure

```
QCLean_CFD_Breakouts/
├── config/
│   └── parameters.json          # Trading parameters configuration
├── project/
│   ├── main.py                  # Main QCAlgorithm implementation
│   ├── signal_generator.py      # Entry signal logic (separated)
│   ├── order_manager.py         # Order execution handler
│   └── trade_logger.py          # Logging and trade recording
└── README.md                    # This file
```

## Quick Start Guide

### 1. Upload to QuantConnect

1. Create a new Python algorithm in QuantConnect
2. Upload all files from the `project/` folder
3. Set `main.py` as the primary algorithm file
4. Verify all imports resolve correctly

### 2. Configure Trading Parameters

**Option A: QuantConnect UI Parameters**
```
tickers: "AAPL,MSFT,GOOGL"
long_entry_offset: 0.02
short_entry_offset: 0.02
tp_percentage: 0.05
sl_percentage: 0.03
```

**Option B: Modify parameters.json**
```json
{
  "parameters": {
    "long_entry_offset": 0.02,
    "short_entry_offset": 0.02,
    "tp_percentage": 0.05,
    "sl_percentage": 0.03,
    "tickers": "AAPL,MSFT,GOOGL"
  }
}
```

### 3. Run Backtest

1. Set backtest date range (e.g., 2024-01-01 to 2024-12-31)
2. Click "Run Backtest"
3. Verify initialization logs show parameter loading
4. Confirm universe setup with selected tickers

## Trading Parameters

| Parameter | Description | Default | Range |
|-----------|-------------|---------|-------|
| `long_entry_offset` | Long stop above open (%) | 0.02 | 0.01-0.05 |
| `short_entry_offset` | Short stop below open (%) | 0.02 | 0.01-0.05 |
| `tp_percentage` | Take profit target (%) | 0.05 | 0.02-0.10 |
| `sl_percentage` | Stop loss limit (%) | 0.03 | 0.01-0.05 |
| `tickers` | Trading universe | "AAPL,MSFT,GOOGL" | Any CFD symbols |

##  Architecture Design

### Separation of Concerns
- **SignalGenerator**: Determines what to trade (signal logic)
- **OrderManager**: Handles how to trade (execution)  
- **TradeLogger**: Records and monitors activity
- **Main Algorithm**: Orchestrates components and timing

### Key Features (Milestone 1)
-  **Externalized Parameters**: No code edits needed for strategy tuning
-  **Modular Architecture**: Strategy logic separated from execution
-  **Logging Framework**: Comprehensive event and trade logging
-  **LEAN Compatible**: Runs in backtest mode with proper QC structure
-  **IBKR Ready**: Order manager designed for CFD execution

##  Development Roadmap

| Milestone | Status | Features |
|-----------|--------|----------|
| **M1** |  Complete | Project skeleton, parameters, logging |
| **M2** |  Next | Session handling, market open detection |
| **M3** |  Planned | OCO entries, bracket orders |
| **M4** |  Planned | Capture point, time stops |
| **M5** |  Planned | Risk controls, CSV logging |
| **M6** |  Planned | Live trading toggle |

##  Expected Log Output

When running successfully, you should see:
```
==================================================
CFD Breakout Strategy Initialized
==================================================
Trading Parameters:
  Long Entry: +2.0%
  Short Entry: -2.0%
  Take Profit: 5.0%
  Stop Loss: 3.0%
  Tickers: AAPL,MSFT,GOOGL
==================================================
Universe initialized with 3 symbols
```

##  Troubleshooting

**Common Issues:**
- **Import Errors**: Ensure all .py files are uploaded to QC
- **Parameter Not Found**: Check parameter names match exactly
- **No Log Output**: Verify algorithm initialization completed
- **Symbol Errors**: Confirm tickers are available in QC universe

##  Notes

- Current implementation is milestone 1 skeleton
- Order placement logic is placeholder (M3)
- Session handling simplified (M2) 
- Risk controls pending (M5)
- Designed for future IBKR CFD integration