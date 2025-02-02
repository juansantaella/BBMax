import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import pytz

# Constants
CSV_FILE = "YieldMax_ETF_Symbols.csv"
TZ = pytz.UTC  # Ensure consistent timezone

# Step 1: Data Entry
def load_symbols():
    return pd.read_csv(CSV_FILE)

def display_sidebar():
    st.sidebar.image("BBMax_Logo_TM.jpg", use_container_width=True)

    symbols_data = load_symbols()
    symbol_options = [row['Symbol'] for _, row in symbols_data.iterrows()]

    select_all = st.sidebar.checkbox("Select All Symbols")

    selected_symbol = st.sidebar.selectbox(
        "Symbol", options=[None] + symbol_options, format_func=lambda x: x if x else "Type or select a symbol",
        disabled=select_all
    )

    # Replace lookback period slider with number of past dividends slider
    num_past_dividends = st.sidebar.slider("Number of Past Dividends", 1, 12, 6)
    budget_percentage = st.sidebar.slider("Budget Percentage (%)", 10, 60, 25)
    multiplier = st.sidebar.slider("Multiplier", 1, 12, 6)
    strike_adjustment = st.sidebar.slider("Strike Adjustment Amount", 1, 10, 4)

    if select_all:
        st.session_state["restored_symbol"] = selected_symbol
        selected_symbol = None
    else:
        if "restored_symbol" in st.session_state:
            selected_symbol = st.session_state.pop("restored_symbol")

    if not select_all and not selected_symbol:
        st.sidebar.error("Please select a symbol or check 'Select All Symbols'.")

    return selected_symbol, select_all, num_past_dividends, budget_percentage, multiplier, strike_adjustment

# Step 2: Fetch Dividend Data
@st.cache_data
def fetch_dividend_data(symbol, num_past_dividends):
    try:
        stock = yf.Ticker(symbol)
        dividends = stock.dividends

        if dividends.empty:
            st.error(f"No dividend data available for {symbol}.")
            return None, None, None, None

        # Ensure dividends are sorted by date (most recent first)
        dividends = dividends.sort_index(ascending=False)

        # Fetch the last N dividends
        last_n_dividends = dividends.head(num_past_dividends)

        if last_n_dividends.empty:
            st.error(f"Not enough dividend data available for {symbol}. Found {len(dividends)} dividends, but {num_past_dividends} requested.")
            return None, None, None, None

        # Debugging: Display dividend dates and amounts for the selected number of past dividends
        # t.write("### Dividend Data for Selected Number of Past Dividends")
        # st.write(last_n_dividends)

        total_dividends = last_n_dividends.sum()
        num_occurrences = len(last_n_dividends)
        last_dividend_date = last_n_dividends.index[0] if len(last_n_dividends) > 0 else None
        avg_dividend = total_dividends / num_occurrences if num_occurrences else 0

        return total_dividends, num_occurrences, last_dividend_date, avg_dividend
    except Exception as e:
        st.error(f"Failed to fetch dividend data for {symbol}: {str(e)}")
        return None, None, None, None

# Step 3: Fetch Put Option Data
@st.cache_data
def fetch_put_option_data(symbol, premium_budget, strike_price_threshold, avg_dividend, last_dividend_date, budget_percentage, dividend_frequency):
    try:
        stock = yf.Ticker(symbol)
        expiration_dates = stock.options

        opportunities = []
        for expiration in expiration_dates:
            option_chain = stock.option_chain(expiration)
            puts = option_chain.puts

            valid_puts = puts[(puts['strike'] >= strike_price_threshold) & (puts['lastPrice'] <= premium_budget)]

            for _, row in valid_puts.iterrows():
                expiration_date = pd.Timestamp(expiration, tz=TZ)
                total_days = (expiration_date - last_dividend_date).days

                # Use the symbol-specific dividend frequency instead of a hardcoded value
                future_occurrences = total_days // dividend_frequency
                estimated_dividends = future_occurrences * avg_dividend
                estimated_future_budget = estimated_dividends * (budget_percentage / 100)

                opportunities.append({
                    "Expiration Date": expiration_date.date(),
                    "Strike Price": row['strike'],
                    "Last Price": row['lastPrice'],
                    "Symbol": symbol,
                    "Highlight": "✅" if row['lastPrice'] <= estimated_future_budget else "",
                    "Future Events": f"{future_occurrences} occurrences, {estimated_dividends:.2f} est."
                })

        return pd.DataFrame(opportunities)
    except Exception as e:
        st.error(f"Failed to fetch put option data for {symbol}: {str(e)}")
        return pd.DataFrame()

