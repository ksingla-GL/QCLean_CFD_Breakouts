# region imports
from AlgorithmImports import *
# endregion

class OrderManager:
    """
    Handles order execution for OCO entries and bracket exits.
    Returns fill types to main.py for position tracking.
    """
    
    def __init__(self, algorithm):
        self.algo = algorithm
        self.oco_pairs = {}  # ticker -> {'long': order_id, 'short': order_id}
        self.position_brackets = {}  # ticker -> {'tp': order_id, 'sl': order_id, 'entry_price': price}
        self.order_info = {}  # order_id -> order details
        
    def round_to_tick(self, price):
        """
        Round price to IBKR minimum tick size.
        """
        if price >= 1.00:
            return round(price, 2)  # $0.01 tick
        else:
            return round(price, 4)  # $0.0001 tick
    
    def place_oco_orders(self, symbol, signals):
        """
        Place OCO entry orders. Returns True if successful.
        """
        ticker = str(symbol).split(' ')[0]
        
        # Check if OCO already exists
        if ticker in self.oco_pairs:
            self.algo.debug(f"OCO already exists for {ticker}")
            return False
            
        # Get position size
        position_value = signals.get('position_size', 10000)
        
        # Calculate and round prices
        long_stop = self.round_to_tick(signals['long_stop'])
        short_stop = self.round_to_tick(signals['short_stop'])
        
        # Add cushion for limit prices (0.1%)
        long_limit = self.round_to_tick(long_stop * 1.001)
        short_limit = self.round_to_tick(short_stop * 0.999)
        
        # Calculate quantities
        long_quantity = int(position_value / long_stop)
        short_quantity = int(position_value / short_stop)
        
        if long_quantity <= 0 or short_quantity <= 0:
            self.algo.debug(f"Position size too small for {ticker}")
            return False
            
        try:
            # Place long entry order
            long_order = self.algo.stop_limit_order(
                symbol,
                long_quantity,
                long_stop,
                long_limit
            )
            
            # Place short entry order
            short_order = self.algo.stop_limit_order(
                symbol,
                -short_quantity,
                short_stop,
                short_limit
            )
            
            # Track OCO pair
            self.oco_pairs[ticker] = {
                'long': long_order.order_id,
                'short': short_order.order_id,
                'tp_pct': signals['tp_percentage'],
                'sl_pct': signals['sl_percentage']
            }
            
            # Track order info
            self.order_info[long_order.order_id] = {
                'ticker': ticker,
                'type': 'oco_long',
                'quantity': long_quantity
            }
            
            self.order_info[short_order.order_id] = {
                'ticker': ticker,
                'type': 'oco_short',
                'quantity': short_quantity
            }
            
            self.algo.debug(f"OCO placed: Long {long_quantity}@${long_stop:.2f}, Short {short_quantity}@${short_stop:.2f}")
            return True
            
        except Exception as e:
            self.algo.debug(f"Error placing OCO for {ticker}: {str(e)}")
            return False
    
    def place_bracket_orders(self, symbol, entry_price, direction, quantity):
        """
        Place bracket orders (TP and SL) after entry fill.
        """
        ticker = str(symbol).split(' ')[0]
        
        # Get TP/SL percentages from stored OCO info
        if ticker not in self.oco_pairs:
            self.algo.debug(f"No OCO info for {ticker}")
            return
            
        tp_pct = self.oco_pairs[ticker]['tp_pct']
        sl_pct = self.oco_pairs[ticker]['sl_pct']
        
        if direction == 'long':
            # Long brackets
            tp_price = self.round_to_tick(entry_price * (1 + tp_pct))
            sl_stop = self.round_to_tick(entry_price * (1 - sl_pct))
            sl_limit = self.round_to_tick(sl_stop * 0.999)
            
            tp_order = self.algo.limit_order(symbol, -quantity, tp_price)
            sl_order = self.algo.stop_limit_order(symbol, -quantity, sl_stop, sl_limit)
            
        else:  # short
            # Short brackets
            tp_price = self.round_to_tick(entry_price * (1 - tp_pct))
            sl_stop = self.round_to_tick(entry_price * (1 + sl_pct))
            sl_limit = self.round_to_tick(sl_stop * 1.001)
            
            tp_order = self.algo.limit_order(symbol, quantity, tp_price)
            sl_order = self.algo.stop_limit_order(symbol, quantity, sl_stop, sl_limit)
            
        # Track brackets
        self.position_brackets[ticker] = {
            'tp': tp_order.order_id,
            'sl': sl_order.order_id,
            'entry_price': entry_price,
            'direction': direction
        }
        
        # Track order info
        self.order_info[tp_order.order_id] = {
            'ticker': ticker,
            'type': 'bracket_tp'
        }
        
        self.order_info[sl_order.order_id] = {
            'ticker': ticker,
            'type': 'bracket_sl'
        }
        
        self.algo.debug(f"Brackets placed: TP@${tp_price:.2f}, SL@${sl_stop:.2f}")
    
    def handle_order_event(self, order_event):
        """
        Process order events and return fill type for main.py.
        Returns: 'entry_long', 'entry_short', 'exit_tp', 'exit_sl', or None
        """
        order_id = order_event.order_id
        
        if order_id not in self.order_info:
            return None
            
        order_data = self.order_info[order_id]
        ticker = order_data['ticker']
        order_type = order_data['type']
        
        if order_event.status == OrderStatus.FILLED:
            
            if order_type == 'oco_long':
                # Long entry filled - cancel short OCO
                if ticker in self.oco_pairs:
                    short_id = self.oco_pairs[ticker]['short']
                    self.algo.transactions.cancel_order(short_id)
                    
                    # Place brackets
                    self.place_bracket_orders(
                        order_event.symbol,
                        order_event.fill_price,
                        'long',
                        order_data['quantity']
                    )
                    
                    # Cleanup OCO
                    del self.oco_pairs[ticker]
                    
                return 'entry_long'
                
            elif order_type == 'oco_short':
                # Short entry filled - cancel long OCO
                if ticker in self.oco_pairs:
                    long_id = self.oco_pairs[ticker]['long']
                    self.algo.transactions.cancel_order(long_id)
                    
                    # Place brackets
                    self.place_bracket_orders(
                        order_event.symbol,
                        order_event.fill_price,
                        'short',
                        order_data['quantity']
                    )
                    
                    # Cleanup OCO
                    del self.oco_pairs[ticker]
                    
                return 'entry_short'
                
            elif order_type == 'bracket_tp':
                # Take profit hit - cancel stop loss
                if ticker in self.position_brackets:
                    sl_id = self.position_brackets[ticker]['sl']
                    self.algo.transactions.cancel_order(sl_id)
                    del self.position_brackets[ticker]
                    
                return 'exit_tp'
                
            elif order_type == 'bracket_sl':
                # Stop loss hit - cancel take profit
                if ticker in self.position_brackets:
                    tp_id = self.position_brackets[ticker]['tp']
                    self.algo.transactions.cancel_order(tp_id)
                    del self.position_brackets[ticker]
                    
                return 'exit_sl'
                
        elif order_event.status == OrderStatus.CANCELED:
            # Clean up canceled orders
            if order_id in self.order_info:
                del self.order_info[order_id]
                
        return None
    
    def cancel_oco_orders(self, ticker):
        """Cancel OCO orders for a ticker."""
        if ticker in self.oco_pairs:
            oco = self.oco_pairs[ticker]
            self.algo.transactions.cancel_order(oco['long'])
            self.algo.transactions.cancel_order(oco['short'])
            del self.oco_pairs[ticker]
            self.algo.debug(f"Canceled OCO orders for {ticker}")
    
    def has_pending_oco(self, ticker):
        """Check if ticker has pending OCO orders."""
        return ticker in self.oco_pairs
    
    def cleanup_ticker(self, ticker):
        """Clean up all orders for a ticker (used when halting)."""
        # Cancel OCO if exists
        if ticker in self.oco_pairs:
            self.cancel_oco_orders(ticker)
            
        # Cancel brackets if exist
        if ticker in self.position_brackets:
            brackets = self.position_brackets[ticker]
            self.algo.transactions.cancel_order(brackets['tp'])
            self.algo.transactions.cancel_order(brackets['sl'])
            del self.position_brackets[ticker]
            
        # Clean up order info
        orders_to_remove = [oid for oid, info in self.order_info.items() if info['ticker'] == ticker]
        for oid in orders_to_remove:
            del self.order_info[oid]