"""Shared engine for the Commodity Option Strategy Advisor (Crude & LNG).

Extracted from option_strategy_advisor.ipynb so the same pricing logic,
strategy library, and decision matrix back both front-ends:

- streamlit_app.py                       (Streamlit web app)
- option_strategy_advisor_widgets.ipynb  (ipywidgets panel, servable via Voila)

All pricing uses Black-76 on futures. Default prices/vols in COMMODITIES are
illustrative -- update to live market levels before making real decisions.
"""

import numpy as np
from scipy.stats import norm

# ── Black-76 pricing engine ──────────────────────────────────────────────────

def d1_76(F, K, T, sigma):
    return (np.log(F / K) + 0.5 * sigma**2 * T) / (sigma * np.sqrt(T))


def black76_price(F, K, T, r, sigma, opt_type):
    d1 = d1_76(F, K, T, sigma)
    d2 = d1 - sigma * np.sqrt(T)
    disc = np.exp(-r * T)
    if opt_type == 'call':
        return disc * (F * norm.cdf(d1) - K * norm.cdf(d2))
    else:
        return disc * (K * norm.cdf(-d2) - F * norm.cdf(-d1))


def black76_greeks(F, K, T, r, sigma, opt_type):
    """Returns dict: delta, gamma, theta ($/day), vega (per 1% IV), price."""
    d1 = d1_76(F, K, T, sigma)
    disc = np.exp(-r * T)
    price = black76_price(F, K, T, r, sigma, opt_type)
    delta = disc * norm.cdf(d1) if opt_type == 'call' else -disc * norm.cdf(-d1)
    gamma = disc * norm.pdf(d1) / (F * sigma * np.sqrt(T))
    vega = F * disc * norm.pdf(d1) * np.sqrt(T) / 100
    theta = -(F * disc * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) + r * price) / 365
    return {'delta': delta, 'gamma': gamma, 'theta': theta, 'vega': vega, 'price': price}


# ── Commodity profiles ───────────────────────────────────────────────────────

COMMODITIES = {
    'WTI Crude': {
        'F': 80.00, 'sigma': 0.35, 'unit': '$/bbl',
        'contract_size': 1000, 'contract_unit': 'bbl',
        'exchange': 'NYMEX (CL options → LO)',
        'notes': 'Upside vol skew — OTM calls trade rich vs. puts. Watch OPEC meetings and EIA Wednesday storage reports.'
    },
    'Brent Crude': {
        'F': 84.00, 'sigma': 0.33, 'unit': '$/bbl',
        'contract_size': 1000, 'contract_unit': 'bbl',
        'exchange': 'ICE (B options)',
        'notes': 'Global waterborne benchmark; geopolitical premium usually shows up here first.'
    },
    'LNG (JKM)': {
        'F': 12.00, 'sigma': 0.60, 'unit': '$/MMBtu',
        'contract_size': 10000, 'contract_unit': 'MMBtu',
        'exchange': 'ICE / CME JKM futures & options',
        'notes': 'Extremely high and seasonal vol (winter demand, freight, outages). Skew is heavily to the upside — supply shocks can triple prices. Consider wider strikes than you would for crude.'
    },
}

# ── Strategy library ─────────────────────────────────────────────────────────
# Each leg: (option_type, strike_pct_of_F, quantity)  qty >0 = long, <0 = short
# 'fut' legs represent a futures position (for reference strategies).

