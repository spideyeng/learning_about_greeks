"""Streamlit front-end for the Commodity Option Strategy Advisor.

Run locally:
    streamlit run streamlit_app.py
(or `python streamlit_app.py` — it relaunches itself under streamlit)

All pricing/strategy logic lives in advisor_core.py (shared with the
ipywidgets notebook version).
"""

import sys

try:
    import streamlit as st
except ModuleNotFoundError:
    sys.exit(
        f"streamlit is not installed in this interpreter: {sys.executable}\n"
        "Use the miniconda one instead:\n"
        "    ~/miniconda3/bin/python -m streamlit run streamlit_app.py\n"
        "In VS Code: Ctrl+Shift+P -> 'Python: Select Interpreter' -> "
        "Python (base) ~/miniconda3/bin/python"
    )

# Launched as a plain script (e.g. VS Code Run button)? Re-exec under streamlit.
if __name__ == '__main__':
    from streamlit import runtime
    if not runtime.exists():
        from streamlit.web import cli as stcli
        sys.argv = ['streamlit', 'run', __file__] + sys.argv[1:]
        sys.exit(stcli.main())

from advisor_core import (
    COMMODITIES, STRATEGIES, ROLES, VIEWS, PREMIUM_APPETITES, TENORS,
    analyze_strategy, recommend, payoff_figure,
)

st.set_page_config(page_title='Option Strategy Advisor — Crude & LNG', page_icon='🛢️', layout='wide')

st.title('🛢️ Commodity Option Strategy Advisor — Crude & LNG')
st.caption(
    'Tell it your commodity, role, price view, and premium appetite — it recommends a strategy, '
    'prices every leg with Black-76, and shows the payoff, Greeks, and breakevens. '
    'Default prices and vols are illustrative, not live market data.'
)

# ── Inputs ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header('Your situation')
    commodity = st.selectbox('Commodity', list(COMMODITIES))
    role = st.selectbox('Your role', ROLES)
    view = st.selectbox('Price view', VIEWS)
    prem = st.selectbox('Premium appetite', PREMIUM_APPETITES)
    tenor_label = st.select_slider('Tenor', options=[t[0] for t in TENORS], value='3 months')
    T = dict(TENORS)[tenor_label]

    st.header('Market levels')
    profile = COMMODITIES[commodity]
    F = st.number_input(
        f"Futures price ({profile['unit']})", min_value=0.01,
        value=float(profile['F']), step=0.5,
        help='Defaults to the illustrative profile — override with the live level.')
    sigma = st.slider(
        'Implied volatility (%)', min_value=5, max_value=150,
        value=int(profile['sigma'] * 100),
        help='LNG routinely trades 40–150%; crude 25–60%.') / 100
    r = st.slider('Risk-free rate (%)', min_value=0.0, max_value=10.0, value=5.0, step=0.25) / 100

picks = recommend(role, view, prem)
if picks is None:
    st.error(f'No mapping for ({role}, {view}, {prem}) — check your inputs.')
    st.stop()

primary, alternatives = picks

st.success(f'**Recommended: {primary}**  —  {STRATEGIES[primary]["summary"]}')
if alternatives:
    st.info('**Alternative(s):** ' + ', '.join(alternatives) + ' — compare them in the tabs below.')

# ── Trade cards: primary first, alternatives in their own tabs ───────────────
tabs = st.tabs([f'▶ {primary}'] + [f'Alt: {a}' for a in alternatives])

