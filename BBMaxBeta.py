import streamlit as st
import pandas as pd
import yfinance as yf
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

# --- Predefined YieldMax Groups ---
YIELDMAX_GROUPS = {
    "Group A": ["TSLY", "CRSH", "GOOY", "YBIT", "OARK", "XOMO", "SNOY", "TSMY", "FEAT", "FIVY"],
    "Group B": ["NVDY", "DIPS", "FBY", "GDXY", "BABO", "JPMO", "MRNY", "PLTY", "MARO"],
    "Group C": ["CONY", "FIAT", "MSFO", "AMDY", "NFLY", "ABNY", "PYPY", "ULTY"],
    "Group D": ["MSTY", "YQQQ", "AMZY", "APLY", "AIYY", "DISO", "SQY", "SMCY"]
}

# Flatten list with group headers
grouped_symbols = []
for group_name, symbols in YIELDMAX_GROUPS.items():
    grouped_symbols.append(f"--- {group_name} ---")
    grouped_symbols.extend(symbols)

# --- Function to Fetch Dividends from Yahoo Finance ---
def fetch_dividends_from_yfinance(symbol, num_dividends):
    try:
        logger.info(f"Fetching dividends for {symbol}")
        ticker = yf.Ticker(symbol)
        dividends = ticker.dividends

        if dividends.empty:
            return 0.0, None

        # Calculate average of the last `num_dividends`
        recent_dividends = dividends.iloc[-num_dividends:]
        avg_dividend = recent_dividends.mean()
        last_dividend_date = dividends.index[-1].tz_localize(None).normalize()
        logger.info(f"Fetched dividends for {symbol}: Avg: {avg_dividend}, Last Date: {last_dividend_date}")
        return avg_dividend, last_dividend_date
    except Exception as e:
        st.error(f"Error fetching dividends: {e}")
        logger.error(f"Error fetching dividends for {symbol}: {e}")
        return 0.0, None

# --- Function to Fetch Put Options ---
def fetch_put_options(symbol):
    try:
        logger.info(f"Fetching put options for {symbol}")
        ticker = yf.Ticker(symbol)
        puts_data = []
        for exp in ticker.options:
            chain = ticker.option_chain(exp)
            puts = chain.puts
            puts['expiration'] = pd.to_datetime(exp).tz_localize(None).normalize()
            puts_data.append(puts)
        logger.info(f"Fetched put options for {symbol}")
        return pd.concat(puts_data)
    except Exception as e:
        st.error(f"Error fetching put options: {e}")
        logger.error(f"Error fetching put options for {symbol}: {e}")
        return pd.DataFrame()

# --- Streamlit App ---
st.title("YieldMax ETF Put Option Analyzer")

st.write("**Note:** Select a specific symbol to analyze or leave the selection empty to analyze all symbols. If the 'Analyze All Symbols' checkbox is selected, the search and select fields will appear empty.")

# --- User Inputs ---
st.sidebar.header("User Input")

# Remember last selected symbol
if "last_selected_symbol" not in st.session_state:
    st.session_state.last_selected_symbol = None

# Dynamic search box
search_input = st.sidebar.text_input("Search for a symbol", "").upper()

# Filter symbols based on search input
filtered_symbols = [
    symbol for symbol in grouped_symbols if search_input in symbol and not symbol.startswith("---")
] if search_input else grouped_symbols

# Select symbol from filtered options
selected_symbol = st.sidebar.selectbox(
    "Select YieldMax ETF Symbol",
    filtered_symbols,
    index=filtered_symbols.index(st.session_state.last_selected_symbol) if st.session_state.last_selected_symbol in filtered_symbols else 0,
)

# Update last selected symbol
if selected_symbol and not selected_symbol.startswith("---"):
    st.session_state.last_selected_symbol = selected_symbol

# Option to analyze all symbols
analyze_all = st.sidebar.checkbox("Analyze All Symbols")

# User input for dividend calculation
num_dividends = st.sidebar.slider("Number of Past Dividends to Include", 1, 12, 6)
future_periods = st.sidebar.number_input("Number of Future Periods to Evaluate", 1, 12, 3)
percentage_for_single_premium = st.sidebar.slider("Percentage of Dividend for Single Put Premium", 1, 100, 25)
strike_price_relative = st.sidebar.number_input("Strike Price Adjustment (Integer Below Stock Price)", 0, 100, 5)

