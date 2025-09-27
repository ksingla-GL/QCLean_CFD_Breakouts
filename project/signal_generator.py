# region imports
from AlgorithmImports import *
# endregion

class SignalGenerator:
    """
    Generates entry signals based on opening price.
    Separated from execution logic.
    """
    
    def __init__(self, params):
        self.params = params
        self.long_offset = params['long_entry_offset']
        self.short_offset = params['short_entry_offset']
        self.tp_percentage = params['tp_percentage']
        self.sl_percentage = params['sl_percentage']
    
    def generate_entry_signals(self, ticker, open_price):
        """
        Generate OCO entry signals based on opening price.
        Returns dict with entry levels and parameters.
        """
        if open_price <= 0:
            return None
            
        # Calculate entry levels (raw, not rounded)
        long_stop = open_price * (1 + self.long_offset)
        short_stop = open_price * (1 - self.short_offset)
        
        # Validate signals
        if long_stop <= open_price or short_stop >= open_price:
            return None
            
        return {
            'ticker': ticker,
            'open_price': open_price,
            'long_stop': long_stop,  # Rounding happens in OrderManager
            'short_stop': short_stop,
            'tp_percentage': self.tp_percentage,
            'sl_percentage': self.sl_percentage
        }