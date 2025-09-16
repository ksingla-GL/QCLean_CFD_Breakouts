# region imports
from AlgorithmImports import *
# endregion
class SignalGenerator:
    """
    Handles signal generation logic separated from execution.
    This class determines WHAT to trade based on strategy rules.
    """
    
    def __init__(self, params):
        self.params = params
        self.long_offset = params['long_entry_offset']
        self.short_offset = params['short_entry_offset']
        self.tp_percentage = params['tp_percentage']
        self.sl_percentage = params['sl_percentage']
    
    def generate_entry_signals(self, ticker, open_price):
        """
        Generate entry signals based on opening price.
        Returns dict with long_stop and short_stop prices for OCO orders.
        """
        if open_price <= 0:
            return None
            
        signals = {
            'ticker': ticker,
            'open_price': open_price,
            'long_stop': round(open_price * (1 + self.long_offset), 2),
            'short_stop': round(open_price * (1 - self.short_offset), 2),
            'tp_percentage': self.tp_percentage,
            'sl_percentage': self.sl_percentage,
            'timestamp': None  # Will be set by algo
        }
        
        # Validate signals are reasonable
        if signals['long_stop'] <= open_price or signals['short_stop'] >= open_price:
            return None
            
        return signals
    
    def should_enter_position(self, ticker, existing_position, in_blackout):
        """
        Determine if we should enter a new position.
        Checks for existing positions and blackout periods.
        """
        if existing_position:
            return False, "Already has position"
        
        if in_blackout:
            return False, "In earnings blackout"
            
        return True, "Clear to trade"