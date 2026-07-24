import time
import streamlit as st
import pandas as pd
import plotly.express as px
from db import fetch_due_cards, record_quiz_transaction, fetch_analytics_logs, fetch_all_cards_df, fetch_subjects_dict, save_card_changes
from logic import calculate_sm2

st.set_page_config(page_title="Project Memo Engine", layout="wide")
st.title("⚡ Memo Engine: Spaced Repetition Platform")

# Initialize Session State Variables
if "queue" not in st.session_state:
    st.session_state.queue = fetch_due_cards()
if "card_idx" not in st.session_state:
    st.session_state.card_idx = 0
if "card_flipped" not in st.session_state:
    st.session_state.card_flipped = False
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

tab1, tab2 = st.tabs(["📚 Active Review Queue", "📊 Analytics Dashboard"])

# TAB 1: REVIEW QUEUE
with tab1:
    queue = st.session_state.queue
    
    if queue.empty or st.session_state.card_idx >= len(queue):
        st.success("🎉 Review queue completed for today!")
        if st.button("Reload Queue"):
            st.session_state.queue = fetch_due_cards()
            st.session_state.card_idx = 0
            st.rerun()
    else:
        card = queue.iloc[st.session_state.card_idx]
        st.caption(f"Subject: {card['subject_name']} | Card {st.session_state.card_idx + 1} of {len(queue)}")
        
        with st.container(border=True):
            st.markdown(f"### **Front:**\n{card['front']}")
            if st.session_state.card_flipped:
                st.divider()
                st.markdown(f"### **Back:**\n{card['back']}")

        if not st.session_state.card_flipped:
            if st.button("Show Answer", use_container_width=True):
                st.session_state.card_flipped = True
                st.rerun()
        else:
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("❌ Fail", use_container_width=True):
                    elapsed_ms = int((time.time() - st.session_state.start_time) * 1000)
                    ef_new, rep_new, next_date = calculate_sm2(
                        q=1, 
                        ef_prev=float(card['easiness_factor']), 
                        rep_prev=int(card['repetition_count'])
                    )
                    record_quiz_transaction(card['card_id'], False, ef_new, rep_new, next_date, elapsed_ms)
                    
                    st.session_state.card_flipped = False
                    st.session_state.card_idx += 1
                    st.session_state.start_time = time.time()
                    st.rerun()

            with col2:
                if st.button("✅ Pass", use_container_width=True, type="primary"):
                    elapsed_ms = int((time.time() - st.session_state.start_time) * 1000)
                    ef_new, rep_new, next_date = calculate_sm2(
                        q=4, 
                        ef_prev=float(card['easiness_factor']), 
                        rep_prev=int(card['repetition_count'])
                    )
                    record_quiz_transaction(card['card_id'], True, ef_new, rep_new, next_date, elapsed_ms)
                    
                    st.session_state.card_flipped = False
                    st.session_state.card_idx += 1
                    st.session_state.start_time = time.time()
                    st.rerun()

# TAB 2: ANALYTICS DASHBOARD
with tab2:
    logs_df = fetch_analytics_logs()
    
    if logs_df.empty:
        st.info("No transaction logs recorded yet. Complete reviews in the queue to generate data.")
    else:
        total_reviews = len(logs_df)
        retention_acc = (logs_df['pass_fail'].sum() / total_reviews) * 100
        avg_latency = logs_df['response_time_ms'].mean() / 1000.0

        m1, m2, m3 = st.columns(3)
        m1.metric("Historic Retention", f"{retention_acc:.1f}%")
        m2.metric("Total Reviews Logged", f"{total_reviews}")
        m3.metric("Avg Response Time", f"{avg_latency:.2f}s")


        # --- Tab Navigation ---
tab_study, tab_manage, tab_analytics = st.tabs(["📚 Study", "📝 Manage Cards", "📊 Analytics"])

with tab_manage:
    st.header("Card Management Grid")
    st.caption("Double-click cells to edit. Add new rows at the bottom or delete rows using the checkbox column.")

    # 1. Fetch Subject Map & Original Data
    subject_map = fetch_subjects_dict()
    subject_list = list(subject_map.keys())

    # Keep original dataset in session state for diffing during save
    if "original_cards_df" not in st.session_state:
        st.session_state["original_cards_df"] = fetch_all_cards_df()

    df_to_edit = st.session_state["original_cards_df"].copy()

    # 2. Render Spreadsheet Grid with Config
    edited_df = st.data_editor(
        df_to_edit,
        key="card_grid_editor",
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "card_id": None,      # Hidden from UI
            "subject_id": None,   # Hidden from UI
            "subject_name": st.column_config.SelectboxColumn(
                "Subject",
                help="Select the card subject category",
                options=subject_list,
                required=True,
            ),
            "front": st.column_config.TextColumn(
                "Front (Prompt)",
                help="Prompt or question displayed on front side",
                required=True,
                width="large"
            ),
            "back": st.column_config.TextColumn(
                "Back (Answer)",
                help="Answer or solution displayed on back side",
                required=True,
                width="large"
            ),
            "repetition_count": st.column_config.NumberColumn(
                "Reps",
                disabled=True,
                help="Spaced Repetition count (Auto-calculated)"
            ),
            "easiness_factor": st.column_config.NumberColumn(
                "EF Factor",
                disabled=True,
                format="%.2f",
                help="Easiness factor (Auto-calculated)"
            ),
            "next_review_date": st.column_config.DateColumn(
                "Next Review",
                disabled=True,
                format="YYYY-MM-DD"
            )
        }
    )

    # 3. Save Action Button
    st.divider()
    col1, col2 = st.columns([1, 4])

    with col1:
        if st.button("💾 Save All Changes", type="primary", use_container_width=True):
            success, message = save_card_changes(
                edited_df=edited_df, 
                original_df=st.session_state["original_cards_df"],
                subject_map=subject_map
            )

            if success:
                st.success(message)
                # Clear session state and cache to force reload fresh data from DB
                st.session_state.pop("original_cards_df", None)
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(message)

    with col2:
        if st.button("🔄 Discard Unsaved Changes"):
            st.session_state.pop("original_cards_df", None)
            st.rerun()