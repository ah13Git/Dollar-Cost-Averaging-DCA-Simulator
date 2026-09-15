
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.6rem; }
    .stMetric { 
        background-color: rgba(28, 131, 225, 0.05); 
        padding: 10px; 
        border-radius: 8px; 
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
st.caption("Backtest a DCA strategy against real historical market prices.")

st.sidebar.divider()

PERIODS_PER_YEAR = {"Daily": 252, "Weekly": 52, "Monthly": 12}
FREQ_RESAMPLE = {"Daily": "B", "Weekly": "W-MON", "Monthly": "MS"}


    return None, last_error


@st.cache_data(ttl=3600)
def get_earliest_available_date(symbol):
    """Find the earliest date price history exists for a ticker.

    This is used as a stand-in for "when the stock went public": Yahoo
