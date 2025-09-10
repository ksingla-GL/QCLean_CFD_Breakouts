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
        Returns dict with long_stop and short_stop prices.
        Implementation will be completed in milestone 3.
        """
        # Structure in place for OCO order levels
        signals = {
            'long_stop': open_price * (1 + self.long_offset),
            'short_stop': open_price * (1 - self.short_offset),
            'tp_percentage': self.tp_percentage,
            'sl_percentage': self.sl_percentage
        }
        
        # Placeholder - actual signal validation logic in milestone 3
        return None  # Will return signals when implementation is complete
    
    def calculate_position_size(self, account_value, risk_percentage):
        """
        Calculate position size based on risk parameters.
        To be implemented in milestone 5.
        """
        pass