# Step 5: Health Recovery Graph
def plot_health_recovery_graph(symbol, dividends, num_past_dividends):
    try:
        st.write(f"Processing Health Recovery Graph for symbol: {symbol}")

        # Fetch historical prices
        stock = yf.Ticker(symbol)
        historical = stock.history(period="max")

        # Ensure consistent timezone for historical data
        if historical.index.tz is None:
            historical.index = historical.index.tz_localize(pytz.UTC)
        else:
            historical.index = historical.index.tz_convert(pytz.UTC)

        # Ensure consistent timezone for dividend dates
        if dividends.index.tz is None:
            dividends.index = dividends.index.tz_localize(pytz.UTC)

        # Fetch the last N dividends
        dividends = dividends.sort_index(ascending=False).head(num_past_dividends)

        recovery_data = []
        for dividend_date in dividends.index:
            try:
                # Determine prior and current dividend dates
                current_date = dividend_date
                prior_date = dividends.index[dividends.index < dividend_date].max()

                if pd.isna(prior_date):
                    continue

                # Fetch P1, P2, and P3 based on your logic
                P1_date = prior_date - timedelta(days=2)
                P2_date = prior_date
                P3_date = current_date - timedelta(days=2)

                P1 = historical['Close'].asof(P1_date)
                P2 = historical['Close'].loc[historical.index >= P2_date].iloc[0]
                P3 = historical['Close'].asof(P3_date)

                # Skip if any of P1, P2, or P3 is None
                if pd.isna(P1) or pd.isna(P2) or pd.isna(P3):
                    st.warning(f"Missing market data for calculations near {dividend_date}")
                    continue

                # Determine recovery status
                if P3 > P1:
                    recovery_data.append(('Surpass', dividend_date, P3))
                elif P3 > P2:
                    recovery_data.append(('Recovered', dividend_date, P3))
                else:
                    recovery_data.append(('Decline', dividend_date, P3))
            except Exception as e:
                st.warning(f"Error processing data for {dividend_date}: {e}")
                continue

        # Plotting the graph
        fig, ax1 = plt.subplots()

        # Plot market price line if selected
        for status, date, P3_value in recovery_data:
            color = {"Surpass": "green", "Recovered": "orange", "Decline": "red"}[status]
            ax1.scatter(date, P3_value, color=color, label=f"{status}")

        ax1.set_xlabel("Date")
        ax1.set_ylabel("Market Price", color="blue")
        ax1.tick_params(axis='y', labelcolor="blue")
        ax1.tick_params(axis='x', rotation=45, labelsize=8)

        # Plot dividend amounts as a line if selected
        ax2 = ax1.twinx()
        ax2.set_ylabel("Dividend Amount", color="lightblue")
        ax2.scatter(dividends.index, dividends.values, color="lightblue", label="Dividends")
        ax2.plot(dividends.index, dividends.values, color="lightblue", linestyle="-", label="Dividend Line")
        ax2.tick_params(axis='y', labelcolor="lightblue")

        # Add legends and title
        fig.tight_layout()
        legend_handles = [
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='green', markersize=10, label='Surpass'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='orange', markersize=10, label='Recovered'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='red', markersize=10, label='Decline'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='lightblue', markersize=10, label='Dividends'),
        ]
        ax1.legend(handles=legend_handles, loc="upper left")
        plt.title(f"Health Recovery Graph for {symbol}")

        st.pyplot(fig)
        st.markdown("---")
        st.markdown("**Version 3.6.0 | Last Updated February 2, 2025 |  By: Sandeaux Bros**")
    except Exception as e:
        st.error(f"Error plotting health recovery graph: {str(e)}")

