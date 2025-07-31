import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from pytrends.request import TrendReq
import pandas as pd
import time
import random 
from datetime import datetime, date
import matplotlib.pyplot as plt
import json

# Google Sheets Setup 
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

key_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)

client = gspread.authorize(creds)
spreadsheet = client.open("Consumer trends")
worksheet = spreadsheet.worksheet("Phrases")

# Caching to avoid repeated calls
@st.cache_data
def load_phrases():
    return worksheet.col_values(1)

# Load existing phrases from the sheet
existing_phrases = worksheet.col_values(1)
existing_phrases_lower = [p.lower() for p in existing_phrases]

# Streamlit UI
st.title("Consumer Trend Submission & Analysis")
st.write("Google Trends uses values from 0-100 for the number of searches including a particular phrase.")
st.write("These values are relative to a phrases' peak interest (set at 100).")
st.write("When graphed, the amount of interest in each phrase is then compared at an absolute level.")
st.write("It is unfortunately not possible to get absolute figures without comparison.")
st.subheader("Submit New Trend Phrase")

st.write("Enter a new phrase below to add it to the shared Google Sheet.")

new_phrase = st.text_input("New Phrase")

if st.button("Submit Phrase"):
    if not new_phrase.strip():
        st.warning("Please enter a phrase.")
    elif new_phrase.lower() in existing_phrases_lower:
        st.info("That phrase already exists in the sheet.")
    else:
        worksheet.append_row([new_phrase.strip()])
        st.cache_data.clear()
        st.success(f"Added phrase: {new_phrase.strip()}")


# retry-safe function to handle 429 errors
def safe_build_payload(pytrends, terms, retries=3):
    for attempt in range(retries):
        try:
            pytrends.build_payload(terms, cat=0, timeframe='today 1-m', geo='GB', gprop='')
            return True
        except Exception as e:
            if "429" in str(e):
                wait = 2 ** attempt + random.random()
                st.warning(f"Rate limited. Retrying in {wait:.1f} seconds...")
                time.sleep(wait)
            else:
                st.error(f"Trend fetch failed for batch: {e}")
                return False
    st.error("Too many retries — skipping this batch.")
    return False

# Button to trigger trend analysis
st.subheader("Phrase Analysis")
st.write("Ideally run this after lunch, otherwise today's data will likely be incomplete which can affect analysis")

if st.button("Analyse Phrases"):
    pytrends = TrendReq(hl='en-GB', tz=0)
    st.session_state["pytrends"] = pytrends
    all_phrases = [p for p in existing_phrases if p.strip()]
    batch_size = 5
    summary_rows = []

    for i in range(0, len(all_phrases), batch_size):
        batch = all_phrases[i:i+batch_size]
        if not safe_build_payload(pytrends, batch):
            continue

        try:
            pytrends.build_payload(batch, cat=0, timeframe='today 1-m', geo='GB', gprop='')
            data = pytrends.interest_over_time()

            if 'isPartial' in data.columns:
                data = data.drop(columns=['isPartial'])

            for term in batch:
                if term not in data.columns or len(data[term]) < 21:
                    summary_rows.append({
                        "Term": term,
                        "Status": "Insufficient Data",
                        "% Change": "N/A",
                        "Notes": "Not enough historical points",
                        "Interest Level": "N/A",
                        "Avg Interest": "N/A"
                    })
                    continue

                recent_3 = data[term].iloc[-3:]
                prev_11 = data[term].iloc[-14:-3]
                last_4 = data[term].iloc[-4:]

                recent_avg = recent_3.mean()
                prev_avg = prev_11.mean()

                if prev_avg == 0:
                    if recent_avg > 10:
                        status = "New Spike"
                        pct_change = "∞"
                        notes = "No prior interest"
                    else:
                        status = "-"
                        pct_change = "N/A"
                        notes = "Insufficient signal"
                else:
                    pct_change_val = ((recent_avg - prev_avg) / prev_avg) * 100
                    sustained_rise = (last_4 > prev_avg).sum() >= 3
                    sustained_drop = (last_4 < prev_avg).sum() >= 3

                    if pct_change_val >= 10:
                        status = "Spike"
                        notes = "Sustained increase" if sustained_rise else "Unsustained increase"
                    elif pct_change_val <= -10:
                        status = "Drop"
                        notes = "Sustained decrease" if sustained_drop else "Unsustained decrease"
                    else:
                        status = "-"
                        notes = ""

                    pct_change = f"{pct_change_val:.1f}%"

                # NEW: Calculate interest level based on full 30-day average
                avg_interest = data[term].mean()
                if avg_interest < 25:
                    interest_level = "Low"
                elif avg_interest < 50:
                    interest_level = "Moderate"
                elif avg_interest < 75:
                    interest_level = "High"
                else:
                    interest_level = "Extremely High"

                summary_rows.append({
                    "Term": term,
                    "Status": status,
                    "% Change": pct_change,
                    "Notes": notes,
                    "Interest Level": interest_level,
                    "Avg Interest": avg_interest
                })

        except Exception as e:
            for term in batch:
                summary_rows.append({
                    "Term": term,
                    "Status": "Error",
                    "% Change": "N/A",
                    "Notes": str(e),
                    "Interest Level": "N/A",
                    "Avg Interest": "N/A" 
                })

        time.sleep(5)  # Delay between batches

    # Display results in a table
    summary_df = pd.DataFrame(summary_rows)
    st.session_state["summary_df"] = summary_df
    st.subheader("Trend Change Summary")
    st.dataframe(summary_df)

    # Combined chart for phrases with a spike/drop

    st.subheader("Biggest changes")
    st.write("Phrases with the biggest movement (up to 5).")

    spiked_terms = summary_df[summary_df["Status"] != "-"]["Term"].tolist()

    # Filter summary_df for only spiked_terms
    spiked_df = summary_df[summary_df["Term"].isin(spiked_terms)].copy()

    # Convert % Change to sortable value (∞ = very large number)
    def parse_pct_change(val):
        if val == "∞":
            return float('inf')
        try:
            return float(val.strip('%'))
        except:
            return 0.0

    spiked_df["pct_val"] = spiked_df["% Change"].apply(parse_pct_change)

    # Sort by absolute movement (largest positive or negative)
    spiked_df["abs_change"] = spiked_df["pct_val"].abs()
    top_spiked = spiked_df.sort_values(by="abs_change", ascending=False).head(5)
    top_terms = top_spiked["Term"].tolist()

    if top_terms:
        if safe_build_payload(pytrends, top_terms): 
            try:
                data = pytrends.interest_over_time()
                if 'isPartial' in data.columns:
                    data = data.drop(columns=['isPartial'])

                fig, ax = plt.subplots(figsize=(12, 6))

                for term in top_terms:
                    if term in data.columns:
                        ax.plot(data.index, data[term], label=term, linewidth=2)

                ax.set_title("Phrases with Biggest Spike/Drop – Last 30 Days")
                ax.set_xlabel("Date")
                ax.set_ylabel("Search Interest")
                ax.grid(True)
                ax.legend()
                st.pyplot(fig)

            except Exception as e:
                st.warning(f"Could not generate combined chart: {e}")
    else:
        st.info("No phrases with spikes or drops to display in chart.")


    # Additional chart: All high-interest phrases (avg interest >= 50)
    st.subheader("Phrases with High or Extremely High Interest")
    st.write("Phrases with the highest average level of interest (up to 5).")

    high_df = summary_df[summary_df["Interest Level"].isin(["High", "Extremely High"])].copy()

    if not high_df.empty:
        high_df["Avg Interest"] = pd.to_numeric(high_df["Avg Interest"], errors="coerce")
        top_high_df = high_df.sort_values(by="Avg Interest", ascending=False).head(5)
        top_high_terms = top_high_df["Term"].tolist()

        if safe_build_payload(pytrends, top_high_terms):
            try:
                data = pytrends.interest_over_time()
                if 'isPartial' in data.columns:
                    data = data.drop(columns=['isPartial'])

                fig, ax = plt.subplots(figsize=(12, 6))

                for term in top_high_terms:
                    if term in data.columns:
                        ax.plot(data.index, data[term], label=term, linewidth=2)

                ax.set_title("Phrases with High or Extremely High Interest – Last 30 Days")
                ax.set_xlabel("Date")
                ax.set_ylabel("Search Interest")
                ax.grid(True)
                ax.legend()
                st.pyplot(fig)

            except Exception as e:
                st.warning(f"Could not generate high-interest chart: {e}")
    else:
        st.info("No phrases with high or extremely high interest to display.")

