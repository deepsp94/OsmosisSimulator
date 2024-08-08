from math import log, floor
from position import Position
from tick import Tick
from typing import Tuple


class Pair:
    """
    A class to represent a Uniswap v3 pool of two tokens

    ...

    Attributes
    ----------
    token_x : str
        A hexadecimal string representing the first token
    token_y : str
        A hexadecimal string representing the second token
    liquidity : int
        The current global liquidity of the pair
    init_sqrt_price : float
        The initial square root price of the pair
    fee_tier : float
        The fee tier of the pair
    tick_spacing : float
        The tick spacing of the pair
    curr_price : float
        The current price of the pair
    positions : List[Position]
        A list of positions for the pair
    ticks : Dict[int, Tick]
        A dictionary mapping tick indexes to their respective `Tick` objects
    """

    def __init__(
            self,
            token_x: str,
            token_y: str,
            init_sqrt_price: float,
            fee_tier: float,
            tick_spacing: float
    ):
        """
        Constructs all the necessary attributes for the Pair object.

        Parameters
        ----------
        token_x: str
            A hexadecimal string representing the first token
        token_y : str
            A hexadecimal string representing the second token
        init_sqrt_price : float
            The initial square root price of the pair
        fee_tier : float
            The fee tier of the pair
        tick_spacing : float
            The tick spacing of the pair
        """

        self.token_x = token_x
        self.token_y = token_y
        self.liquidity = 0
        self.init_sqrt_price = init_sqrt_price
        self.fee_tier = fee_tier
        self.std_increment_distance = int(9e6)  # Refer Osmosis docs
        self.exp_at_price_one = -6
        self.tick_spacing = tick_spacing
        self.curr_sqrt_price = init_sqrt_price
        self.curr_tick_idx = self.sqrt_price_to_tick(self.curr_sqrt_price)
        self.positions = {}
        self.ticks = {}
        self.all_ticks = {}  # Keep track of all ticks ever initialized
        # Track global fees per liquidity (as explained in WP)
        self.fee_growth_global_x = 0
        self.fee_growth_global_y = 0
        # Track token balances
        self.token_x_balance = 0
        self.token_y_balance = 0

    def add_liquidity(
            self,
            owner: str,
            liquidity: int,
            lower_tick_idx: int,
            upper_tick_idx: int
    ) -> Position:
        """
        Adds liquidity to the pair within a certain range of ticks.

        Parameters
        ----------
        owner : str
            The owner (address) of the LP position
        liquidity : int
            The amount of liquidity to be added.
        lower_tick_idx : int
            The lower bound of the range of ticks.
        upper_tick_idx : int
            The upper bound of the range of ticks.

        Returns
        -------
        Position
            The position where the liquidity was added.
        """
        # Update global liquidity
        if (self.curr_tick_idx >= lower_tick_idx
                and self.curr_tick_idx < upper_tick_idx):
            self.liquidity += liquidity
        # Create or update position
        key = (owner, lower_tick_idx, upper_tick_idx)
        if (key in self.positions
                and lower_tick_idx in self.ticks
                and upper_tick_idx in self.ticks):
            self.collect_fees(self.positions[key])
            self.positions[key].liquidity += liquidity
            position = self.positions[key]

            self.ticks[lower_tick_idx].liquidity_net += liquidity
            self.ticks[lower_tick_idx].liquidity_gross += liquidity
            self.ticks[upper_tick_idx].liquidity_net -= liquidity
            self.ticks[upper_tick_idx].liquidity_gross += liquidity

        else:
            if lower_tick_idx not in self.ticks:
                (lower_tick_fee_growth_outside_x,
                 lower_tick_fee_growth_outside_y) =\
                    self.fee_growth_outside(lower_tick_idx)
                self.ticks[lower_tick_idx] = Tick(
                    lower_tick_idx,
                    liquidity_net=liquidity,
                    liquidity_gross=liquidity,
                    fee_growth_outside_x=lower_tick_fee_growth_outside_x,
                    fee_growth_outside_y=lower_tick_fee_growth_outside_y
                )
                self.all_ticks[lower_tick_idx] = self.ticks[lower_tick_idx]
            else:
                self.ticks[lower_tick_idx].liquidity_net += liquidity
                self.ticks[lower_tick_idx].liquidity_gross += liquidity

            if upper_tick_idx not in self.ticks:
                (upper_tick_fee_growth_outside_x,
                 upper_tick_fee_growth_outside_y) =\
                    self.fee_growth_outside(upper_tick_idx)
                self.ticks[upper_tick_idx] = Tick(
                    upper_tick_idx,
                    liquidity_net=-liquidity,
                    liquidity_gross=liquidity,
                    fee_growth_outside_x=upper_tick_fee_growth_outside_x,
                    fee_growth_outside_y=upper_tick_fee_growth_outside_y
                )
                self.all_ticks[upper_tick_idx] = self.ticks[upper_tick_idx]
            else:
                self.ticks[upper_tick_idx].liquidity_net -= liquidity
                self.ticks[upper_tick_idx].liquidity_gross += liquidity

            if key in self.positions:
                self.collect_fees(self.positions[key])
                self.positions[key].liquidity += liquidity
                position = self.positions[key]
            else:
                # Get fee within range
                fee_within_range_x, fee_within_range_y = self.fee_within_range(
                    self.ticks[lower_tick_idx], self.ticks[upper_tick_idx]
                )
                position = Position(
                    owner,
                    liquidity,
                    self.ticks[lower_tick_idx],
                    self.ticks[upper_tick_idx],
                    fee_within_range_x, fee_within_range_y
                )
            self.positions[key] = position

        self.sort_tick_map()
        delta_x, delta_y =\
            self.liquidity_to_tokens(liquidity, lower_tick_idx, upper_tick_idx)
        self.token_x_balance += delta_x
        self.token_y_balance += delta_y
        return position

    def remove_liquidity(self, position: Position, liquidity: int) -> None:
        """
        Removes liquidity from a specific position in the pair.

        Parameters
        ----------
        position : Position
            The position from which the liquidity is to be removed.
        liquidity : int
            The amount of liquidity to be removed.
        """
        # Remove from active liquidity if within range
        if (self.curr_tick_idx >= position.lower_tick.idx
                and self.curr_tick_idx < position.upper_tick.idx):
            self.liquidity -= liquidity

        # If liquidity is fully removed and the position has no fees to collect
        # then delete the position. Else just update the liquidity amount.
        fees_x, fees_y = self.get_fees(position)
        if (position.liquidity == liquidity and fees_x == 0 and fees_y == 0):
            del self.positions[
                (position.owner,
                 position.lower_tick.idx,
                 position.upper_tick.idx)
            ]
        else:
            self.collect_fees(position)
            position.liquidity -= liquidity

        self.ticks[position.lower_tick.idx].liquidity_net -= liquidity
        self.ticks[position.lower_tick.idx].liquidity_gross -= liquidity
        self.update_tick_map(position.lower_tick.idx)

        self.ticks[position.upper_tick.idx].liquidity_net += liquidity
        self.ticks[position.upper_tick.idx].liquidity_gross -= liquidity
        self.update_tick_map(position.upper_tick.idx)
        delta_x, delta_y =\
            self.liquidity_to_tokens(liquidity, position.lower_tick.idx,
                                     position.upper_tick.idx)
        self.token_x_balance -= delta_x
        self.token_y_balance -= delta_y

    def sort_tick_map(self) -> None:
        """
        Sorts the tick map by tick index.
        """
        self.ticks = dict(sorted(self.ticks.items()))

    def liquidity_to_tokens(
            self,
            liquidity: str,
            lower_tick_idx: int,
            upper_tick_idx: int,
            sqrt_price: float = None
    ) -> int:
        """
        Calculates the amount of tokens that are equivalent to liquidity within
        a given range.

        Parameters
        ----------
        liquidity : int
            The amount of liquidity.
        lower_tick_idx : int
            The lower bound of the range of ticks.
        upper_tick_idx : int
            The upper bound of the range of ticks.
        sqrt_price : float
            The sqrt price at which the token amounts are to be calculated.

        Returns
        -------
        int
            The amount of both tokens that correspond to the given liquidity.
        """
        # p_b, p_a, p_c are square root prices
        p_b, _ = self.tick_to_sqrt_price(upper_tick_idx)
        p_a, _ = self.tick_to_sqrt_price(lower_tick_idx)
        if sqrt_price is None:
            p_c = self.curr_sqrt_price
        else:
            p_c = sqrt_price
        delta_x = liquidity * (p_b - p_c)/(p_b * p_c)
        delta_y = liquidity * (p_c - p_a)
        return max(delta_x, 0), max(delta_y, 0)

    def update_tick_map(self, tick_idx: int) -> None:
        """
        Updates the tick map after a liquidity removal.

        Parameters
        ----------
        tick_idx : int
            The tick index to be updated.
        """
        if self.ticks[tick_idx].liquidity_gross == 0:
            del self.ticks[tick_idx]
        self.sort_tick_map()

    def find_next_tick(self, tick_idx: int, higher: bool) -> int:
        """
        Finds the next, higher or lower, tick in the tick map.

        Parameters
        ----------
        tick_idx : int
            The tick index to be updated.
        higher : bool
            Whether to find the next higher or lower tick.

        Returns
        -------
        int
            The next tick index.
        """
        keys = list(self.ticks.keys())
        found = 0
        for key in keys:
            if key < tick_idx and not higher:
                next_tick = key
                found = 1
            elif key == tick_idx:
                position = keys.index(tick_idx)
                if higher:
                    next_tick = keys[position + 1]
                    found = 1
                    break
                if not higher:
                    next_tick = keys[position - 1]
                    found = 1
                    break
            elif key > tick_idx and higher:
                next_tick = key
                found = 1
                break

        if found == 0:
            next_tick = None
        return next_tick

    def fee_growth_outside(self, tick_idx) -> Tuple[int, int]:
        """
        Returns the fee growth outside the given tick.

        Returns
        -------
        Tuple[int, int]
            The fee growth outside the tick, in token x and token y.
        """
        if tick_idx not in self.ticks:
            if self.curr_tick_idx >= tick_idx:
                return (self.fee_growth_global_x, self.fee_growth_global_y)
            else:
                return (0, 0)
        else:
            return (
                self.fee_growth_global_x
                - self.ticks[tick_idx].fee_growth_outside_x,
                self.fee_growth_global_y
                - self.ticks[tick_idx].fee_growth_outside_y
            )

    def fee_within_range(
            self,
            lower_tick: Tick,
            upper_tick: Tick
    ) -> Tuple[int, int]:
        """
        Returns the fee within a certain range of ticks.

        Parameters
        ----------
        lower_tick : Tick
            The lower bound of the range of ticks.
        upper_tick : Tick
            The upper bound of the range of ticks.

        Returns
        -------
        Tuple[int, int]
            The fee within the range, in token x and token y.
        """
        if self.curr_tick_idx >= lower_tick.idx:
            fee_below_lower = (
                lower_tick.fee_growth_outside_x,
                lower_tick.fee_growth_outside_y
            )
        else:
            fee_below_lower = (
                self.fee_growth_global_x - lower_tick.fee_growth_outside_x,
                self.fee_growth_global_y - lower_tick.fee_growth_outside_y
            )

        if self.curr_tick_idx >= upper_tick.idx:
            fee_above_upper = (
                self.fee_growth_global_x - upper_tick.fee_growth_outside_x,
                self.fee_growth_global_y - upper_tick.fee_growth_outside_y
            )
        else:
            fee_above_upper = (
                upper_tick.fee_growth_outside_x,
                upper_tick.fee_growth_outside_y
            )

        fee_within_range_x =\
            self.fee_growth_global_x - fee_above_upper[0] - fee_below_lower[0]
        fee_within_range_y =\
            self.fee_growth_global_y - fee_above_upper[1] - fee_below_lower[1]

        return fee_within_range_x, fee_within_range_y

    def get_fees(self, position: Position) -> Tuple[int, int]:
        """
        Returns the fees held by a position.

        Parameters
        ----------
        position : Position
            A Position object.

        Returns
        -------
        Tuple[int, int]
            The fees held, in token x and token y, by the given position.
        """
        # Get fees accumulated within range
        fee_within_range_x, fee_within_range_y = self.fee_within_range(
            self.all_ticks[position.lower_tick.idx],
            self.all_ticks[position.upper_tick.idx]
        )
        # Sub fees this position has already collected or isn't entitled to
        fees_x = fee_within_range_x - position.fee_growth_inside_x
        fees_x = fees_x * position.liquidity
        fees_y = fee_within_range_y - position.fee_growth_inside_y
        fees_y = fees_y * position.liquidity

        return fees_x, fees_y

    def collect_fees(self, position: Position) -> Tuple[float, float]:
        """
        Collects fees from a position.

        Parameters
        ----------
        position : Position
            The position from which fees are collected.

        Returns
        -------
        Tuple[float, float]
            The fees collected, in token x and token y.
        """
        # Get fees accumulated within range
        fees_x, fees_y = self.get_fees(position)

        # Update fee growth in position object
        fee_within_range_x, fee_within_range_y = self.fee_within_range(
            self.all_ticks[position.lower_tick.idx],
            self.all_ticks[position.upper_tick.idx]
        )

        position.fee_growth_inside_x = fee_within_range_x
        position.fee_growth_inside_y = fee_within_range_y

        position.fees_x += fees_x
        position.fees_y += fees_y

        return fees_x, fees_y

    def withdraw_fees(self, position: Position) -> Tuple[float, float]:
        """
        Withdraws fees from a position.

        Parameters
        ----------
        position : Position
            The position from which fees are withdrawn.

        Returns
        -------
        Tuple[float, float]
            The fees withdrawn, in token x and token y.
        """
        self.collect_fees(position)
        fees_x = position.fees_x
        fees_y = position.fees_y
        position.fees_x = 0
        position.fees_y = 0
        if (position.liquidity == 0):
            del self.positions[
                (position.owner,
                 position.lower_tick.idx,
                 position.upper_tick.idx)
            ]
        self.token_x_balance -= fees_x
        self.token_y_balance -= fees_y
        return fees_x, fees_y

    def tick_by_tick_spacing(self, precise_tick: float) -> int:
        """
        Rounds down the precise tick to the nearest tick that is a multiple
        of the tick spacing.

        Parameters
        ----------
        precise_tick : float
            The precise tick to be rounded down.

        Returns
        -------
        int
            The corresponding tick, as per the pool's tick spacing.
        """
        tick_step = int(precise_tick/self.tick_spacing)
        if precise_tick >= 0:
            tick = tick_step * self.tick_spacing
        else:
            if tick_step % 1 != 0:
                tick = (tick_step - 1) * self.tick_spacing
            else:
                tick = tick_step * self.tick_spacing
        return tick

    def tick_to_sqrt_price(self, tick: int) -> Tuple[float, float]:
        curr_increment_lvl = int(abs(tick/self.std_increment_distance))
        if tick > 0:
            exp_at_curr_tick = self.exp_at_price_one + curr_increment_lvl
            curr_additive_increment = 10 ** (exp_at_curr_tick)
            num_additive_ticks =\
                tick - (curr_increment_lvl * self.std_increment_distance)
            price = ((10 ** curr_increment_lvl)
                     + (num_additive_ticks * curr_additive_increment))
        else:
            exp_at_curr_tick = self.exp_at_price_one - (curr_increment_lvl + 1)
            curr_additive_increment = 10 ** (exp_at_curr_tick)
            num_additive_ticks =\
                -tick - (curr_increment_lvl * self.std_increment_distance)
            price = ((10 ** -curr_increment_lvl)
                     - (num_additive_ticks * curr_additive_increment))
        return price**(1/2), (price + curr_additive_increment)**(1/2)

    def sqrt_price_to_tick(self, sqrt_price: float) -> Tuple[int, int]:
        price = sqrt_price**2
        if price == 1:
            tick = 0
        elif price > 1:
            price_levels = [10**i for i in range(int(50))]  # Adjust range as needed
            for i, pl in enumerate(price_levels):
                if price > pl and price <= price_levels[i+1]:
                    price_level = pl
                    price_level_index = i
                    break
            exp_at_curr_tick = int(price_level_index - 6)
            curr_additive_increment = 10 ** (exp_at_curr_tick)
            tick_level = price_level_index * self.std_increment_distance
            additive_ticks = round((price - price_level)
                                   / curr_additive_increment)
            tick = tick_level + additive_ticks
        else:
            price_levels = [10**-i for i in range(int(50))]  # Adjust range as needed
            for i, pl in enumerate(price_levels):
                if price < pl and price >= price_levels[i+1]:
                    price_level = pl
                    price_level_index = i
                    break
            exp_at_curr_tick = -1 * int(price_level_index + 7)
            curr_additive_increment = 10 ** (exp_at_curr_tick)
            tick_level = -price_level_index * self.std_increment_distance
            additive_ticks = round((price_level - price)
                                   / curr_additive_increment)
            tick = tick_level - additive_ticks
        return tick

    def deduct_fees(self, amount_in: float) -> Tuple[float, float]:
        """
        Deducts fees from the amount in.

        Parameters
        ----------
        amount_in : float
            The amount to deduct fees from.

        Returns
        -------
        float
            The token amount leftover after fees are deducted.
        float
            The amount of fees deducted.
        """
        fees_deducted = int(amount_in * self.fee_tier)
        amount_leftover = amount_in - fees_deducted
        return amount_leftover, fees_deducted

    def add_fees(self, amount_used_for_swap: float) -> Tuple[float, float]:
        """
        Adds fees to the amount used.

        Parameters
        ----------
        amount_used_for_swap : float
            The amount to add fees to.

        Returns
        -------
        float
            The token amount including fees.
        float
            The amount of fees added.
        """
        amount_used = amount_used_for_swap/(1-self.fee_tier)
        fees = amount_used - amount_used_for_swap
        return amount_used, fees

    def revert_swap(self, original_state: dict):
        """
        Reverts a swap by restoring all class attributes to their pre-swap
        values.

        Parameters
        ----------
        original_state : dict
            A dictionary containing all the class attributes before the swap.
        """
        self.__dict__.update(original_state)

    def swap(
            self,
            token_in_addr: str,
            amount_in: float,
            sqrt_price_limit: float,
            simulate: bool = False
    ) -> float:
        """
        Performs a swap in the Uniswap pool.

        Parameters
        ----------
        token_in_addr : str
            The token to be swapped in.
        amount_in : float
            The amount of the token to be swapped in.
        sqrt_price_limit : float
            The limit of the square root price for the swap (to protect against
            slippage).

        Returns
        -------
        float
            The amount of the token swapped out.
        """

        original_state = self.__dict__.copy()
        try:
            if token_in_addr == self.token_x:
                amount_out = self.swap_x_for_y(amount_in, sqrt_price_limit)
                if not simulate:
                    self.token_x_balance += amount_in
                    self.token_y_balance -= amount_out
            else:
                amount_out = self.swap_y_for_x(amount_in, sqrt_price_limit)
                if not simulate:
                    self.token_y_balance += amount_in
                    self.token_x_balance -= amount_out
            if simulate:
                self.revert_swap(original_state)
            return amount_out
        except Exception:
            print('''
                  SWAP FAILED
                  Restoring all pool attributes to their pre-swap values
                  ''')
            # Restore all class attributes to their pre-swap values
            self.revert_swap(original_state)

    def swap_x_for_y(
        self,
        amount_in: float,
        sqrt_price_limit: float
    ) -> float:
        """
        Swaps token X for token Y in the Uniswap pool.

        Parameters
        ----------
        amount_in : float
            The amount of token X to be swapped in (after deducting fees).
        sqrt_price_limit : float
            The limit of the square root price for the swap.

        Returns
        -------
        float
            The amount of token Y swapped out.
        """

        amount_out = 0
        amount_remaining = amount_in
        next_tick = self.find_next_tick(self.curr_tick_idx, False)
        if next_tick is None:
            raise InsufficientLiquidityException
        lower_tick_sqrt_price, _ = self.tick_to_sqrt_price(next_tick)

        while amount_remaining > 0:
            amount_remaining_after_fees, fees_deducted =\
                self.deduct_fees(amount_remaining)
            # delta(1/sqrt(P)) = delta(x) / L
            delta_inv_sqrt_price = amount_remaining_after_fees/self.liquidity
            inv_sqrt_price = 1/self.curr_sqrt_price
            updated_inv_sqrt_price = inv_sqrt_price + delta_inv_sqrt_price
            # New sqrt price
            updated_sqrt_price = 1/updated_inv_sqrt_price
            # If new sqrt price is within current tick
            if updated_sqrt_price >= lower_tick_sqrt_price:
                # delta(sqrt(P))
                delta_sqrt_price = self.curr_sqrt_price - updated_sqrt_price
                # delta(y) = delta(sqrt(P)) * L
                amount_out += int(delta_sqrt_price * self.liquidity)
                amount_remaining = 0
                # Update fees
                self.fee_growth_global_x += fees_deducted/self.liquidity
                # Update state
                self.curr_sqrt_price = updated_sqrt_price
                self.curr_tick_idx =\
                    self.sqrt_price_to_tick(self.curr_sqrt_price)
            else:
                # delta(x) = delta(1/sqrt(P)) * L
                amount_used_for_swap =\
                    (((1/lower_tick_sqrt_price) - (1/self.curr_sqrt_price))
                        * self.liquidity)
                amount_used, fees_deducted =\
                    self.add_fees(amount_used_for_swap)
                # delta(sqrt(P))
                delta_sqrt_price =\
                    self.curr_sqrt_price - lower_tick_sqrt_price
                # delta(y) = delta(sqrt(P)) * L
                amount_out += int(delta_sqrt_price * self.liquidity)
                amount_remaining = amount_remaining - amount_used
                self.fee_growth_global_x += fees_deducted/self.liquidity
                # Update state
                self.curr_tick_idx = next_tick
                print('Tick crossed: ', self.curr_tick_idx)
                print('Liquidity pct change: ', self.ticks[self.curr_tick_idx].liquidity_net*100/self.liquidity)
                next_tick = self.find_next_tick(self.curr_tick_idx, False)
                if next_tick is None:
                    raise InsufficientLiquidityException
                self.curr_sqrt_price = lower_tick_sqrt_price
                self.liquidity = (
                    self.liquidity
                    - self.ticks[self.curr_tick_idx].liquidity_net
                )
                if self.liquidity == 0:
                    raise InsufficientLiquidityException
                lower_tick_sqrt_price, _ = self.tick_to_sqrt_price(next_tick)
                # Update fee growth outside
                (self.ticks[self.curr_tick_idx].fee_growth_outside_x,
                 self.ticks[self.curr_tick_idx].fee_growth_outside_y) =\
                    self.fee_growth_outside(self.curr_tick_idx)

            if self.curr_sqrt_price <= sqrt_price_limit:
                raise SlippageTooHighException

        return amount_out

    def swap_y_for_x(
        self,
        amount_in: float,
        sqrt_price_limit: float
    ) -> float:
        """
        Swaps token Y for token X in the Uniswap pool.

        Parameters
        ----------
        amount_in : float
            The amount of token Y to be swapped in (after deducting fees).
        sqrt_price_limit : float
            The limit of the square root price for the swap.

        Returns
        -------
        float
            The amount of token X swapped out.
        """

        amount_out = 0
        amount_remaining = amount_in
        next_tick = self.find_next_tick(self.curr_tick_idx, True)
        if next_tick is None:
            raise InsufficientLiquidityException
        lower_tick_sqrt_price, _ = self.tick_to_sqrt_price(next_tick)

        while amount_remaining > 0:
            amount_remaining_after_fees, fees_deducted =\
                self.deduct_fees(amount_remaining)
            # delta(sqrt(P)) = delta(y) / L
            delta_sqrt_price = amount_remaining_after_fees / self.liquidity
            updated_sqrt_price = self.curr_sqrt_price + delta_sqrt_price
            # If new sqrt price is within current tick
            if updated_sqrt_price <= lower_tick_sqrt_price:
                # delta(x) = delta(1/sqrt(P)) * L
                delta_inv_sqrt_price =\
                    (1/self.curr_sqrt_price) - (1/updated_sqrt_price)
                amount_out += delta_inv_sqrt_price * self.liquidity
                amount_remaining = 0
                # Update fees
                self.fee_growth_global_y += fees_deducted/self.liquidity
                # Update state
                self.curr_sqrt_price = updated_sqrt_price
                self.curr_tick_idx =\
                    self.sqrt_price_to_tick(self.curr_sqrt_price)
            else:
                # delta(y) = delta(sqrt(P)) * L
                amount_used_for_swap =\
                    ((lower_tick_sqrt_price - self.curr_sqrt_price)
                     * self.liquidity)
                amount_used, fees_deducted =\
                    self.add_fees(amount_used_for_swap)
                # delta(1/sqrt(P))
                delta_inv_sqrt_price =\
                    (1/self.curr_sqrt_price) - (1/lower_tick_sqrt_price)
                amount_out += delta_inv_sqrt_price * self.liquidity
                amount_remaining = amount_remaining - amount_used
                self.fee_growth_global_y += fees_deducted/self.liquidity
                # Update state
                self.curr_tick_idx = next_tick
                print('Tick crossed: ', self.curr_tick_idx)
                print('Liquidity pct change: ', self.ticks[self.curr_tick_idx].liquidity_net*100/self.liquidity)
                next_tick = self.find_next_tick(self.curr_tick_idx, True)
                if next_tick is None:
                    raise InsufficientLiquidityException
                self.curr_sqrt_price = lower_tick_sqrt_price
                self.liquidity = (
                    self.liquidity
                    + self.ticks[self.curr_tick_idx].liquidity_net
                )
                if self.liquidity == 0:
                    raise InsufficientLiquidityException
                lower_tick_sqrt_price, _ = self.tick_to_sqrt_price(next_tick)
                # Update fee growth outside
                (self.ticks[self.curr_tick_idx].fee_growth_outside_x,
                 self.ticks[self.curr_tick_idx].fee_growth_outside_y) =\
                    self.fee_growth_outside(self.curr_tick_idx)

            if self.curr_sqrt_price >= sqrt_price_limit:
                raise SlippageTooHighException

        return amount_out


class SlippageTooHighException(Exception):
    """Raised when slippage due to swap is too high"""
    pass


class InsufficientLiquidityException(Exception):
    """Raised when there isn't enough liquidity to perform a swap"""
    pass
