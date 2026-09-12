import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# Page Setup
st.set_page_config(page_title="DCA Simulator", layout="wide", page_icon="📈")

# Custom CSS for clean metric cards
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.6rem; }
    .stMetric { 
        background-color: rgba(28, 131, 225, 0.05); 
        padding: 10px; 
        border-radius: 8px; 
        border: 1px solid rgba(28, 131, 225, 0.1);
    }
    </style>
    """, unsafe_allow_html=True)

st.title("The Dollar Cost Averaging (DCA) Simulator")

# --- MODE SELECTION ---
mode = st.sidebar.radio(
    "Simulation Mode",
    ["📜 Historical Backtest", "🔮 Future Projection"],
    help="Backtest uses real historical prices. Projection assumes a future rate of return."
)

st.sidebar.divider()

PERIODS_PER_YEAR = {"Daily": 252, "Weekly": 52, "Monthly": 12}
FREQ_RESAMPLE = {"Daily": "B", "Weekly": "W-MON", "Monthly": "MS"}


# =========================================================
# MODE 1: HISTORICAL BACKTEST (real market data)
# =========================================================
if mode == "📜 Historical Backtest":

    st.sidebar.header("Backtest Settings")
    ticker_symbol = st.sidebar.text_input("Ticker (e.g., SPY, AAPL, MSFT)", value="SPY").upper()
    invest_amount = st.sidebar.number_input("Amount per Interval ($)", value=100, min_value=1)

    today = datetime.now().date()
    absolute_min = datetime(1980, 1, 1).date()
    default_start = datetime(2010, 1, 1).date()

    st.sidebar.subheader("Simulation Dates")
    start_date = st.sidebar.date_input("Start Date", value=default_start, min_value=absolute_min, max_value=today)

    if "end_date_key" not in st.session_state:
        st.session_state["end_date_key"] = today
    if st.sidebar.button("🕒 Reset End Date to Today"):
        st.session_state["end_date_key"] = today

    end_date = st.sidebar.date_input(
        "End Date", value=st.session_state["end_date_key"], key="end_date_key",
        min_value=start_date, max_value=today
    )

    frequency = st.sidebar.selectbox("Investment Frequency", list(FREQ_RESAMPLE.keys()))

    @st.cache_data(ttl=3600)
    def load_data(symbol, start, end):
        try:
            df = yf.download(symbol, start=start, end=end, auto_adjust=True)
            return df['Close'] if not df.empty else None
        except Exception:
            return None

    prices = load_data(ticker_symbol, start_date, end_date)

    if prices is not None and not prices.empty:
        if isinstance(prices, pd.DataFrame):
            prices = prices.iloc[:, 0]

        # --- MATH ENGINE ---
        buy_days = prices.resample(FREQ_RESAMPLE[frequency]).first().dropna()
        buy_prices = prices[prices.index.isin(buy_days.index)]

        total_intervals = len(buy_prices)
        total_invested = total_intervals * invest_amount
        shares_held = (invest_amount / buy_prices).sum()
        current_price = float(prices.iloc[-1])
        portfolio_value = shares_held * current_price
        avg_cost = total_invested / shares_held
        day_1_price = float(buy_prices.iloc[0])
        total_growth = ((portfolio_value / total_invested) - 1) * 100
        total_profit = portfolio_value - total_invested

        years_elapsed = max((prices.index[-1] - prices.index[0]).days / 365.25, 0.01)
        cagr = ((portfolio_value / total_invested) ** (1 / years_elapsed) - 1) * 100

        # --- METRICS ---
        st.subheader("📊 Performance Summary")
        m1, m2, m3 = st.columns(3)
        m1.metric("Current Market Price", f"${current_price:,.2f}")
        m2.metric("Total Invested", f"${total_invested:,.2f}")
        m3.metric("Current Portfolio Value", f"${portfolio_value:,.2f}")

        m4, m5, m6 = st.columns(3)
        m4.metric("Total Shares Owned", f"{shares_held:.3f}")
        m5.metric("Average Cost/Share", f"${avg_cost:,.2f}")
        m6.metric("Total Growth", f"{total_growth:.2f}%", f"${total_profit:,.2f} Profit")

        m7, _, _ = st.columns(3)
        m7.metric("Annualized Return (CAGR)", f"{cagr:.2f}%")

        st.divider()

        col_chart, col_story = st.columns([2, 1])

        with col_chart:
            st.subheader("📈 Price History")
            st.line_chart(prices)

        with col_story:
            st.subheader("📝 Your Story")
            first_p = buy_prices.index[0].strftime('%b %Y')
            st.info(f"""
            Starting in **{first_p}**, you invested **${invest_amount}** at regular intervals. 

            Over **{total_intervals}** contributions, you've seen the price move from an initial **${day_1_price:,.2f}** to the current **${current_price:,.2f}**.
            """)

            cost_diff = day_1_price - avg_cost
            if cost_diff > 0:
                st.success(f"**DCA Success:** Your average cost is **${cost_diff:,.2f} lower** than if you bought everything on Day 1.")
            else:
                st.warning("**Strong Uptrend:** Buying on Day 1 would have been cheaper, but DCA reduced your risk of timing a peak.")
    else:
        st.error("No data found for this ticker and date range.")


# =========================================================
# MODE 2: FUTURE PROJECTION (assumed rate of return)
# =========================================================
else:
    st.sidebar.header("Projection Settings")
    invest_amount = st.sidebar.number_input("Amount per Interval ($)", value=100, min_value=1)
    frequency = st.sidebar.selectbox("Investment Frequency", list(PERIODS_PER_YEAR.keys()), index=2)
    years = st.sidebar.slider("Investing Horizon (years)", min_value=1, max_value=40, value=15)
    expected_return = st.sidebar.slider("Expected Annual Return (%)", -10.0, 20.0, 7.0, 0.5)
    band = st.sidebar.slider("Optimistic / Pessimistic Band (± %)", 1.0, 10.0, 4.0, 0.5)
    starting_balance = st.sidebar.number_input("Starting Balance ($, optional)", value=0, min_value=0)

    periods_per_year = PERIODS_PER_YEAR[frequency]
    n_periods = years * periods_per_year

    scenarios = {
        "Pessimistic": expected_return - band,
        "Expected": expected_return,
        "Optimistic": expected_return + band,
    }

    def project(annual_return_pct, contribution, n, periods_per_yr, start_bal):
        r_annual = annual_return_pct / 100
        r_period = (1 + r_annual) ** (1 / periods_per_yr) - 1 if r_annual != -1 else 0
        values = np.zeros(n + 1)
        values[0] = start_bal
        for i in range(1, n + 1):
            values[i] = values[i - 1] * (1 + r_period) + contribution
        return values

    invested_series = starting_balance + np.arange(0, n_periods + 1) * invest_amount

    proj_df = pd.DataFrame({"Invested": invested_series})
    for label, rate in scenarios.items():
        proj_df[label] = project(rate, invest_amount, n_periods, periods_per_year, starting_balance)

    # Build a date-like index for readability
    proj_df.index = pd.date_range(start=datetime.now().date(), periods=n_periods + 1,
                                   freq="D" if frequency == "Daily" else ("W" if frequency == "Weekly" else "MS"))

    total_invested = float(invested_series[-1])
    final_expected = float(proj_df["Expected"].iloc[-1])
    final_optimistic = float(proj_df["Optimistic"].iloc[-1])
    final_pessimistic = float(proj_df["Pessimistic"].iloc[-1])
    total_growth = ((final_expected / total_invested) - 1) * 100 if total_invested > 0 else 0

    st.subheader("🔮 Projected Outcome")
    m1, m2, m3 = st.columns(3)
    m1.metric("Total You'll Invest", f"${total_invested:,.2f}")
    m2.metric("Projected Value (Expected)", f"${final_expected:,.2f}", f"{total_growth:.1f}% growth")
    m3.metric("Range at End of Horizon", f"${final_pessimistic:,.0f} – ${final_optimistic:,.0f}")

    st.divider()

    col_chart, col_story = st.columns([2, 1])

    with col_chart:
        st.subheader("📈 Projected Growth Over Time")
        st.line_chart(proj_df[["Invested", "Pessimistic", "Expected", "Optimistic"]])

    with col_story:
        st.subheader("📝 What This Means")
        st.info(f"""
        Investing **${invest_amount}** every **{frequency.lower()[:-2] if frequency != 'Monthly' else 'month'}** 
        for **{years} years**, assuming a **{expected_return:.1f}%** average annual return, 
        you'd contribute **${total_invested:,.0f}** and end up with roughly **${final_expected:,.0f}**.
        """)
        st.success(f"**The power of compounding:** ${final_expected - total_invested:,.0f} of your final balance is pure growth, not money you put in.")
        st.warning("This is a projection based on assumed, constant returns — real markets are volatile. Use the Historical Backtest mode to see how this strategy actually performed in the past.")
