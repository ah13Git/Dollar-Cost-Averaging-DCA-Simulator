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
st.caption("Backtest a DCA strategy against real historical market prices.")

st.sidebar.divider()

FREQ_RESAMPLE = {"Daily": "B", "Weekly": "W-MON", "Monthly": "MS"}

# Quote types worth showing in the search dropdown (drops things like OPTION)
SEARCHABLE_TYPES = {"EQUITY", "ETF", "INDEX", "MUTUALFUND", "CRYPTOCURRENCY", "CURRENCY", "FUTURE"}


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


@st.cache_data(ttl=3600)
def get_earliest_available_date(symbol):
    """Find the earliest date price history exists for a ticker.

    This is used as a stand-in for "when the stock went public": Yahoo
    Finance doesn't expose a reliable IPO date field, but the first bar
    of the full price history is effectively that date for equities.
    """
    try:
        hist = yf.Ticker(symbol).history(period="max", auto_adjust=True)
        if hist is not None and not hist.empty:
            first_date = hist.index[0]
            if first_date.tzinfo is not None:
                first_date = first_date.tz_localize(None)
            return first_date.date()
    except Exception:
        pass
    return None


@st.cache_data(ttl=3600)
def search_symbols(query):
    """Look up tickers by company name (or symbol) via Yahoo's search/autocomplete.

    Returns a list of dicts: symbol, name, exchange, type. Falls back to an
    empty list (never raises) so the caller can decide how to handle a miss.
    """
    query = (query or "").strip()
    if not query:
        return []
    try:
        raw = yf.Search(query, max_results=10).quotes
    except Exception:
        return []

    matches = []
    for r in raw:
        symbol = r.get("symbol")
        quote_type = (r.get("quoteType") or "").upper()
        if not symbol or (quote_type and quote_type not in SEARCHABLE_TYPES):
            continue
        matches.append({
            "symbol": symbol,
            "name": r.get("shortname") or r.get("longname") or symbol,
            "exchange": r.get("exchange", ""),
            "type": quote_type,
        })
    return matches


def get_buy_prices(prices, frequency):
    """Resample a price series down to the buy dates for a given frequency."""
    buy_days = prices.resample(FREQ_RESAMPLE[frequency]).first().dropna()
    return prices[prices.index.isin(buy_days.index)]


# =========================================================
# TICKER SEARCH (company name OR ticker symbol)
# =========================================================
st.sidebar.header("Backtest Settings")
search_query = st.sidebar.text_input(
    "Search by company name or ticker", value="Apple", help="e.g. 'Apple', 'AAPL', 'S&P 500', 'SPY'"
).strip()

ticker_symbol = ""
selected_name = ""

if search_query:
    matches = search_symbols(search_query)

    if matches:
        options = [f"{m['symbol']} — {m['name']} ({m['exchange']})" for m in matches]

        # If the query already IS a valid symbol among the results, default to it
        default_idx = 0
        for i, m in enumerate(matches):
            if m["symbol"].upper() == search_query.upper():
                default_idx = i
                break

        choice = st.sidebar.selectbox("Select the match you meant", options, index=default_idx)
        chosen = matches[options.index(choice)]
        ticker_symbol = chosen["symbol"].upper()
        selected_name = chosen["name"]
    else:
        # No matches from search — treat the raw input as a ticker symbol,
        # so power users can still type an obscure/exact symbol directly.
        st.sidebar.caption(f"No name matches for '{search_query}' — using it as a ticker symbol.")
        ticker_symbol = search_query.upper()

if ticker_symbol:
    label = f"**{ticker_symbol}**" + (f" · {selected_name}" if selected_name else "")
    st.sidebar.success(f"Using {label}")

invest_amount = st.sidebar.number_input("Amount per Interval ($)", value=100, min_value=1)

today = datetime.now().date()
fallback_min = datetime(1970, 1, 1).date()

earliest_date = get_earliest_available_date(ticker_symbol) if ticker_symbol else None
absolute_min = earliest_date or fallback_min
default_start = max(absolute_min, today - timedelta(days=365 * 10))

st.sidebar.subheader("Simulation Dates")
if earliest_date:
    st.sidebar.caption(f"📅 **{ticker_symbol}** price history starts **{earliest_date.strftime('%b %d, %Y')}**")
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


if st.sidebar.button("🔄 Force Refresh Data"):
    st.cache_data.clear()

# --- GUARD: empty ticker ---
if not ticker_symbol:
    st.warning("Search for a company or ticker in the sidebar to begin.")
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