# Custom Phrase Trend Chart
st.subheader("Visualise Custom Phrase Trends")
st.write("Select up to 5 phrases to view their trends over the past month.")

custom_terms = st.multiselect(
    "Choose up to 5 phrases:",
    options=existing_phrases,
    max_selections=5
)

if custom_terms:
    # Try to use the cached data if it's been recently fetched
    try:
        # Only reuse summary_df if it exists and was just generated
        if "summary_df" in st.session_state and "pytrends" in st.session_state:
            summary_df = st.session_state["summary_df"]
            pytrends = st.session_state["pytrends"]
        else:
            st.warning("Please run 'Analyse Phrases' first.")
            st.stop()

        # Safe to continue
        if safe_build_payload(pytrends, custom_terms):
            try:
                pytrends.build_payload(custom_terms, cat=0, timeframe='today 1-m', geo='GB', gprop='')
                data = pytrends.interest_over_time()

                if 'isPartial' in data.columns:
                    data = data.drop(columns=['isPartial'])

                fig, ax = plt.subplots(figsize=(12, 6))
                for term in custom_terms:
                    if term in data.columns:
                        ax.plot(data.index, data[term], label=term, linewidth=2)

                ax.set_title("Selected Phrase Trends – Last 30 Days")
                ax.set_xlabel("Date")
                ax.set_ylabel("Search Interest")
                ax.grid(True)
                ax.legend()
                st.pyplot(fig)

            except Exception as e:
                st.warning(f"Could not generate custom trend chart: {e}")
    except Exception as err:
        st.warning("Trend data is not currently available. Please run 'Analyse Phrases' first or try again.")


# Choice to delete phrases
st.subheader("Delete Unwanted Phrases")

# Reload the latest list from the sheet
current_phrases = load_phrases()

phrase_to_delete = st.multiselect(
    "Select phrases to delete:",
    options=current_phrases
)

if st.button("Delete Selected Phrases"):
    if not phrase_to_delete:
        st.warning("Please select at least one phrase to delete.")
    else:
        # Get all rows in the sheet
        all_values = worksheet.get_all_values()

        for phrase in phrase_to_delete:
            # Find the row number (1-based index) and delete
            for idx, row in enumerate(all_values, start=1):
                if row and row[0].strip().lower() == phrase.strip().lower():
                    worksheet.delete_rows(idx)
                    break  # Only delete the first match
        
        st.cache_data.clear() 
        st.success("Selected phrases have been deleted.")



