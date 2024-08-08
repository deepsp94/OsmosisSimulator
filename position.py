from tick import Tick


class Position:
    """
    A class to represent a Position in a Uniswap v3 pool.

    ...

    Attributes
    ----------
    liquidity : int
        The liquidity amount in this position
    lower_tick : Tick
        The lower tick of the range of this position
    upper_tick : Tick
        The upper tick of the range of this position
    range_len : int
        Number of ticks between, and including, the lower and upper ticks

    """
    def __init__(
            self,
            owner: str,
            liquidity: int,
            lower_tick: Tick,
            upper_tick: Tick,
            fee_growth_inside_x: float,
            fee_growth_inside_y: float
    ) -> None:
        """
        Constructs all the necessary attributes for the Position object.

        Parameters
        ----------
        owner : str
            The owner (address) of the LP position
        liquidity : int
            The liquidity amount in this position
        lower_tick : Tick
            The lower tick of the range of this position
        upper_tick : Tick
            The upper tick of the range of this position
        fee_growth_inside_x : float
            The fee growth of token X inside the range of this position
        fee_growth_inside_y : float
            The fee growth of token Y inside the range of this position
        fees_x : float
            The fees collected in token X
        fees_y : float
            The fees collected in token Y
        """
        self.owner = owner
        self.liquidity = liquidity
        self.lower_tick = lower_tick
        self.upper_tick = upper_tick
        self.fee_growth_inside_x = fee_growth_inside_x
        self.fee_growth_inside_y = fee_growth_inside_y
        self.fees_x = 0
        self.fees_y = 0
