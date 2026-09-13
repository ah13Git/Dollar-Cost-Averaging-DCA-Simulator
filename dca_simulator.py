import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

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
# SHARED HELPERS
# =========================================================
def calc_cagr(final_value, invested, years):
    """Annualized return. Returns 0 for degenerate inputs instead of raising."""
    if invested is None or invested <= 0 or years is None or years <= 0:
        return 0.0
    try:
        return ((final_value / invested) ** (1 / years) - 1) * 100
    except (ZeroDivisionError, ValueError):
        return 0.0


@st.cache_data(ttl=900)
def load_data(symbol, start, end):
    """Fetch historical closing prices.

    Uses Ticker().history() rather than yf.download() - the batch
    downloader has a known history of lagging or returning stale data,
    while the Ticker interface has proven more reliable for getting the
    most recent bars. Retries a couple of times since Yahoo's endpoint
    occasionally rate-limits or hiccups on shared/cloud IPs, and returns
    the real error message instead of silently swallowing it.
    """
    last_error = None
    for _ in range(3):
        try:
            hist = yf.Ticker(symbol).history(
                start=start,
                end=end + timedelta(days=1),  # 'end' is exclusive
                auto_adjust=True,
            )
            if hist is None or hist.empty:
                raise ValueError(f"No data returned for '{symbol}'. Check the ticker is valid.")
            closes = hist["Close"]
            if closes.index.tz is not None:
                closes.index = closes.index.tz_localize(None)
            return closes, None
        except Exception as e:
            last_error = str(e)
    return None, last_error


def get_buy_prices(prices, frequency):
    """Resample a price series down to the buy dates for a given frequency."""
    buy_days = prices.resample(FREQ_RESAMPLE[frequency]).first().dropna()
    return prices[prices.index.isin(buy_days.index)]