STRATEGIES = {
    'Long Put': {
        'legs': [('put', 0.95, +1)],
        'summary': 'Buy a put ~5% OTM. Insurance: floor your selling price, keep all upside.',
        'when': 'Producer fearing a fall, or bearish speculator, willing to pay premium.',
        'watch': 'Premium is a sunk cost; high IV (common in LNG) makes this expensive.'
    },
    'Put Spread': {
        'legs': [('put', 0.95, +1), ('put', 0.85, -1)],
        'summary': 'Buy 95% put, sell 85% put. Cheaper downside protection, but the floor stops at the lower strike.',
        'when': 'Moderately bearish view / budget-constrained hedge. You accept re-exposure below the short strike.',
        'watch': 'Protection vanishes below the short strike — size the gap to your worst-case tolerance.'
    },
    'Costless Collar (producer)': {
        'legs': [('put', 0.90, +1), ('call', 1.10, -1)],
        'summary': 'Buy 90% put financed by selling a 110% call. Near-zero net premium: floor at 90%, ceiling at 110%.',
        'when': 'Producer who wants free protection and can live with capped upside.',
        'watch': 'You give away rallies above the call strike — painful in an LNG spike. Strikes here are illustrative; solve for the call strike that makes net premium exactly zero.'
    },
    'Covered Call (vs. physical)': {
        'legs': [('call', 1.08, -1)],
        'summary': 'Sell an ~8% OTM call against physical production/inventory. Collect premium as extra yield.',
        'when': 'Producer with a neutral-to-mildly-bullish view who wants income, not protection.',
        'watch': 'NO downside protection beyond the premium collected. This is yield enhancement, not a hedge.'
    },
    'Long Call': {
        'legs': [('call', 1.05, +1)],
        'summary': 'Buy a call ~5% OTM. Caps your purchase cost, keeps the benefit if prices fall.',
        'when': 'Consumer fearing a spike, or bullish speculator, willing to pay premium.',
        'watch': 'LNG upside skew makes OTM calls expensive — compare against a call spread.'
    },
    'Call Spread': {
        'legs': [('call', 1.05, +1), ('call', 1.20, -1)],
        'summary': 'Buy 105% call, sell 120% call. Cheaper cost cap; protection stops above the upper strike.',
        'when': 'Consumer hedging a moderate spike scenario, or bullish speculator wanting defined risk/reward.',
        'watch': 'In an extreme squeeze (LNG winters), price can blow through the short strike and you are unhedged above it.'
    },
    'Consumer Collar': {
        'legs': [('call', 1.10, +1), ('put', 0.90, -1)],
        'summary': 'Buy 110% call financed by selling a 90% put. Near-zero premium: cost capped at 110%, but you forgo savings below 90%.',
        'when': 'Consumer (airline, utility, importer) wanting zero-cost cost certainty within a band.',
        'watch': 'If prices collapse you are obligated at the put strike — you lose the windfall of cheap fuel.'
    },
    'Cash-Secured Put': {
        'legs': [('put', 0.92, -1)],
        'summary': 'Sell an ~8% OTM put. Collect premium; if assigned, you buy the commodity at an effective discount.',
        'when': 'Consumer happy to buy at lower levels, or neutral-to-bullish premium seller.',
        'watch': 'Full downside exposure below the strike. Only sell puts on volume you genuinely want to own.'
    },
    'Long Straddle': {
        'legs': [('call', 1.00, +1), ('put', 1.00, +1)],
        'summary': 'Buy ATM call + ATM put. Profits from a large move in EITHER direction.',
        'when': 'Speculator expecting a big move (OPEC decision, winter weather, geopolitics) but unsure of direction. Best entered when IV is LOW relative to the expected move.',
        'watch': 'Expensive; double theta bleed. If the event passes quietly, IV crush hits both legs.'
    },
    'Long Strangle': {
        'legs': [('call', 1.08, +1), ('put', 0.92, +1)],
        'summary': 'Buy OTM call + OTM put. Cheaper than a straddle; needs a bigger move to pay off.',
        'when': 'Same thesis as straddle but with less capital; suits high-priced-premium markets like LNG.',
        'watch': 'Wider breakevens — the move must be violent, not just large.'
    },
    'Short Strangle': {
        'legs': [('call', 1.12, -1), ('put', 0.88, -1)],
        'summary': 'Sell OTM call + OTM put. Collect double premium if price stays in the band.',
        'when': 'Speculator with a strong range-bound view and falling-IV expectation (post-event, shoulder season).',
        'watch': 'UNLIMITED risk both directions. In LNG this can be ruinous — one cold snap and the call side explodes. Professionals only, with strict risk limits.'
    },
    'Iron Condor': {
        'legs': [('put', 0.80, +1), ('put', 0.90, -1), ('call', 1.10, -1), ('call', 1.20, +1)],
        'summary': 'Short strangle with protective wings. Defined-risk premium collection in a range.',
        'when': 'Range-bound view but you want a hard cap on losses (the sane version of a short strangle).',
        'watch': 'Lower premium than a naked strangle; commissions on 4 legs. Still hurts if price trends through a wing.'
    },
    'Short Futures (reference)': {
        'legs': [('fut', 1.00, -1)],
        'summary': 'Sell futures outright. Locks the price completely — no premium, no optionality.',
        'when': 'Producer wanting certainty over flexibility. The benchmark every option hedge should be compared against.',
        'watch': 'Gives up ALL upside; margin calls if the market rallies against you.'
    },
    'Long Futures (reference)': {
        'legs': [('fut', 1.00, +1)],
        'summary': 'Buy futures outright. Locks purchase cost completely — no premium, no optionality.',
        'when': 'Consumer wanting certainty over flexibility.',
        'watch': 'Gives up all benefit if prices fall; margin calls in a sell-off.'
    },
}

