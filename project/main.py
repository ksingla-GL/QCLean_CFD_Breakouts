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
        
        # Load parameters (M1 requirement)
        self.load_parameters()
        
        # Initialize components (M1 - separation of concerns)
        self.signal_generator = SignalGenerator(self.parameters)
        self.order_manager = OrderManager(self)
        self.logger = TradeLogger(self)
        
        # Trading state for M2
        self.daily_open_prices = {}
        self.bot_positions = {}  # Bot's expected state
        self.position_metadata = {}  # Store entry times for D+4
        self.processed_today = False
        self.reconciliation_halts = set()  # Safety feature per client feedback
        
        # Setup universe
        self.setup_universe()
        
        # Initial reconciliation (M2 - safe restart)
        self.reconcile_positions(is_startup=True)
        
        # Setup LEAN scheduling (M2 requirement)
        self.setup_scheduling()
        
        # Basic logging (M1)
        self.setup_logging()
        
    def load_parameters(self):
        """Load M1/M2 essential parameters from SetParameter"""
        self.parameters = {
            'long_entry_offset': float(self.get_parameter("long_entry_offset") or 0.02),
            'short_entry_offset': float(self.get_parameter("short_entry_offset") or 0.02),
            'tp_percentage': float(self.get_parameter("tp_percentage") or 0.05),
            'sl_percentage': float(self.get_parameter("sl_percentage") or 0.03),
            'timestop_days': int(self.get_parameter("timestop_days") or 4),  # D+4
            'tickers': self.get_parameter("tickers") or "AAPL,MSFT,GOOGL",
            'use_cfds': self.get_parameter("use_cfds") or "false"
        }
            
    def setup_universe(self):
        """Add tickers - supports both stocks and CFDs per client requirement"""
        self.tickers = [t.strip() for t in self.parameters['tickers'].split(",")]
        use_cfds = self.parameters['use_cfds'].lower() == "true"
        
        for ticker in self.tickers:
            # Add as CFD or equity based on parameter
            if use_cfds:
                try:
                    symbol = self.add_cfd(ticker, Resolution.MINUTE)
                except:
                    symbol = self.add_equity(ticker, Resolution.MINUTE)
                    self.debug(f"CFD unavailable for {ticker}, using equity")
            else:
                symbol = self.add_equity(ticker, Resolution.MINUTE)
            
            # Initialize tracking structures
            self.bot_positions[ticker] = {
                'expected_quantity': 0,  # What bot thinks position is
                'entry_price': None
            }
            
            self.position_metadata[ticker] = {
                'entry_time': None  # For D+4 calculation
            }
            
        self.debug(f"Universe: {len(self.tickers)} symbols (CFDs: {use_cfds})")
            
    def setup_scheduling(self):
        """M2: LEAN scheduling with holiday/early close handling"""
        if not self.tickers:
            return
            
        schedule_symbol = self.symbol(self.tickers[0])
        
        # Capture opening price at 9:30 ET (M2 requirement)
        self.schedule.on(
            self.date_rules.every_day(schedule_symbol),  # Auto handles holidays
            self.time_rules.after_market_open(schedule_symbol, 0),
            self.capture_market_open
        )
        
        # End of day
        self.schedule.on(
            self.date_rules.every_day(schedule_symbol),
            self.time_rules.before_market_close(schedule_symbol, 5),
            self.end_of_day_processing
        )
        
        self.debug("LEAN scheduling configured")
        
    def reconcile_positions(self, ticker=None, is_startup=False):
        """M2: Single reconciliation function for both startup and runtime
        Returns True if positions match, False if mismatch detected"""
        
        if is_startup:
            self.debug("="*50)
            self.debug("Startup reconciliation")
            
        # If specific ticker provided, just check that one
        tickers_to_check = [ticker] if ticker else self.tickers
        all_reconciled = True
        
        for t in tickers_to_check:
            # Skip already halted tickers (except on startup)
            if not is_startup and t in self.reconciliation_halts:
                all_reconciled = False
                continue
                
            symbol = self.symbol(t)
            broker_position = self.portfolio[symbol]
            broker_qty = broker_position.quantity if broker_position.invested else 0
            expected_qty = self.bot_positions[t]['expected_quantity']
            
            if is_startup:
                # Startup: sync bot state with broker reality
                if broker_qty != 0:
                    self.bot_positions[t]['expected_quantity'] = broker_qty
                    self.bot_positions[t]['entry_price'] = broker_position.average_price
                    
                    # Try to recover entry time from storage
                    stored_meta = self.object_store.read(f"{t}_entry")
                    if stored_meta:
                        meta = json.loads(stored_meta)
                        self.position_metadata[t]['entry_time'] = DateTime.parse(meta.get('time'))
                        self.debug(f"Found position: {t} qty={broker_qty} price=${broker_position.average_price:.2f}")
                    else:
                        self.debug(f"Warning: Position found but no entry time for {t}")
            else:
                # Runtime: check for manual intervention
                if abs(broker_qty - expected_qty) > 0.01:
                    self.debug(f"Mismatch {t}: expected {expected_qty}, broker has {broker_qty}")
                    self.debug(f"Halting {t} - manual override detected")
                    
                    # Halt and update
                    self.reconciliation_halts.add(t)
                    self.bot_positions[t]['expected_quantity'] = broker_qty
                    
                    # Cancel pending orders
                    self.transactions.cancel_open_orders(symbol)
                    all_reconciled = False
                    
        if is_startup:
            self.debug("Reconciliation complete")
            
        return all_reconciled
        
    def capture_market_open(self):
        """M2: Capture official opening price at 9:30 ET"""
        if self.processed_today:
            return
            
        self.debug("="*50)
        self.debug(f"Market open at {self.time}")
        
        # Check all positions for overnight manual intervention
        self.reconcile_positions(is_startup=False)
        
        self.daily_open_prices = {}
        
        for ticker in self.tickers:
            # Skip halted tickers
            if ticker in self.reconciliation_halts:
                self.debug(f"{ticker} halted")
                continue
                
            symbol = self.symbol(ticker)
            
            # Capture opening price
            if self.securities[symbol].open > 0:
                open_price = self.securities[symbol].open
                self.daily_open_prices[ticker] = open_price
                
                self.debug(f"{ticker} open: ${open_price:.2f}")
                
                # Check if position exists
                if self.portfolio[symbol].invested:
                    qty = self.portfolio[symbol].quantity
                    self.debug(f"  Existing position: {qty}")
                else:
                    # Generate signals (execution in M3)
                    signals = self.signal_generator.generate_entry_signals(ticker, open_price)
                    if signals:
                        self.debug(f"  Signals: long ${signals['long_stop']:.2f}, short ${signals['short_stop']:.2f}")
            else:
                self.debug(f"Warning: No price for {ticker}")
                
        self.processed_today = True
        
    def on_order_event(self, order_event):
        """Track fills to maintain bot state"""
        ticker = str(order_event.symbol).split(' ')[0]
        
        if order_event.status == OrderStatus.FILLED:
            # Check this specific ticker before updating
            if not self.reconcile_positions(ticker=ticker, is_startup=False):
                self.debug(f"Ignoring fill for halted ticker {ticker}")
                return
                
            # Update bot's expected position
            if order_event.direction == OrderDirection.BUY:
                self.bot_positions[ticker]['expected_quantity'] += order_event.filled_quantity
            else:
                self.bot_positions[ticker]['expected_quantity'] -= order_event.filled_quantity
                
            # If new position, store entry time
            if self.bot_positions[ticker]['expected_quantity'] != 0 and not self.position_metadata[ticker]['entry_time']:
                self.position_metadata[ticker]['entry_time'] = self.time
                # Persist for restart safety
                self.object_store.save(f"{ticker}_entry", json.dumps({'time': str(self.time)}))
                
            # If position closed, clear metadata
            if self.bot_positions[ticker]['expected_quantity'] == 0:
                self.position_metadata[ticker]['entry_time'] = None
                self.object_store.delete(f"{ticker}_entry")
                
        self.logger.log_order_event(order_event)
        
    def end_of_day_processing(self):
        """Reset daily flags"""
        self.processed_today = False
        if self.reconciliation_halts:
            self.debug(f"Halted tickers: {self.reconciliation_halts}")
        
    def on_data(self, data):
        """Main data handler - logic in scheduled events"""
        pass
        
    def setup_logging(self):
        """M1: Basic logging scaffold"""
        self.debug("="*50)
        self.debug("CFD breakout strategy initialized")
        self.debug(f"Long offset: +{self.parameters['long_entry_offset']*100:.1f}%")
        self.debug(f"Short offset: -{self.parameters['short_entry_offset']*100:.1f}%")
        self.debug(f"TP: {self.parameters['tp_percentage']*100:.1f}%")
        self.debug(f"SL: {self.parameters['sl_percentage']*100:.1f}%")
        self.debug(f"Time stop: D+{self.parameters['timestop_days']}")
        self.debug(f"Tickers: {self.parameters['tickers']}")
        self.debug("="*50)