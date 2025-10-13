from AlgorithmImports import *
from signal_generator import SignalGenerator
from order_manager import OrderManager
from trade_logger import TradeLogger
import json
from datetime import timedelta

class CFDBreakoutStrategy(QCAlgorithm):
    
    def initialize(self):
        # Basic setup
        self.set_start_date(2024, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.set_time_zone("America/New_York")
        
        # Set brokerage model for IBKR
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)
        
        # Load parameters
        self.load_parameters()
        
        # Initialize components
        self.signal_generator = SignalGenerator(self.parameters)
        self.order_manager = OrderManager(self)
        self.logger = TradeLogger(self)
        
        # Trading state
        self.daily_open_prices = {}
        self.bot_positions = {}  # Bot's expected state
        self.position_metadata = {}  # Store entry times and trading days count
        self.processed_today = False
        self.reconciliation_halts = set()
        self.capture_point_adjusted = {}  # Track which positions had SL adjusted
        self.last_trading_day = None  # Track trading days
        self.traded_today = set()  # Track tickers that have traded today
        
        # Setup universe
        self.setup_universe()
        
        # Initial reconciliation
        self.reconcile_positions(is_startup=True)
        
        # Setup LEAN scheduling
        self.setup_scheduling()
        
        # Basic logging
        self.setup_logging()
        
    def load_parameters(self):
        """Load parameters from SetParameter"""
        self.parameters = {
            'long_entry_offset': float(self.get_parameter("long_entry_offset") or 0.02),
            'short_entry_offset': float(self.get_parameter("short_entry_offset") or 0.02),
            'tp_percentage': float(self.get_parameter("tp_percentage") or 0.05),
            'sl_percentage': float(self.get_parameter("sl_percentage") or 0.03),
            'timestop_days': int(self.get_parameter("timestop_days") or 4),
            'position_size': float(self.get_parameter("position_size") or 10000),  # $ per position
            'tickers': self.get_parameter("tickers") or "AAPL,MSFT,GOOGL",
            'use_cfds': self.get_parameter("use_cfds") or "false",
            'capture_point_pct': float(self.get_parameter("capture_point_pct") or 0.04),  # 4% capture point
            'breakeven_offset': float(self.get_parameter("breakeven_offset") or 0.01),  # 1% above breakeven
            # Earnings dates format: "TICKER:YYYY-MM-DD,TICKER:YYYY-MM-DD"
            'earnings_dates': self.get_parameter("earnings_dates") or ""
        }
        
        # Parse earnings dates
        self.earnings_calendar = {}
        if self.parameters['earnings_dates']:
            for entry in self.parameters['earnings_dates'].split(','):
                if ':' in entry:
                    ticker, date_str = entry.split(':')
                    try:
                        earnings_date = datetime.strptime(date_str.strip(), '%Y-%m-%d')
                        self.earnings_calendar[ticker.strip()] = earnings_date
                    except:
                        self.debug(f"Invalid earnings date format: {entry}")
            
    def setup_universe(self):
        """Add tickers to universe"""
        self.tickers = [t.strip() for t in self.parameters['tickers'].split(",")]
        use_cfds = self.parameters['use_cfds'].lower() == "true"
        
        for ticker in self.tickers:
            # Add symbol based on type
            if use_cfds:
                try:
                    symbol = self.add_cfd(ticker, Resolution.MINUTE)
                except:
                    symbol = self.add_equity(ticker, Resolution.MINUTE)
                    self.debug(f"CFD unavailable for {ticker}, using equity")
            else:
                symbol = self.add_equity(ticker, Resolution.MINUTE)
            
            # Initialize tracking
            self.bot_positions[ticker] = {
                'has_position': False,
                'is_entry_pending': False,  # OCO orders placed
                'entry_price': None,
                'entry_time': None,
                'direction': None  # 'long' or 'short'
            }
            
            self.position_metadata[ticker] = {
                'entry_time': None,
                'trading_days_held': 0  # Track trading days since entry
            }
            
            self.capture_point_adjusted[ticker] = False
            
        self.debug(f"Universe: {len(self.tickers)} symbols")
            
    def setup_scheduling(self):
        """Setup LEAN scheduling"""
        if not self.tickers:
            return
            
        schedule_symbol = self.symbol(self.tickers[0])
        
        # Market open - capture price and place orders
        self.schedule.on(
            self.date_rules.every_day(schedule_symbol),
            self.time_rules.after_market_open(schedule_symbol, 0),
            self.capture_market_open
        )
        
        # End of day
        self.schedule.on(
            self.date_rules.every_day(schedule_symbol),
            self.time_rules.before_market_close(schedule_symbol, 5),
            self.end_of_day_processing
        )
        
        self.debug("Scheduling configured")
        
    def is_in_earnings_blackout(self, ticker):
        """Check if ticker is in earnings blackout period (D-2 to D+1)"""
        if ticker not in self.earnings_calendar:
            return False
            
        earnings_date = self.earnings_calendar[ticker]
        current_date = self.time.date()
        earnings_date_only = earnings_date.date()
        
        # D-2 to D+1 blackout window
        blackout_start = earnings_date_only - timedelta(days=2)
        blackout_end = earnings_date_only + timedelta(days=1)
        
        return blackout_start <= current_date <= blackout_end
        
    def reconcile_positions(self, ticker=None, is_startup=False):
        """Reconcile bot state with broker positions"""
        if is_startup:
            self.debug("="*50)
            self.debug("Startup reconciliation")
            
        tickers_to_check = [ticker] if ticker else self.tickers
        all_reconciled = True
        
        for t in tickers_to_check:
            if not is_startup and t in self.reconciliation_halts:
                all_reconciled = False
                continue
                
            symbol = self.symbol(t)
            broker_position = self.portfolio[symbol]
            
            if is_startup:
                # On startup, sync with broker
                if broker_position.invested:
                    self.bot_positions[t]['has_position'] = True
                    self.bot_positions[t]['entry_price'] = broker_position.average_price
                    self.bot_positions[t]['direction'] = 'long' if broker_position.quantity > 0 else 'short'
                    
                    # For paper/live trading, use current time as we can't recover entry time
                    # In production, you'd store this in a database or file
                    self.position_metadata[t]['entry_time'] = self.time
                    self.position_metadata[t]['trading_days_held'] = 0
                    self.debug(f"Found existing position: {t} {self.bot_positions[t]['direction']} @ ${broker_position.average_price:.2f}")
                    self.debug(f"WARNING: Cannot recover entry time for {t}, using current time (time-stop may be inaccurate)")
                else:
                    self.bot_positions[t]['has_position'] = False
            else:
                # Runtime check - detect manual intervention
                bot_has_position = self.bot_positions[t]['has_position']
                broker_has_position = broker_position.invested
                
                if bot_has_position != broker_has_position:
                    self.debug(f"Mismatch {t}: bot thinks {bot_has_position}, broker has {broker_has_position}")
                    self.debug(f"Halting {t} - manual intervention detected")
                    self.reconciliation_halts.add(t)
                    
                    # Log manual override
                    self.logger.log_trade(t, "OVERRIDE", 0, 0, 0, "ManualIntervention")
                    
                    # Sync state and cancel orders
                    self.bot_positions[t]['has_position'] = broker_has_position
                    self.transactions.cancel_open_orders(symbol)
                    self.order_manager.cleanup_ticker(t)
                    all_reconciled = False
                    
        if is_startup:
            self.debug("Reconciliation complete")
            
        return all_reconciled
        
    def capture_market_open(self):
        """Capture opening price and place OCO orders"""
        if self.processed_today:
            return
            
        self.debug("="*50)
        self.debug(f"Market open at {self.time}")
        
        # Track that we have a new trading day
        current_day = self.time.date()
        if self.last_trading_day != current_day:
            self.last_trading_day = current_day
            
            # Increment trading days for all positions
            for ticker in self.tickers:
                if self.bot_positions[ticker]['has_position']:
                    self.position_metadata[ticker]['trading_days_held'] += 1
                    self.debug(f"{ticker} position day counter: D+{self.position_metadata[ticker]['trading_days_held']}")
        
        # Check for overnight manual interventions
        self.reconcile_positions(is_startup=False)
        
        # First, check for D+4 time-stops
        self.process_timestops()
        
        self.daily_open_prices = {}
        
        for ticker in self.tickers:
            # Skip halted tickers
            if ticker in self.reconciliation_halts:
                self.debug(f"{ticker} halted")
                continue
                
            symbol = self.symbol(ticker)
            
            # Get opening price
            if self.securities[symbol].open > 0:
                open_price = self.securities[symbol].open
                self.daily_open_prices[ticker] = open_price
                
                self.debug(f"{ticker} open: ${open_price:.2f}")
                
                # Check if ticker already traded today
                if ticker in self.traded_today:
                    self.debug(f"  {ticker} already traded today - no new entries")
                    continue
                
                # Check earnings blackout for new entries
                if self.is_in_earnings_blackout(ticker):
                    self.debug(f"  {ticker} in earnings blackout - no new trades")
                    continue
                
                # Only place orders if no position and no pending orders
                if not self.bot_positions[ticker]['has_position'] and not self.bot_positions[ticker]['is_entry_pending']:
                    # Generate and place OCO orders
                    signals = self.signal_generator.generate_entry_signals(ticker, open_price)
                    if signals:
                        signals['position_size'] = self.parameters['position_size']
                        if self.order_manager.place_oco_orders(symbol, signals):
                            self.bot_positions[ticker]['is_entry_pending'] = True
                            self.debug(f"  OCO orders placed for {ticker}")
                else:
                    if self.bot_positions[ticker]['has_position']:
                        self.debug(f"  {ticker} has position - skipping")
                    elif self.bot_positions[ticker]['is_entry_pending']:
                        self.debug(f"  {ticker} has pending OCO - skipping")
            else:
                self.debug(f"Warning: No opening price for {ticker}")
                
        self.processed_today = True
        
    def process_timestops(self):
        """Process D+4 time-stop exits at market open"""
        for ticker in self.tickers:
            if ticker in self.reconciliation_halts:
                continue
                
            if not self.bot_positions[ticker]['has_position']:
                continue
                
            # Get trading days held
            trading_days_held = self.position_metadata[ticker]['trading_days_held']
            
            # Check if time-stop should trigger (D+4 means 4 trading days after entry)
            if trading_days_held >= self.parameters['timestop_days']:
                # Check if in earnings blackout - no timestops during earnings
                if self.is_in_earnings_blackout(ticker):
                    self.debug(f"{ticker} D+{trading_days_held} timestop blocked by earnings blackout")
                    continue
                    
                # Execute time-stop
                symbol = self.symbol(ticker)
                
                # Cancel any existing bracket orders
                self.order_manager.cleanup_ticker(ticker)
                
                # Get position details before liquidation
                position = self.portfolio[symbol]
                entry_price = self.bot_positions[ticker]['entry_price']
                direction = self.bot_positions[ticker]['direction']
                quantity = abs(position.quantity)
                
                # Liquidate position and get the order tickets
                liquidate_tickets = self.liquidate(symbol, tag="TimeStop_D+4")
                
                # Get exit price from liquidation or use current price
                exit_price = self.securities[symbol].price
                
                # For immediate fills in backtest, use the current price
                # In live trading, you'd wait for the fill
                if self.securities[symbol].open > 0:
                    exit_price = self.securities[symbol].open
                
                # Calculate PnL correctly
                if direction == 'long':
                    pnl = (exit_price - entry_price) * quantity
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                else:
                    pnl = (entry_price - exit_price) * quantity
                    pnl_pct = ((entry_price - exit_price) / entry_price) * 100
                
                self.debug(f"TimeStop executed: {ticker} @ ${exit_price:.2f} (D+{trading_days_held}, {pnl_pct:+.2f}%)")
                
                # Log the trade with correct PnL
                self.logger.log_trade(ticker, direction, entry_price, exit_price, pnl, "TimeStop")
                
                # Mark ticker as traded today - PREVENT RE-ENTRY
                self.traded_today.add(ticker)
                
                # Reset position state
                self.bot_positions[ticker]['has_position'] = False
                self.bot_positions[ticker]['entry_price'] = None
                self.bot_positions[ticker]['entry_time'] = None
                self.bot_positions[ticker]['direction'] = None
                self.position_metadata[ticker]['entry_time'] = None
                self.position_metadata[ticker]['trading_days_held'] = 0
                self.capture_point_adjusted[ticker] = False
    
    def on_data(self, data):
        """Monitor positions for capture-point SL adjustment"""
        for ticker in self.tickers:
            # Skip if halted or no position
            if ticker in self.reconciliation_halts:
                continue
                
            pos = self.bot_positions[ticker]
            if not pos['has_position'] or not pos['entry_price']:
                continue
                
            # Skip if already adjusted
            if self.capture_point_adjusted[ticker]:
                continue
                
            symbol = self.symbol(ticker)
            current_price = self.securities[symbol].price
            
            if current_price <= 0:
                continue
                
            entry_price = pos['entry_price']
            capture_point_pct = self.parameters['capture_point_pct']
            
            # Check if capture point reached
            capture_point_hit = False
            if pos['direction'] == 'long':
                capture_target = entry_price * (1 + capture_point_pct)
                if current_price >= capture_target:
                    capture_point_hit = True
                    self.debug(f"{ticker} long capture point hit: ${current_price:.2f} >= ${capture_target:.2f}")
            else:  # short
                capture_target = entry_price * (1 - capture_point_pct)
                if current_price <= capture_target:
                    capture_point_hit = True
                    self.debug(f"{ticker} short capture point hit: ${current_price:.2f} <= ${capture_target:.2f}")
            
            # Adjust stop-loss to breakeven + offset
            if capture_point_hit:
                if self.order_manager.adjust_sl_to_breakeven(symbol, ticker, entry_price, pos['direction']):
                    self.capture_point_adjusted[ticker] = True
        
    def on_order_event(self, order_event):
        """Handle order events - coordinate with order manager"""
        # More robust symbol parsing for paper/live trading
        symbol_str = str(order_event.symbol)
        if ' ' in symbol_str:
            ticker = symbol_str.split(' ')[0]
        else:
            # Handle cases where symbol doesn't have space
            ticker = symbol_str.replace('CFD', '').replace('EQUITY', '').strip()
        
        # Let order manager process OCO and bracket logic
        fill_type = self.order_manager.handle_order_event(order_event)
        
        # Update bot state based on what happened
        if order_event.status == OrderStatus.FILLED and fill_type:
            
            # Don't update if ticker is halted
            if ticker in self.reconciliation_halts:
                self.debug(f"Ignoring fill for halted ticker {ticker}")
                return
                
            if fill_type == 'entry_long':
                self.bot_positions[ticker]['has_position'] = True
                self.bot_positions[ticker]['is_entry_pending'] = False
                self.bot_positions[ticker]['direction'] = 'long'
                self.bot_positions[ticker]['entry_price'] = order_event.fill_price
                self.bot_positions[ticker]['entry_time'] = self.time
                self.position_metadata[ticker]['entry_time'] = self.time
                self.position_metadata[ticker]['trading_days_held'] = 0  # Reset counter
                self.capture_point_adjusted[ticker] = False
                
                # Mark ticker as traded today
                self.traded_today.add(ticker)
                
                self.debug(f"Entry recorded: {ticker} long @ ${order_event.fill_price:.2f}")
                
            elif fill_type == 'entry_short':
                self.bot_positions[ticker]['has_position'] = True
                self.bot_positions[ticker]['is_entry_pending'] = False
                self.bot_positions[ticker]['direction'] = 'short'
                self.bot_positions[ticker]['entry_price'] = order_event.fill_price
                self.bot_positions[ticker]['entry_time'] = self.time
                self.position_metadata[ticker]['entry_time'] = self.time
                self.position_metadata[ticker]['trading_days_held'] = 0  # Reset counter
                self.capture_point_adjusted[ticker] = False
                
                # Mark ticker as traded today
                self.traded_today.add(ticker)
                
                self.debug(f"Entry recorded: {ticker} short @ ${order_event.fill_price:.2f}")
                
            elif fill_type in ['exit_tp', 'exit_sl', 'exit_sl_adjusted']:
                # Position closed
                entry_price = self.bot_positions[ticker]['entry_price']
                exit_price = order_event.fill_price
                direction = self.bot_positions[ticker]['direction']
                
                # Calculate PnL
                if direction == 'long':
                    pnl = (exit_price - entry_price) * abs(order_event.fill_quantity)
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                else:
                    pnl = (entry_price - exit_price) * abs(order_event.fill_quantity)
                    pnl_pct = ((entry_price - exit_price) / entry_price) * 100
                    
                # Determine exit reason
                if fill_type == 'exit_tp':
                    exit_reason = "TakeProfit"
                elif fill_type == 'exit_sl_adjusted':
                    exit_reason = "StopLoss_Adjusted"
                else:
                    exit_reason = "StopLoss"
                    
                self.debug(f"Exit recorded: {ticker} @ ${exit_price:.2f} ({exit_reason}, {pnl_pct:+.2f}%)")
                
                # Log the trade
                self.logger.log_trade(ticker, direction, entry_price, exit_price, pnl, exit_reason)
                
                # Mark ticker as traded today - PREVENT RE-ENTRY
                self.traded_today.add(ticker)
                
                # Reset position state
                self.bot_positions[ticker]['has_position'] = False
                self.bot_positions[ticker]['entry_price'] = None
                self.bot_positions[ticker]['entry_time'] = None
                self.bot_positions[ticker]['direction'] = None
                self.position_metadata[ticker]['entry_time'] = None
                self.position_metadata[ticker]['trading_days_held'] = 0
                self.capture_point_adjusted[ticker] = False
                
        elif order_event.status == OrderStatus.CANCELED:
            # Handle OCO cancellation
            if ticker in self.bot_positions and self.bot_positions[ticker]['is_entry_pending']:
                # Check if all OCO orders are now canceled
                if not self.order_manager.has_pending_oco(ticker):
                    self.bot_positions[ticker]['is_entry_pending'] = False
                    
        self.logger.log_order_event(order_event)
        
    def end_of_day_processing(self):
        """End of day cleanup"""
        self.processed_today = False
        
        # Cancel any unfilled OCO orders
        for ticker in self.tickers:
            if self.bot_positions[ticker]['is_entry_pending']:
                symbol = self.symbol(ticker)
                self.order_manager.cancel_oco_orders(ticker)
                self.bot_positions[ticker]['is_entry_pending'] = False
                self.debug(f"Canceled unfilled OCO orders for {ticker}")
                
        if self.reconciliation_halts:
            self.debug(f"Halted tickers: {self.reconciliation_halts}")
            
        # Clear traded today set for next trading day
        if self.traded_today:
            self.debug(f"Traded today (blocked re-entry): {self.traded_today}")
        self.traded_today.clear()
            
        # Daily summary
        self.logger.daily_summary(self.time)
        
    def setup_logging(self):
        """Initial logging"""
        self.debug("="*50)
        self.debug("CFD BREAKOUT STRATEGY")
        self.debug(f"Long offset: +{self.parameters['long_entry_offset']*100:.1f}%")
        self.debug(f"Short offset: -{self.parameters['short_entry_offset']*100:.1f}%")
        self.debug(f"TP: {self.parameters['tp_percentage']*100:.1f}%")
        self.debug(f"SL: {self.parameters['sl_percentage']*100:.1f}%")
        self.debug(f"Capture point: {self.parameters['capture_point_pct']*100:.1f}%")
        self.debug(f"Breakeven offset: {self.parameters['breakeven_offset']*100:.1f}%")
        self.debug(f"Time-stop: D+{self.parameters['timestop_days']}")
        self.debug(f"Position size: ${self.parameters['position_size']}")
        self.debug(f"Tickers: {self.parameters['tickers']}")
        if self.earnings_calendar:
            self.debug(f"Earnings dates loaded: {len(self.earnings_calendar)} tickers")
        self.debug("="*50)