# Main Application
def main():
    st.title("YieldMax ETF Put Option Analyzer")

    symbol, select_all, num_past_dividends, budget_percentage, multiplier, strike_adjustment = display_sidebar()

    health_graph_disabled = not symbol or select_all
    search_opportunities_disabled = not symbol and not select_all

    health_graph_button = st.sidebar.button(
        "Health Recovery Graph",
        disabled=health_graph_disabled
    )
    search_opportunities_button = st.sidebar.button(
        "Search for Opportunities",
        disabled=search_opportunities_disabled
    )

    if health_graph_button:
        if symbol and not select_all:
            total_dividends, num_occurrences, last_dividend_date, avg_dividend = fetch_dividend_data(symbol, num_past_dividends)
            if total_dividends is None:
                return

            # Fetch the correct dividends Series
            stock = yf.Ticker(symbol)
            dividends = stock.dividends
            if dividends.empty:
                st.error(f"No dividend data available for {symbol}.")
                return

            plot_health_recovery_graph(symbol, dividends, num_past_dividends)
        else:
            st.error("Please select a single symbol and provide a valid number of past dividends.")

    if search_opportunities_button:
        with st.spinner("Processing..."):
            if select_all:
                # Fetch opportunities for all symbols
                symbols_data = load_symbols()
                all_opportunities = []

                for _, row in symbols_data.iterrows():
                    symbol = row['Symbol']
                    total_dividends, num_occurrences, last_dividend_date, avg_dividend = fetch_dividend_data(symbol, num_past_dividends)
                    if total_dividends is None:
                        continue

                    # Fetch the dividend frequency for the symbol from the CSV file
                    dividend_frequency = row['Frequency']

                    premium_budget = avg_dividend * (budget_percentage / 100) * multiplier
                    historical = yf.Ticker(symbol).history(period="1d")
                    if not historical.empty:
                        day_close_price = historical.iloc[-1]['Close']
                        strike_price_threshold = np.floor(day_close_price) - strike_adjustment
                    else:
                        st.warning(f"Close price data not available for {symbol}. Skipping...")
                        continue

                    opportunities = fetch_put_option_data(symbol, premium_budget, strike_price_threshold, avg_dividend, last_dividend_date, budget_percentage, dividend_frequency)
                    if not opportunities.empty:
                        all_opportunities.append(opportunities)

                # Combine and display results
                if all_opportunities:
                    combined_df = pd.concat(all_opportunities, ignore_index=True)
                    st.write("**Put Options Opportunities for All Symbols:**")
                    st.write(
                        combined_df.sort_values(by=["Expiration Date", "Strike Price"], ascending=[False, False])[[
                            "Expiration Date", "Strike Price", "Last Price", "Symbol", "Highlight", "Future Events"
                        ]]
                    )
                else:
                    st.error("No opportunities found for the selected criteria.")
            elif symbol:
                # Fetch opportunities for a single symbol
                total_dividends, num_occurrences, last_dividend_date, avg_dividend = fetch_dividend_data(symbol, num_past_dividends)
                if total_dividends is None:
                    return

                # Fetch the dividend frequency for the symbol from the CSV file
                symbols_data = load_symbols()
                dividend_frequency = symbols_data[symbols_data['Symbol'] == symbol]['Frequency'].values[0]

                premium_budget = avg_dividend * (budget_percentage / 100) * multiplier
                historical = yf.Ticker(symbol).history(period="1d")
                if not historical.empty:
                    day_close_price = historical.iloc[-1]['Close']
                    strike_price_threshold = np.floor(day_close_price) - strike_adjustment
                else:
                    st.error(f"Close price data not available for {symbol}.")
                    return

                opportunities = fetch_put_option_data(symbol, premium_budget, strike_price_threshold, avg_dividend, last_dividend_date, budget_percentage, dividend_frequency)

                # Display summary and results
                if not opportunities.empty:
                    st.write(f"### Summary for {symbol}")
                    st.write(f"Current Market Price: {day_close_price:.2f}")
                    st.write(f"Date of Last Dividend: {last_dividend_date.strftime('%Y-%m-%d')}")
                    st.write(f"Average Dividend: {avg_dividend:.2f}")
                    st.write(f"Premium Budget: {premium_budget:.2f}")
                    st.write(f"Opportunity Strike Price: {strike_price_threshold}")

                    st.write("**Put Options Opportunities:**")
                    st.write(
                        opportunities.sort_values(by=["Expiration Date", "Strike Price"], ascending=[False, False])[[
                            "Expiration Date", "Strike Price", "Last Price", "Symbol", "Highlight", "Future Events"
                        ]]
                    )
                    st.markdown("---")
                    st.markdown("**Version 3.6.0 | Last Updated February 2, 2025 |  By: Sandeaux Bros**")
                else:
                    st.error("No opportunities found for the selected symbol.")

if __name__ == "__main__":
    main()