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
        self.position_brackets = {}  # ticker -> {'tp': order_id, 'sl': order_id, 'entry_price': price, 'sl_adjusted': bool}
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
        OCO entries use stop-limit with cushion to avoid chasing.
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
        
        # Add cushion for limit prices (0.1% - this is OK for entries)
        long_limit = self.round_to_tick(long_stop * 1.001)
        short_limit = self.round_to_tick(short_stop * 0.999)
        
        # Calculate quantities
        long_quantity = int(position_value / long_stop)
        short_quantity = int(position_value / short_stop)
        
        if long_quantity <= 0 or short_quantity <= 0:
            self.algo.debug(f"Position size too small for {ticker}")
            return False
            
        try:
            # Place long entry order - stop-limit is OK for entries
            long_order = self.algo.stop_limit_order(
                symbol,
                long_quantity,
                long_stop,
                long_limit
            )
            
            # Place short entry order - stop-limit is OK for entries
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
        TP uses limit order (want specific price).
        SL uses STOP-MARKET order (exit immediately when triggered).
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
            
            # TP as limit order (want specific price)
            tp_order = self.algo.limit_order(symbol, -quantity, tp_price)
            
            # SL as STOP-MARKET order (exit immediately when hit - no limit!)
            sl_order = self.algo.stop_market_order(symbol, -quantity, sl_stop)
            
        else:  # short
            # Short brackets
            tp_price = self.round_to_tick(entry_price * (1 - tp_pct))
            sl_stop = self.round_to_tick(entry_price * (1 + sl_pct))
            
            # TP as limit order (want specific price)
            tp_order = self.algo.limit_order(symbol, quantity, tp_price)
            
            # SL as STOP-MARKET order (exit immediately when hit - no limit!)
            sl_order = self.algo.stop_market_order(symbol, quantity, sl_stop)
            
        # Track brackets
        self.position_brackets[ticker] = {
            'tp': tp_order.order_id,
            'sl': sl_order.order_id,
            'entry_price': entry_price,
            'direction': direction,
            'sl_adjusted': False  # Track if SL has been adjusted to breakeven
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
        
        self.algo.debug(f"Brackets placed: TP@${tp_price:.2f}, SL@${sl_stop:.2f} (market)")
    
    def adjust_sl_to_breakeven(self, symbol, ticker, entry_price, direction):
        """
        Adjust stop-loss to breakeven + offset when capture point is hit.
        Uses STOP-MARKET order for immediate exit when triggered.
        Returns True if successful.
        """
        if ticker not in self.position_brackets:
            self.algo.debug(f"No brackets found for {ticker}")
            return False
            
        brackets = self.position_brackets[ticker]
        
        # Check if already adjusted
        if brackets.get('sl_adjusted', False):
            self.algo.debug(f"{ticker} SL already adjusted")
            return False
            
        old_sl_id = brackets['sl']
        
        # Get the breakeven offset from parameters
        breakeven_offset = self.algo.parameters['breakeven_offset']
        
        # Calculate new SL at breakeven + offset
        if direction == 'long':
            new_sl_stop = self.round_to_tick(entry_price * (1 + breakeven_offset))
            
            # Get current position quantity
            quantity = abs(self.algo.portfolio[symbol].quantity)
            if quantity <= 0:
                self.algo.debug(f"No position found for {ticker}")
                return False
                
            # Cancel old SL
            self.algo.transactions.cancel_order(old_sl_id)
            
            # Place new SL as STOP-MARKET (exit immediately when hit)
            new_sl = self.algo.stop_market_order(symbol, -quantity, new_sl_stop)
            
        else:  # short
            new_sl_stop = self.round_to_tick(entry_price * (1 - breakeven_offset))
            
            # Get current position quantity
            quantity = abs(self.algo.portfolio[symbol].quantity)
            if quantity <= 0:
                self.algo.debug(f"No position found for {ticker}")
                return False
                
            # Cancel old SL
            self.algo.transactions.cancel_order(old_sl_id)
            
            # Place new SL as STOP-MARKET (exit immediately when hit)
            new_sl = self.algo.stop_market_order(symbol, quantity, new_sl_stop)
        
        # Update tracking
        brackets['sl'] = new_sl.order_id
        brackets['sl_adjusted'] = True
        
        # Track the new order info
        self.order_info[new_sl.order_id] = {
            'ticker': ticker,
            'type': 'bracket_sl_adjusted'
        }
        
        # Clean up old order info
        if old_sl_id in self.order_info:
            del self.order_info[old_sl_id]
        
        self.algo.debug(f"{ticker} SL adjusted to breakeven+{breakeven_offset*100:.1f}%: ${new_sl_stop:.2f} (market)")
        return True
    
    def handle_order_event(self, order_event):
        """
        Process order events and return fill type for main.py.
        Returns: 'entry_long', 'entry_short', 'exit_tp', 'exit_sl', 'exit_sl_adjusted', or None
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
                    try:
                        self.algo.transactions.cancel_order(short_id)
                    except:
                        pass  # Already canceled
                    
                    # Place brackets
                    self.place_bracket_orders(
                        order_event.symbol,
                        order_event.fill_price,
                        'long',
                        order_data['quantity']
                    )
                    
                    # Cleanup OCO - check before deleting
                    if ticker in self.oco_pairs:
                        del self.oco_pairs[ticker]
                    
                return 'entry_long'
                
            elif order_type == 'oco_short':
                # Short entry filled - cancel long OCO
                if ticker in self.oco_pairs:
                    long_id = self.oco_pairs[ticker]['long']
                    try:
                        self.algo.transactions.cancel_order(long_id)
                    except:
                        pass  # Already canceled
                    
                    # Place brackets
                    self.place_bracket_orders(
                        order_event.symbol,
                        order_event.fill_price,
                        'short',
                        order_data['quantity']
                    )
                    
                    # Cleanup OCO - check before deleting
                    if ticker in self.oco_pairs:
                        del self.oco_pairs[ticker]
                    
                return 'entry_short'
                
            elif order_type == 'bracket_tp':
                # Take profit hit - cancel stop loss
                if ticker in self.position_brackets:
                    sl_id = self.position_brackets[ticker]['sl']
                    try:
                        self.algo.transactions.cancel_order(sl_id)
                    except:
                        pass  # Already canceled
                    del self.position_brackets[ticker]
                    
                return 'exit_tp'
                
            elif order_type == 'bracket_sl':
                # Original stop loss hit - cancel take profit
                if ticker in self.position_brackets:
                    tp_id = self.position_brackets[ticker]['tp']
                    try:
                        self.algo.transactions.cancel_order(tp_id)
                    except:
                        pass  # Already canceled
                    del self.position_brackets[ticker]
                    
                return 'exit_sl'
                
            elif order_type == 'bracket_sl_adjusted':
                # Adjusted stop loss hit (breakeven) - cancel take profit
                if ticker in self.position_brackets:
                    tp_id = self.position_brackets[ticker]['tp']
                    try:
                        self.algo.transactions.cancel_order(tp_id)
                    except:
                        pass  # Already canceled
                    del self.position_brackets[ticker]
                    
                return 'exit_sl_adjusted'
                
        elif order_event.status == OrderStatus.CANCELED:
            # Clean up canceled orders
            if order_id in self.order_info:
                del self.order_info[order_id]
                
        return None
    
    def cancel_oco_orders(self, ticker):
        """Cancel OCO orders for a ticker."""
        if ticker in self.oco_pairs:
            oco = self.oco_pairs[ticker]
            try:
                self.algo.transactions.cancel_order(oco['long'])
            except:
                pass  # Order might already be canceled
            try:
                self.algo.transactions.cancel_order(oco['short'])
            except:
                pass  # Order might already be canceled
            del self.oco_pairs[ticker]
            self.algo.debug(f"Canceled OCO orders for {ticker}")
    
    def has_pending_oco(self, ticker):
        """Check if ticker has pending OCO orders."""
        return ticker in self.oco_pairs
    
    def cleanup_ticker(self, ticker):
        """Clean up all orders for a ticker (used when halting or time-stop)."""
        # Cancel OCO if exists
        if ticker in self.oco_pairs:
            self.cancel_oco_orders(ticker)
            
        # Cancel brackets if exist
        if ticker in self.position_brackets:
            brackets = self.position_brackets[ticker]
            try:
                self.algo.transactions.cancel_order(brackets['tp'])
            except:
                pass  # Order might already be canceled
            try:
                self.algo.transactions.cancel_order(brackets['sl'])
            except:
                pass  # Order might already be canceled
            del self.position_brackets[ticker]
            
        # Clean up order info
        orders_to_remove = [oid for oid, info in self.order_info.items() if info['ticker'] == ticker]
        for oid in orders_to_remove:
            del self.order_info[oid]