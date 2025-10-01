# region imports
from AlgorithmImports import *
# endregion

class TradeLogger:
    """
    Handles logging and trade recording.
    """
    
    def __init__(self, algorithm):
        self.algo = algorithm
        self.trades = []
        self.daily_pnl = 0
        
    def log_event(self, message, level="INFO"):
        """Log events with timestamp"""
        timestamp = self.algo.time.strftime("%Y-%m-%d %H:%M:%S")
        self.algo.debug(f"[{timestamp}] [{level}] {message}")
    
    def log_order_event(self, order_event):
        """Log order events using proper enum comparison"""
        # Only log important events to reduce noise
        if order_event.status == OrderStatus.FILLED:
            direction = "BUY" if order_event.direction == OrderDirection.BUY else "SELL"
            self.log_event(
                f"FILL: {order_event.symbol} {direction} "
                f"{abs(order_event.fill_quantity)} @ ${order_event.fill_price:.2f}",
                "INFO"
            )
        elif order_event.status == OrderStatus.CANCELED:
            # Silent cancellation (expected for OCO)
            pass
        elif order_event.status == OrderStatus.INVALID:
            self.log_event(f"Invalid order: {order_event.symbol}", "ERROR")
            
    def log_trade(self, ticker, side, entry, exit, pnl, exit_reason):
        """Log completed trade"""
        # Handle special cases
        if exit_reason == "ManualIntervention":
            trade = {
                'date': self.algo.time,
                'ticker': ticker,
                'side': 'OVERRIDE',
                'entry_price': 0,
                'exit_price': 0,
                'pnl': 0,
                'pnl_pct': 0,
                'exit_reason': 'ManualIntervention'
            }
        elif exit_reason == "OVERRIDE":  # Legacy compatibility
            trade = {
                'date': self.algo.time,
                'ticker': ticker,
                'side': 'OVERRIDE',
                'entry_price': 0,
                'exit_price': 0,
                'pnl': 0,
                'pnl_pct': 0,
                'exit_reason': 'ManualIntervention'
            }
        else:
            # Normal trade
            pnl_pct = 0
            if entry > 0:
                if side == 'long':
                    pnl_pct = ((exit - entry) / entry * 100)
                else:  # short
                    pnl_pct = ((entry - exit) / entry * 100)
                    
            trade = {
                'date': self.algo.time,
                'ticker': ticker,
                'side': side,
                'entry_price': entry,
                'exit_price': exit,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'exit_reason': exit_reason
            }
            
        self.trades.append(trade)
        
        # Only add to daily PnL for real trades
        if exit_reason not in ["ManualIntervention", "OVERRIDE"]:
            self.daily_pnl += pnl
            
            self.log_event(
                f"TRADE: {ticker} {side} entry=${entry:.2f} exit=${exit:.2f} "
                f"pnl=${pnl:.2f} ({trade['pnl_pct']:+.2f}%) reason={exit_reason}",
                "INFO"
            )
        else:
            self.log_event(
                f"OVERRIDE: {ticker} position manually intervened - halting ticker",
                "WARNING"
            )
    
    def daily_summary(self, date):
        """Log daily summary"""
        if self.trades:
            today_trades = [t for t in self.trades if t['date'].date() == date.date() and t['exit_reason'] not in ["ManualIntervention", "OVERRIDE"]]
            if today_trades:
                total_pnl = sum(t['pnl'] for t in today_trades)
                win_count = sum(1 for t in today_trades if t['pnl'] > 0)
                loss_count = sum(1 for t in today_trades if t['pnl'] <= 0)
                
                # Count exit reasons
                exit_reasons = {}
                for t in today_trades:
                    reason = t['exit_reason']
                    exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
                
                reason_summary = ", ".join([f"{reason}: {count}" for reason, count in exit_reasons.items()])
                
                self.log_event(
                    f"Daily Summary: {len(today_trades)} trades, "
                    f"W/L: {win_count}/{loss_count}, PnL: ${total_pnl:.2f}, "
                    f"Exits: {reason_summary}",
                    "INFO"
                )
                
            # Log any overrides
            overrides = [t for t in self.trades if t['date'].date() == date.date() and t['exit_reason'] in ["ManualIntervention", "OVERRIDE"]]
            if overrides:
                override_tickers = [t['ticker'] for t in overrides]
                self.log_event(
                    f"Manual interventions detected: {', '.join(override_tickers)}",
                    "WARNING"
                )