for tab, strat_name in zip(tabs, [primary] + list(alternatives)):
    with tab:
        res = analyze_strategy(strat_name, commodity, T=T, r=r, F=F, sigma=sigma)

        st.markdown(
            f"**{strat_name}** on **{commodity}**  |  F = {res['F']:.2f} {res['unit']}  |  "
            f"IV = {res['sigma'] * 100:.0f}%  |  T = {tenor_label}  |  {res['exchange']}"
        )

        col_left, col_right = st.columns([2, 3])

        with col_left:
            st.subheader('Legs')
            st.table([
                {
                    'Side': leg['side'],
                    'Qty': leg['qty'],
                    'Type': leg['type'],
                    'Strike': f"{leg['strike']:.2f}",
                    'Premium': '—' if leg['premium'] is None else f"{leg['premium']:.4f}",
                }
                for leg in res['legs']
            ])

            net = res['net_premium']
            lbl = 'you PAY' if net > 0 else 'you COLLECT'
            per_contract = abs(net) * res['contract_size']
            st.metric(
                'Net premium',
                f"{abs(net):.4f} {res['unit']} ({lbl})",
                delta=f"${per_contract:,.0f} per contract ({res['contract_size']:,} {res['contract_unit']})",
                delta_color='off',
            )
            if res['breakevens']:
                st.metric('Breakeven(s) at expiry', ', '.join(str(b) for b in res['breakevens']) + f" {res['unit']}")

            c1, c2 = st.columns(2)
            c1.metric('Max profit', f"{res['max_profit']:,.2f}", help='Per unit, within the ±50% price range shown')
            c2.metric('Max loss', f"{res['max_loss']:,.2f}", help='Per unit, within the ±50% price range shown')

        with col_right:
            st.subheader('Payoff at expiry')
            st.pyplot(payoff_figure(res), clear_figure=True)

            g = res['greeks']
            g1, g2, g3, g4 = st.columns(4)
            g1.metric('Δ Delta', f"{g['delta']:+.3f}")
            g2.metric('Γ Gamma', f"{g['gamma']:+.4f}")
            g3.metric('Θ Theta /day', f"{g['theta']:+.4f}")
            g4.metric('Vega /1% IV', f"{g['vega']:+.4f}")

        st.markdown(f"**When to use:** {res['when']}")
        st.warning(f"**Watch out:** {res['watch']}")
        st.caption(f"Commodity note: {res['commodity_notes']}")

# ── Reference ────────────────────────────────────────────────────────────────
with st.expander('📖 Decision matrix reference'):
    st.markdown('''
### Producer (long physical — owns crude barrels / LNG cargoes, fears a price FALL)

| Price view | Pay premium | Zero-cost | Collect premium |
|---|---|---|---|
| Bearish | **Long Put** | **Costless Collar** | Collar |
| Range-bound | Put Spread | Collar | **Covered Call** |
| Bullish | Put Spread (cheap insurance) | Put Spread | Covered Call |
| Big move either way | Long Put | Collar | Collar |

### Consumer (short physical — must buy fuel/feedstock, fears a SPIKE)

| Price view | Pay premium | Zero-cost | Collect premium |
|---|---|---|---|
| Bullish | **Long Call** | **Consumer Collar** | Collar |
| Range-bound | Call Spread | Collar | **Cash-Secured Put** |
| Bearish | Call Spread (cheap insurance) | Call Spread | Cash-Secured Put |
| Big move either way | Long Call | Collar | Collar |

### Speculator (no physical exposure)

| Price view | Pay premium | Zero-cost | Collect premium |
|---|---|---|---|
| Bullish | **Long Call** | Call Spread | Cash-Secured Put |
| Bearish | **Long Put** | Put Spread | Put Spread |
| Range-bound | Iron Condor | Iron Condor | **Iron Condor / Short Strangle** |
| Big move either way | **Long Straddle** | Long Strangle | Long Strangle |

### Crude vs. LNG — practical differences

| Factor | Crude (WTI/Brent) | LNG (JKM) |
|---|---|---|
| Typical IV | 25–60% | 40–150%, extreme in winter |
| Skew | Moderate upside skew | Heavy upside skew — OTM calls very rich |
| Premium selling | Reasonable risk/reward | Dangerous on the call side (spike risk) |
| Collar strikes | ±10% works | Consider asymmetric strikes (wider call side) |
| Liquidity | Deep, tight spreads | Thinner; wider bid/ask, use limit orders |
| Seasonality | Mild (driving season) | Severe (winter heating, summer cooling in Asia) |
''')

st.caption(
    '⚠️ Disclaimer: default prices and vols are illustrative. Update them to live market levels, '
    'and treat the output as a structured starting point — not trade advice.'
)
