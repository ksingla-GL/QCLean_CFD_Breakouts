from AlgorithmImports import *
from signal_generator import SignalGenerator
from order_manager import OrderManager
from trade_logger import TradeLogger

class CFDBreakoutStrategy(QCAlgorithm):
    
    def initialize(self):
        # Basic setup
        self.set_start_date(2024, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        
        # Load parameters from config
        self.load_parameters()
        
        # Initialize components (separation of concerns)
        self.signal_generator = SignalGenerator(self.parameters)
        self.order_manager = OrderManager(self)
        self.logger = TradeLogger(self)
        
        # Trading state
        self.daily_positions = {}
        self.open_prices = {}
        
        # Add symbols to universe
        self.setup_universe()
        
        # Initialize logging
        self.setup_logging()
        
    def load_parameters(self):
        """Load all trading parameters - externalized for easy modification"""
        self.parameters = {
            # Entry parameters (from Trade Setup doc)
            'long_entry_offset': float(self.get_parameter("long_entry_offset") or 0.02),
            'short_entry_offset': float(self.get_parameter("short_entry_offset") or 0.02),
            
            # Exit parameters (from Trade Setup doc)
            'tp_percentage': float(self.get_parameter("tp_percentage") or 0.05),
            'sl_percentage': float(self.get_parameter("sl_percentage") or 0.03),
            
            # Universe
            'tickers': self.get_parameter("tickers") or "AAPL,MSFT,GOOGL"
        }
        
        # Note: Additional risk and position sizing parameters 
        # will be added in relevant milestones
        
    def setup_universe(self):
        """Add tickers to trading universe"""
        self.tickers = [t.strip() for t in self.parameters['tickers'].split(",")]
        
        for ticker in self.tickers:
            # Add as CFD if available, otherwise as regular equity
            # Note: IBKR CFD implementation will be handled in OrderManager
            self.add_equity(ticker, Resolution.MINUTE)
            
        self.debug(f"Universe initialized with {len(self.tickers)} symbols")
            
    def setup_logging(self):
        """Initialize logging system"""
        self.debug("="*50)
        self.debug("CFD Breakout Strategy Initialized")
        self.debug("="*50)
        self.debug(f"Trading Parameters:")
        self.debug(f"  Long Entry: +{self.parameters['long_entry_offset']*100:.1f}%")
        self.debug(f"  Short Entry: -{self.parameters['short_entry_offset']*100:.1f}%")
        self.debug(f"  Take Profit: {self.parameters['tp_percentage']*100:.1f}%")
        self.debug(f"  Stop Loss: {self.parameters['sl_percentage']*100:.1f}%")
        self.debug(f"  Tickers: {self.parameters['tickers']}")
        self.debug("="*50)
        
    def on_data(self, data):
        """Main strategy logic - delegated to components"""
        
        # Check if market just opened (9:30 ET)
        if self.is_market_open(self.time):
            self.process_market_open(data)
            
        # Placeholder for position management (future milestones)
        # This demonstrates the separation of concerns:
        # - SignalGenerator decides what to trade
        # - OrderManager handles how to place orders
        # - Logger records all activity
        
    def is_market_open(self, current_time):
        """Check if it's market open time (9:30 ET)"""
        # Simple check for now - will be enhanced in milestone 2 with proper scheduling
        return (current_time.hour == 9 and current_time.minute == 30)
    
    def process_market_open(self, data):
        """Process market open - get signals and place orders"""
        self.debug(f"Market open processing at {self.time}")
        
        for ticker in self.tickers:
            symbol = self.symbol(ticker)
            
            if symbol in data and data[symbol] is not None:
                open_price = data[symbol].open
                self.open_prices[ticker] = open_price
                
                # Generate signals (what to trade)
                signals = self.signal_generator.generate_entry_signals(ticker, open_price)
                
                # Place orders (how to trade) - placeholder for now
                if signals:
                    self.logger.log_event(f"Signals generated for {ticker}: {signals}")
                    # Orders will be placed in milestone 3
                    # self.order_manager.place_oco_orders(symbol, signals)
                    
    def on_order_event(self, order_event):
        """Handle order events - delegated to OrderManager"""
        self.order_manager.handle_order_event(order_event)
        self.logger.log_order_event(order_event)
        
    def on_end_of_day(self, symbol):
        """End of day cleanup and reporting"""
        self.logger.daily_summary(self.time)