# ── Decision matrix ──────────────────────────────────────────────────────────
# (role, price_view, premium_appetite) → [primary, alternative, ...]

ROLES = ['Producer', 'Consumer', 'Speculator']
VIEWS = ['Bearish / fear a fall', 'Bullish / expect rise', 'Range-bound', 'Big move, either way']
PREMIUM_APPETITES = ['Pay premium', 'Zero-cost', 'Collect premium']
TENORS = [('1 month', 1 / 12), ('3 months', 0.25), ('6 months', 0.5), ('12 months', 1.0)]

MATRIX = {
    # ── PRODUCER (long physical: owns barrels / cargoes, fears a price FALL) ──
    ('Producer', 'Bearish / fear a fall',  'Pay premium'):     ['Long Put', 'Put Spread'],
    ('Producer', 'Bearish / fear a fall',  'Zero-cost'):       ['Costless Collar (producer)', 'Put Spread'],
    ('Producer', 'Bearish / fear a fall',  'Collect premium'): ['Costless Collar (producer)', 'Short Futures (reference)'],
    ('Producer', 'Range-bound',            'Pay premium'):     ['Put Spread', 'Long Put'],
    ('Producer', 'Range-bound',            'Zero-cost'):       ['Costless Collar (producer)'],
    ('Producer', 'Range-bound',            'Collect premium'): ['Covered Call (vs. physical)', 'Costless Collar (producer)'],
    ('Producer', 'Bullish / expect rise',  'Pay premium'):     ['Put Spread', 'Long Put'],
    ('Producer', 'Bullish / expect rise',  'Zero-cost'):       ['Put Spread'],
    ('Producer', 'Bullish / expect rise',  'Collect premium'): ['Covered Call (vs. physical)'],
    ('Producer', 'Big move, either way',   'Pay premium'):     ['Long Put', 'Long Strangle'],
    ('Producer', 'Big move, either way',   'Zero-cost'):       ['Costless Collar (producer)'],
    ('Producer', 'Big move, either way',   'Collect premium'): ['Costless Collar (producer)'],

    # ── CONSUMER (short physical: must buy fuel/feedstock, fears a SPIKE) ──
    ('Consumer', 'Bullish / expect rise',  'Pay premium'):     ['Long Call', 'Call Spread'],
    ('Consumer', 'Bullish / expect rise',  'Zero-cost'):       ['Consumer Collar', 'Call Spread'],
    ('Consumer', 'Bullish / expect rise',  'Collect premium'): ['Consumer Collar', 'Long Futures (reference)'],
    ('Consumer', 'Range-bound',            'Pay premium'):     ['Call Spread', 'Long Call'],
    ('Consumer', 'Range-bound',            'Zero-cost'):       ['Consumer Collar'],
    ('Consumer', 'Range-bound',            'Collect premium'): ['Cash-Secured Put', 'Consumer Collar'],
    ('Consumer', 'Bearish / fear a fall',  'Pay premium'):     ['Call Spread'],
    ('Consumer', 'Bearish / fear a fall',  'Zero-cost'):       ['Call Spread'],
    ('Consumer', 'Bearish / fear a fall',  'Collect premium'): ['Cash-Secured Put'],
    ('Consumer', 'Big move, either way',   'Pay premium'):     ['Long Call', 'Long Strangle'],
    ('Consumer', 'Big move, either way',   'Zero-cost'):       ['Consumer Collar'],
    ('Consumer', 'Big move, either way',   'Collect premium'): ['Consumer Collar'],

    # ── SPECULATOR (no physical exposure — pure directional/vol bet) ──
    ('Speculator', 'Bullish / expect rise', 'Pay premium'):     ['Long Call', 'Call Spread'],
    ('Speculator', 'Bullish / expect rise', 'Zero-cost'):       ['Call Spread'],
    ('Speculator', 'Bullish / expect rise', 'Collect premium'): ['Cash-Secured Put', 'Call Spread'],
    ('Speculator', 'Bearish / fear a fall', 'Pay premium'):     ['Long Put', 'Put Spread'],
    ('Speculator', 'Bearish / fear a fall', 'Zero-cost'):       ['Put Spread'],
    ('Speculator', 'Bearish / fear a fall', 'Collect premium'): ['Put Spread'],
    ('Speculator', 'Range-bound',           'Pay premium'):     ['Iron Condor'],
    ('Speculator', 'Range-bound',           'Zero-cost'):       ['Iron Condor'],
    ('Speculator', 'Range-bound',           'Collect premium'): ['Iron Condor', 'Short Strangle'],
    ('Speculator', 'Big move, either way',  'Pay premium'):     ['Long Straddle', 'Long Strangle'],
    ('Speculator', 'Big move, either way',  'Zero-cost'):       ['Long Strangle'],
    ('Speculator', 'Big move, either way',  'Collect premium'): ['Long Strangle'],
}


