from AlgorithmImports import *
from signal_generator import SignalGenerator
from order_manager import OrderManager
from trade_logger import TradeLogger
import json

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
        self.position_metadata = {}  # Store entry times for D+4
        self.processed_today = False
        self.reconciliation_halts = set()
        
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
            'use_cfds': self.get_parameter("use_cfds") or "false"
        }
            
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
                'entry_time': None
            }
            
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
                    
                    # Try to recover entry time (ObjectStore may not be available)
                    try:
                        stored_meta = self.object_store.read(f"{t}_entry")
                        if stored_meta:
                            meta = json.loads(stored_meta)
                            entry_time_str = meta.get('time')
                            if entry_time_str:
                                self.position_metadata[t]['entry_time'] = self.time
                        self.debug(f"Found position: {t} {self.bot_positions[t]['direction']}")
                    except:
                        # ObjectStore not available, use current time as fallback
                        self.position_metadata[t]['entry_time'] = self.time
                        self.debug(f"Found position: {t} {self.bot_positions[t]['direction']} (no stored time)")
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
        
        # Check for overnight manual interventions
        self.reconcile_positions(is_startup=False)
        
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
        
    def on_order_event(self, order_event):
        """Handle order events - coordinate with order manager"""
        ticker = str(order_event.symbol).split(' ')[0]
        
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
                
                # Persist entry time (only if ObjectStore available)
                try:
                    self.object_store.save(f"{ticker}_entry", json.dumps({'time': str(self.time)}))
                except:
                    pass  # ObjectStore not available in backtest
                self.debug(f"Entry recorded: {ticker} long @ ${order_event.fill_price:.2f}")
                
            elif fill_type == 'entry_short':
                self.bot_positions[ticker]['has_position'] = True
                self.bot_positions[ticker]['is_entry_pending'] = False
                self.bot_positions[ticker]['direction'] = 'short'
                self.bot_positions[ticker]['entry_price'] = order_event.fill_price
                self.bot_positions[ticker]['entry_time'] = self.time
                self.position_metadata[ticker]['entry_time'] = self.time
                
                # Persist entry time (only if ObjectStore available)
                try:
                    self.object_store.save(f"{ticker}_entry", json.dumps({'time': str(self.time)}))
                except:
                    pass  # ObjectStore not available in backtest
                self.debug(f"Entry recorded: {ticker} short @ ${order_event.fill_price:.2f}")
                
            elif fill_type in ['exit_tp', 'exit_sl']:
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
                    
                exit_reason = "TakeProfit" if fill_type == 'exit_tp' else "StopLoss"
                self.debug(f"Exit recorded: {ticker} @ ${exit_price:.2f} ({exit_reason}, {pnl_pct:+.2f}%)")
                
                # Log the trade
                self.logger.log_trade(ticker, direction, entry_price, exit_price, pnl, exit_reason)
                
                # Reset position state
                self.bot_positions[ticker]['has_position'] = False
                self.bot_positions[ticker]['entry_price'] = None
                self.bot_positions[ticker]['entry_time'] = None
                self.bot_positions[ticker]['direction'] = None
                self.position_metadata[ticker]['entry_time'] = None
                
                # Clear stored entry (only if ObjectStore available)
                try:
                    self.object_store.delete(f"{ticker}_entry")
                except:
                    pass  # ObjectStore not available in backtest
                
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
            
        # Daily summary
        self.logger.daily_summary(self.time)
        
    def on_data(self, data):
        """Main data handler"""
        pass
        
    def setup_logging(self):
        """Initial logging"""
        self.debug("="*50)
        self.debug("CFD BREAKOUT STRATEGY")
        self.debug(f"Long offset: +{self.parameters['long_entry_offset']*100:.1f}%")
        self.debug(f"Short offset: -{self.parameters['short_entry_offset']*100:.1f}%")
        self.debug(f"TP: {self.parameters['tp_percentage']*100:.1f}%")
        self.debug(f"SL: {self.parameters['sl_percentage']*100:.1f}%")
        self.debug(f"Position size: ${self.parameters['position_size']}")
        self.debug(f"Tickers: {self.parameters['tickers']}")
        self.debug("="*50)