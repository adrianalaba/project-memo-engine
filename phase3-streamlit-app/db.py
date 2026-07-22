import psycopg2
import streamlit as st
import pandas as pd
from datetime import date

@st.cache_resource
def init_connection():
    """Establishes thread-safe PostgreSQL connection via Streamlit secrets."""
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        port=st.secrets["postgres"]["port"],
        dbname=st.secrets["postgres"]["dbname"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"]
    )

def fetch_due_cards() -> pd.DataFrame:
    """Retrieves cards due on or before TODAY."""
    conn = init_connection()
    query = """
        SELECT c.card_id, c.subject_id, s.subject_name, c.front, c.back, 
               c.repetition_count, c.easiness_factor
        FROM fact_flashcards c
        JOIN dim_subjects s ON c.subject_id = s.subject_id
        WHERE c.next_review_date <= %s
        ORDER BY c.next_review_date ASC;
    """
    return pd.read_sql(query, conn, params=[date.today()])

def record_quiz_transaction(card_id: str, pass_fail: bool, ef_new: float, rep_new: int, next_date: date, response_time_ms: int):
    """Executes multi-statement transaction updating flashcard state and logging the review."""
    conn = init_connection()
    with conn.cursor() as cur:
        # Update flashcard SM-2 state
        cur.execute("""
            UPDATE fact_flashcards
            SET easiness_factor = %s, repetition_count = %s, next_review_date = %s
            WHERE card_id = %s;
        """, (ef_new, rep_new, next_date, card_id))
        
        # Insert log record into transaction ledger
        cur.execute("""
            INSERT INTO fact_quiz_logs (card_id, pass_fail, response_time_ms)
            VALUES (%s, %s, %s);
        """, (card_id, pass_fail, response_time_ms))
    conn.commit()

def fetch_analytics_logs() -> pd.DataFrame:
    """Fetches full log history for dashboard reporting."""
    conn = init_connection()
    query = """
        SELECT l.log_id, l.card_id, l.pass_fail, l.response_time_ms, l.timestamp,
               f.easiness_factor
        FROM fact_quiz_logs l
        JOIN fact_flashcards f ON l.card_id = f.card_id;
    """
    return pd.read_sql(query, conn)