# Fetch and analyze data
def analyze_symbol(symbol):
    try:
        logger.info(f"Analyzing {symbol}")
        avg_dividend, last_dividend_date = fetch_dividends_from_yfinance(symbol, num_dividends)
        if avg_dividend == 0:
            return None, None

        max_budget_for_single_put_premium = avg_dividend * (percentage_for_single_premium / 100)
        max_budget_for_extended_put_premium = max_budget_for_single_put_premium * future_periods

        ticker = yf.Ticker(symbol)
        current_price = ticker.history(period="1d")['Close'].iloc[-1]
        logger.info(f"Current price for {symbol}: {current_price}")

        strike_price_threshold = max(1, int(current_price) - strike_price_relative)
        logger.info(f"Strike price threshold for {symbol}: {strike_price_threshold}")

        puts = fetch_put_options(symbol)
        if puts.empty:
            return None, None

        filtered_by_strike = puts[puts['strike'].astype(float) >= strike_price_threshold]
        filtered_by_last_price = filtered_by_strike[filtered_by_strike['lastPrice'].astype(float) <= max_budget_for_extended_put_premium]

        filtered_puts = filtered_by_last_price

        if filtered_puts.empty:
            return None, None

        filtered_puts = filtered_puts[['expiration', 'strike', 'lastPrice']].rename(
            columns={"expiration": "Expiration Date", "strike": "Strike Price", "lastPrice": "Last Price"}
        )
        filtered_puts['Symbol'] = symbol

        filtered_puts['Last Price'] = pd.to_numeric(filtered_puts['Last Price'], errors='coerce')
        filtered_puts['Expiration Date'] = pd.to_datetime(filtered_puts['Expiration Date'], errors='coerce').dt.normalize()

        filtered_puts = filtered_puts.dropna(subset=['Last Price', 'Expiration Date'])

        sorted_puts = filtered_puts.sort_values(by=['Expiration Date', 'Last Price'], ascending=[False, False])

        sorted_puts['Expiration Date'] = sorted_puts['Expiration Date'].dt.strftime('%Y-%m-%d')

        # Adjust highlight logic to account for evaluation date
        today = pd.Timestamp.now().normalize()
        logger.info(f"Today's date: {today}")
        next_expected_dividend_date = last_dividend_date + pd.Timedelta(days=28)
        logger.info(f"Next expected dividend date: {next_expected_dividend_date}")

        # If today is beyond the next expected dividend, adjust the start point
        if today >= next_expected_dividend_date:
            while next_expected_dividend_date <= today:
                next_expected_dividend_date += pd.Timedelta(days=28)
        next_expected_dividend_date = next_expected_dividend_date.tz_localize(None)  # Ensure tz-naive
        logger.info(f"Adjusted next expected dividend date: {next_expected_dividend_date}")

        highlight_date = next_expected_dividend_date + pd.Timedelta(days=28 * (future_periods - 1))
        logger.info(f"Highlight date: {highlight_date}")

        sorted_puts['Highlight'] = sorted_puts['Expiration Date'].apply(
            lambda x: "✅" if pd.to_datetime(x) >= highlight_date else ""
        )

        details = (
            f"Average Dividend: ${avg_dividend:.4f}\n"
            f"Last Dividend Date: {last_dividend_date.strftime('%Y-%m-%d')}\n"
            f"Max Budget for Single Premium: ${max_budget_for_single_put_premium:.4f}\n"
            f"Max Budget for Extended Premium: ${max_budget_for_extended_put_premium:.4f}\n"
            f"Current Price: ${current_price:.4f}\n"
            f"Strike Price Threshold: ${strike_price_threshold:.4f}"
        )
        return sorted_puts.reset_index(drop=True), details
    except Exception as e:
        st.error(f"Error analyzing {symbol}: {e}")
        logger.error(f"Error analyzing {symbol}: {e}")
        return None, None

if st.sidebar.button("Search for Opportunities"):
    logger.info("Search button clicked.")
    if (not selected_symbol or selected_symbol.startswith("---")) and not analyze_all:
        st.warning("Please select a Symbol or check the box for All Symbols.")
    elif analyze_all:
        all_results = []
        logger.info("Analyzing all symbols.")
        with st.spinner("Analyzing all symbols. This may take a moment..."):
            for group_name, symbols in YIELDMAX_GROUPS.items():
                for symbol in symbols:
                    result, _ = analyze_symbol(symbol)
                    if result is not None:
                        highlighted_rows = result[result['Highlight'] == "✅"]
                        if not highlighted_rows.empty:
                            all_results.append(highlighted_rows)
        if all_results:
            st.subheader("Consolidated Opportunities (Highlighted Only)")
            consolidated_results = pd.concat(all_results).sort_values(by=["Expiration Date", "Last Price"], ascending=[False, False]).reset_index(drop=True)
            st.table(consolidated_results)
            st.write("*Highlight (✅): Indicates opportunities where the expiration date is at or beyond the calculated future dividend period based on current date and number of future periods indicated by the user.")
        else:
            st.warning("No highlighted opportunities found for any symbols.")
    else:
        logger.info(f"Analyzing selected symbol: {selected_symbol}")
        with st.spinner(f"Analyzing {selected_symbol}. Please wait..."):
            result, details = analyze_symbol(selected_symbol)
            if result is not None:
                st.subheader(f"Opportunities for {selected_symbol}:")
                st.text(details)
                st.table(result)
                st.write("*Highlight (✅): Indicates opportunities where the expiration date is at or beyond the calculated future dividend period based on user input.")

logger.info("Streamlit app started. Press Ctrl+C to stop.")
