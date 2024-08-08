# Simulator for Osmosis Concentrated Liquidity Pools

This repository contains a simulator for Osmosis concentrated liquidity pools. The simulator is written in Python and is based on the [Osmosis docs](docs.osmosis.zone/overview/integrate/pool-setup).

## Installation
The library uses base python so installation is required.

## Usage
```
token_x = 'ibc/831F0B1BBB1D08A2B75311892876D71565478C532967545476DF4C2D7492E48C'  # DYDX
token_y = 'ibc/498A0751C798A0D9A389AA3691123DADA57DAA4FE165D5C75894505B876BA6E4'  # USD

decimals = 1e6
pair = Pair(
    token_x=token_x,
    token_y=token_y,
    init_sqrt_price=1.8384776310851507e-06,
    fee_tier=0.003,
    tick_spacing=100
)
```