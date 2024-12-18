import streamlit as st
import pandas as pd
import yfinance as yf

# --- Function to Fetch Dividends from Excel ---
def fetch_dividends_from_excel(symbol, months, file_path="EFT Put Option Analyzer - Data.xlsx"):
    """
    Fetches dividends for a given symbol from an Excel file.

    Args:
        symbol (str): ETF symbol (e.g., TSLY).
        months (int): Number of months for dividend calculation.
        file_path (str): Path to the Excel file.

    Returns:
        float: Average monthly dividend.
    """
    try:
        df = pd.read_excel(file_path)
        df.columns = df.columns.str.strip()  # Clean column names
        filtered_df = df[df["Symbol"] == symbol]
        filtered_df = filtered_df.sort_values(by="Ex Date", ascending=False)
        recent_dividends = filtered_df["Dividend"].iloc[:months]
        avg_dividend = recent_dividends.mean()
        return avg_dividend
    except Exception as e:
        st.error(f"Error fetching dividends from Excel: {e}")
        return 0.0

# --- Function to Get Put Options Data ---
def fetch_put_options(symbol):
    """
    Fetches put options data from Yahoo Finance.

    Args:
        symbol (str): ETF symbol.

    Returns:
        DataFrame: Put options data.
    """
    try:
        ticker = yf.Ticker(symbol)
        puts_data = []
        for exp in ticker.options:
            chain = ticker.option_chain(exp)
            puts = chain.puts
            puts['expiration'] = exp
            puts_data.append(puts)
        return pd.concat(puts_data)
    except Exception as e:
        st.error(f"Error fetching put options: {e}")
        return pd.DataFrame()

# --- Function to Load Symbols from Excel ---
def load_symbols_from_excel(file_path="EFT Put Option Analyzer - Data.xlsx"):
    """
    Loads unique symbols from the Excel file.

    Args:
        file_path (str): Path to the Excel file.

    Returns:
        List: List of unique symbols.
    """
    try:
        df = pd.read_excel(file_path)
        symbols = df["Symbol"].unique().tolist()
        return symbols
    except Exception as e:
        st.error(f"Error loading symbols from Excel: {e}")
        return ["TSLY"]  # Default fallback

# --- Streamlit App ---
st.title("YieldMax ETF Put Option Analyzer")

# --- User Inputs ---
st.sidebar.header("User Input")
available_symbols = load_symbols_from_excel()  # Dynamically load symbols
symbol = st.sidebar.selectbox("Select YieldMax ETF Symbol", available_symbols)
months = st.sidebar.number_input("Number of Months for Dividend Calculation", 1, 12, 6)
max_percentage = st.sidebar.slider("Max % for Put Premium", 10, 50, 25)
months_ahead = st.sidebar.number_input("Number of Future Months to Include", 1, 12, 4)
min_strike_price = st.sidebar.number_input(
    "Lowest Strike Price Threshold", 
    min_value=0, 
    step=1, 
    value=0
)

# --- Data Retrieval and Calculations ---
if st.sidebar.button("Analyze"):
    with st.spinner("Fetching data..."):
        # Fetch dividends from Excel
        avg_dividend = fetch_dividends_from_excel(symbol, months)
        if avg_dividend == 0.0:
            st.warning("Unable to calculate dividends. Check the ETF symbol or Excel file.")
        else:
            # Calculate max premium allowed (including future months)
            total_max_premium = avg_dividend * (max_percentage / 100) * months_ahead

            # Fetch put options
            puts = fetch_put_options(symbol)
            try:
                current_price = yf.Ticker(symbol).history(period="1d")['Close'].iloc[-1]
            except:
                current_price = 0.0
                st.error("Error fetching current price.")

            # Filter options
            filtered_puts = puts[
                (puts['strike'] >= min_strike_price) &
                (puts['lastPrice'] <= total_max_premium)
            ]

            # Reorder Columns: Expiration, Strike Price, Premium (Last Price)
            filtered_puts = filtered_puts[['expiration', 'strike', 'lastPrice']]
            filtered_puts = filtered_puts.rename(
                columns={
                    "expiration": "Expiration Date",
                    "strike": "Strike Price",
                    "lastPrice": "Premium"
                }
            )

            # Convert strike price to integer
            filtered_puts['Strike Price'] = filtered_puts['Strike Price'].astype(int)

            # Format 'Premium' to 4 decimal places
            filtered_puts['Premium'] = filtered_puts['Premium'].apply(lambda x: f"{x:.4f}")

            # Reset the index to drop the unwanted index column
            filtered_puts = filtered_puts.reset_index(drop=True)

            # Apply custom CSS for table styling to center content
            st.markdown(
                """
                <style>
                table {
                    width: 100% !important;
                    border-collapse: collapse;
                }
                th, td {
                    text-align: center !important;
                    font-size: 16px !important;
                    padding: 10px !important;
                    border: 1px solid #ddd !important;
                }
                th {
                    background-color: #f4f4f4 !important;
                    font-weight: bold !important;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            # Display Results
            st.write(f"**Average Monthly Dividend:** ${avg_dividend:.2f}")
            st.write(f"**Max Premium Allowed (including {months_ahead} months):** ${total_max_premium:.4f}")
            st.write(f"**Current Price:** ${current_price:.2f}")

            if not filtered_puts.empty:
                st.subheader("Filtered Put Options:")
                st.table(filtered_puts)
            else:
                st.warning("No suitable put options found.")