# =========================================================
# MODE 1: HISTORICAL BACKTEST (real market data)
# =========================================================
if mode == "📜 Historical Backtest":

    st.sidebar.header("Backtest Settings")
    ticker_symbol = st.sidebar.text_input("Ticker (e.g., SPY, AAPL, MSFT)", value="SPY").strip().upper()
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

    st.sidebar.subheader("Extra Comparisons")
    inflation_rate = st.sidebar.number_input(
        "Assumed Annual Inflation (%)", value=3.0, min_value=0.0, max_value=15.0, step=0.5,
        help="Used to show your portfolio's value in today's purchasing power."
    )
    compare_to_spy = st.sidebar.checkbox(
        "Compare to SPY benchmark", value=False,
        help="Runs the same DCA strategy on SPY for comparison. Ignored if your ticker is already SPY."
    )

    if st.sidebar.button("🔄 Force Refresh Data"):
        st.cache_data.clear()

    # --- GUARD: empty ticker ---
    if not ticker_symbol:
        st.warning("Enter a ticker symbol in the sidebar to begin.")
        st.stop()

    prices, fetch_error = load_data(ticker_symbol, start_date, end_date)

    if prices is not None and not prices.empty:
        if isinstance(prices, pd.DataFrame):
            prices = prices.iloc[:, 0]

        buy_prices = get_buy_prices(prices, frequency)

        # --- GUARD: no purchase dates in range ---
        if buy_prices.empty:
            st.error("No purchase dates fall within this date range. Try a wider range or a different frequency.")
            st.stop()

        # --- MATH ENGINE ---
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
        cagr = calc_cagr(portfolio_value, total_invested, years_elapsed)

        latest_date = prices.index[-1].strftime('%b %d, %Y')
        st.caption(f"📅 Price data available through **{latest_date}** (source: Yahoo Finance)")

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

        m7, m8, m9 = st.columns(3)
        m7.metric("Annualized Return (CAGR)", f"{cagr:.2f}%")

        # --- LUMP SUM COMPARISON ---
        lump_shares = total_invested / day_1_price
        lump_value = lump_shares * current_price
        lump_growth = ((lump_value / total_invested) - 1) * 100
        m8.metric(
            "Lump-Sum Alternative",
            f"${lump_value:,.2f}",
            f"{lump_growth - total_growth:+.1f} pts vs. DCA"
        )

        # --- INFLATION-ADJUSTED VALUE ---
        real_portfolio_value = portfolio_value / ((1 + inflation_rate / 100) ** years_elapsed)
        m9.metric(
            "Inflation-Adjusted Value",
            f"${real_portfolio_value:,.2f}",
            f"in today's purchasing power"
        )

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

            if lump_value > portfolio_value:
                st.warning(f"**Lump-sum would have won here:** investing all ${total_invested:,.0f} on Day 1 would be worth ${lump_value - portfolio_value:,.0f} more today.")
            else:
                st.success(f"**DCA came out ahead:** spreading out your buys beat a Day 1 lump sum by ${portfolio_value - lump_value:,.0f}.")

        # --- SPY BENCHMARK COMPARISON ---
        if compare_to_spy and ticker_symbol != "SPY":
            st.divider()
            st.subheader("⚖️ Benchmark: Same Strategy on SPY")
            spy_prices, spy_error = load_data("SPY", start_date, end_date)
            if spy_prices is not None and not spy_prices.empty:
                if isinstance(spy_prices, pd.DataFrame):
                    spy_prices = spy_prices.iloc[:, 0]
                spy_buy_prices = get_buy_prices(spy_prices, frequency)
                if not spy_buy_prices.empty:
                    spy_total_invested = len(spy_buy_prices) * invest_amount
                    spy_shares_held = (invest_amount / spy_buy_prices).sum()
                    spy_current_price = float(spy_prices.iloc[-1])
                    spy_portfolio_value = spy_shares_held * spy_current_price
                    spy_growth = ((spy_portfolio_value / spy_total_invested) - 1) * 100

                    b1, b2, b3 = st.columns(3)
                    b1.metric(f"{ticker_symbol} Value", f"${portfolio_value:,.2f}", f"{total_growth:.1f}%")
                    b2.metric("SPY Value (same $, same dates)", f"${spy_portfolio_value:,.2f}", f"{spy_growth:.1f}%")
                    diff = total_growth - spy_growth
                    b3.metric(
                        f"{ticker_symbol} vs. SPY",
                        f"{diff:+.1f} pts",
                        "outperformed" if diff > 0 else "underperformed"
                    )
                else:
                    st.info("Not enough SPY data in this date range to compare.")
            else:
                st.info(f"Couldn't load SPY data for comparison. {spy_error or ''}")

        # --- TRANSACTION LOG + CSV EXPORT ---
        st.divider()
        with st.expander("🧾 View Full Transaction Log"):
            shares_per_buy = invest_amount / buy_prices
            cum_shares = shares_per_buy.cumsum()
            cum_invested = np.arange(1, len(buy_prices) + 1) * invest_amount

            transactions_df = pd.DataFrame({
                "Date": buy_prices.index.strftime('%Y-%m-%d'),
                "Price": buy_prices.values.round(2),
                "Amount Invested": invest_amount,
                "Shares Bought": shares_per_buy.values.round(4),
                "Cumulative Shares": cum_shares.values.round(4),
                "Cumulative Invested": cum_invested,
            })

            st.dataframe(transactions_df, use_container_width=True, hide_index=True)

            csv_bytes = transactions_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download Transactions as CSV",
                data=csv_bytes,
                file_name=f"{ticker_symbol}_dca_transactions.csv",
                mime="text/csv",
            )

    else:
        st.error(f"Couldn't load data for **{ticker_symbol}**. {fetch_error or 'Try a different ticker or date range.'}")
        st.caption(
            "If this keeps happening, it's often Yahoo Finance temporarily rate-limiting requests "
            "from cloud servers. Try the **Force Refresh Data** button in the sidebar, or wait a "
            "minute and reload the page."
        )


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

    # Clamp pessimistic scenario so it can't imply losing more than 100% annually
    scenarios = {
        "Pessimistic": max(expected_return - band, -99.0),
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

    st.divider()
    with st.expander("🧾 View Full Projection Table"):
        display_df = proj_df.copy()
        display_df.index = display_df.index.strftime('%Y-%m-%d')
        display_df = display_df.round(2)
        st.dataframe(display_df, use_container_width=True)

        csv_bytes = display_df.to_csv().encode("utf-8")
        st.download_button(
            "⬇️ Download Projection as CSV",
            data=csv_bytes,
            file_name="dca_projection.csv",
            mime="text/csv",
        )
