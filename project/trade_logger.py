# region imports
from AlgorithmImports import *
# endregion
import csv
from datetime import datetime

class TradeLogger:
    """
    Handles all logging and trade recording.
    Provides structured logging for backtests and live trading.
    """
    
    def __init__(self, algorithm):
        self.algo = algorithm
        self.trades = []
        self.daily_stats = {}
        
    def log_event(self, message, level="INFO"):
        """Log general events with timestamp and level"""
        timestamp = self.algo.time.strftime("%Y-%m-%d %H:%M:%S")
        self.algo.debug(f"[{timestamp}] [{level}] {message}")
    
    def log_order_event(self, order_event):
        """
        Log order events for audit trail.
        Full implementation in milestone 5.
        """
        # Structure for order event logging
        event_data = {
            'time': self.algo.time,
            'symbol': order_event.symbol,
            'order_id': order_event.order_id,
            'status': order_event.status,
            'fill_price': order_event.fill_price if order_event.status == "Filled" else None,
            'fill_quantity': order_event.fill_quantity if order_event.status == "Filled" else None
        }
        
        self.log_event(f"Order Event: {event_data}")
    
    def log_trade(self, ticker, side, entry, exit, pnl, exit_reason):
        """
        Log completed trades for CSV output.
        To be implemented in milestone 5.
        """
        trade = {
            'date': self.algo.time,
            'ticker': ticker,
            'side': side,
            'entry_price': entry,
            'exit_price': exit,
            'pnl': pnl,
            'exit_reason': exit_reason
        }
        self.trades.append(trade)
        
    def daily_summary(self, date):
        """
        Generate daily P&L summary.
        To be implemented in milestone 5.
        """
        # Will calculate and log daily statistics
        pass
    
    def export_to_csv(self, filename="trades.csv"):
        """
        Export trade log to CSV file.
        To be implemented in milestone 5.
        """
        # Will write self.trades to CSV
        pass