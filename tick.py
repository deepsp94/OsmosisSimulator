class Tick:
    """
    A class to represent a Tick on the price space of a Uniswap v3 pool.
    ...

    Attributes
    ----------
    idx : int
        The index of the Tick
    liquidity : float
        The liquidity at this Tick

    """
    def __init__(
            self,
            idx: int,
            liquidity_net: float,
            liquidity_gross: float,
            fee_growth_outside_x: float,
            fee_growth_outside_y: float
    ) -> None:
        """
        Constructs all the necessary attributes for the Tick object.

        Parameters
        ----------
        idx : int
            The index of the Tick
        liquidity : float
            The liquidity at this Tick
        """
        self.idx = idx
        self.liquidity_net = liquidity_net
        self.liquidity_gross = liquidity_gross
        self.fee_growth_outside_x = fee_growth_outside_x
        self.fee_growth_outside_y = fee_growth_outside_y