# ── Analysis ─────────────────────────────────────────────────────────────────

def leg_payoff(opt_type, K, qty, premium, S_range):
    """P&L of one leg at expiry across a range of settlement prices."""
    if opt_type == 'fut':
        return qty * (S_range - K)
    intrinsic = np.maximum(S_range - K, 0) if opt_type == 'call' else np.maximum(K - S_range, 0)
    return qty * (intrinsic - premium)


def analyze_strategy(strategy_name, commodity_name, T=0.25, r=0.05, F=None, sigma=None):
    """Price all legs with Black-76 and return a structured result dict.

    F and sigma default to the commodity profile but can be overridden
    with live market levels.
    """
    c = COMMODITIES[commodity_name]
    strat = STRATEGIES[strategy_name]
    F = c['F'] if F is None else F
    sigma = c['sigma'] if sigma is None else sigma

    S_range = np.linspace(F * 0.5, F * 1.6, 500)
    total_pnl = np.zeros_like(S_range)
    net_premium = 0.0
    net_greeks = {'delta': 0.0, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0}
    legs = []

    for opt_type, k_pct, qty in strat['legs']:
        K = round(F * k_pct, 2)
        if opt_type == 'fut':
            premium = 0.0
            g = {'delta': 1.0, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0}
        else:
            premium = black76_price(F, K, T, r, sigma, opt_type)
            g = black76_greeks(F, K, T, r, sigma, opt_type)
        total_pnl += leg_payoff(opt_type, K, qty, premium, S_range)
        net_premium += qty * premium
        for k in net_greeks:
            net_greeks[k] += qty * g[k]
        legs.append({
            'side': 'BUY' if qty > 0 else 'SELL',
            'qty': abs(qty),
            'type': opt_type.upper(),
            'strike': K,
            'premium': None if opt_type == 'fut' else premium,
        })

    # Breakevens: sign changes of payoff
    sign_change = np.where(np.diff(np.sign(total_pnl)) != 0)[0]
    breakevens = [round(float(S_range[i] + S_range[i + 1]) / 2, 2) for i in sign_change]

    return {
        'strategy': strategy_name,
        'commodity': commodity_name,
        'F': F, 'sigma': sigma, 'T': T, 'r': r,
        'unit': c['unit'],
        'exchange': c['exchange'],
        'contract_size': c['contract_size'],
        'contract_unit': c['contract_unit'],
        'commodity_notes': c['notes'],
        'summary': strat['summary'],
        'when': strat['when'],
        'watch': strat['watch'],
        'legs': legs,
        'net_premium': net_premium,
        'breakevens': breakevens,
        'max_profit': float(total_pnl.max()),
        'max_loss': float(total_pnl.min()),
        'greeks': net_greeks,
        'S_range': S_range,
        'pnl': total_pnl,
    }


def recommend(role, view, premium_appetite):
    """Look up the decision matrix. Returns (primary, [alternatives]) or None."""
    picks = MATRIX.get((role, view, premium_appetite))
    if picks is None:
        return None
    return picks[0], picks[1:]


def payoff_figure(res, figsize=(9, 4.5)):
    """Matplotlib payoff-at-expiry figure for an analyze_strategy() result."""
    import matplotlib.pyplot as plt

    S_range, total_pnl, F, unit = res['S_range'], res['pnl'], res['F'], res['unit']
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(S_range, total_pnl, color='navy', linewidth=2)
    ax.fill_between(S_range, total_pnl, 0, where=total_pnl >= 0, color='mediumseagreen', alpha=0.25)
    ax.fill_between(S_range, total_pnl, 0, where=total_pnl < 0, color='tomato', alpha=0.25)
    ax.axhline(0, color='black', linewidth=0.8)
    ax.axvline(F, color='gray', linestyle='--', alpha=0.7, label=f'Current F = {F}')
    for b in res['breakevens']:
        ax.axvline(b, color='darkorange', linestyle=':', alpha=0.8)
    ax.set_xlabel(f'Settlement Price ({unit})')
    ax.set_ylabel(f'P&L at Expiry ({unit} per unit)')
    ax.set_title(f"{res['strategy']} — {res['commodity']}  |  payoff at expiry")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig
