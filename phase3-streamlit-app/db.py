import psycopg2
from psycopg2 import pool
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

def fetch_subjects_dict():
    """Returns a dict mapping subject_name -> subject_id and a list of names."""
    query = "SELECT subject_id, subject_name FROM dim_subjects ORDER BY subject_name;"
    conn = get_db_connection() # Assuming your connection wrapper function
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            subject_map = {row[1]: str(row[0]) for row in rows}
            return subject_map
    finally:
        release_db_connection(conn)


def fetch_all_cards_df():
    """
    Fetches all flashcards joined with subject names into a Pandas DataFrame.
    Indexed by card_id for fast edit/diff operations.
    """
    query = """
        SELECT 
            f.card_id::text AS card_id,
            s.subject_name,
            f.subject_id::text AS subject_id,
            f.front,
            f.back,
            f.repetition_count,
            f.easiness_factor,
            f.next_review_date
        FROM fact_flashcards f
        JOIN dim_subjects s ON f.subject_id = s.subject_id
        ORDER BY f.next_review_date ASC;
    """
    conn = get_db_connection()
    try:
        df = pd.read_sql(query, conn)
        return df
    finally:
        release_db_connection(conn)


def save_card_changes(edited_df, original_df, subject_map):
    """
    Diffs original_df against edited_df and executes SQL batch updates/inserts/deletes.
    `subject_map` is a dict mapping subject_name -> subject_id string.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Identify DELETIONS
            # Rows present in original_df but removed in edited_df
            orig_ids = set(original_df['card_id'].dropna())
            edited_ids = set(edited_df['card_id'].dropna())
            deleted_ids = orig_ids - edited_ids

            if deleted_ids:
                cur.execute(
                    "DELETE FROM fact_flashcards WHERE card_id = ANY(%s::uuid[]);",
                    (list(deleted_ids),)
                )

            # 2. Identify INSERTS
            # New rows added in st.data_editor won't have a card_id
            new_rows = edited_df[edited_df['card_id'].isna() | (edited_df['card_id'] == '')]
            
            insert_data = []
            for _, row in new_rows.iterrows():
                subj_id = subject_map.get(row['subject_name'])
                if subj_id and row['front'] and row['back']:
                    insert_data.append((subj_id, row['front'], row['back']))

            if insert_data:
                insert_query = """
                    INSERT INTO fact_flashcards (subject_id, front, back)
                    VALUES (%s, %s, %s);
                """
                cur.executemany(insert_query, insert_data)

            # 3. Identify UPDATES
            # Rows present in both datasets that have changes in front, back, or subject_name
            existing_edited = edited_df[edited_df['card_id'].isin(orig_ids)].set_index('card_id')
            existing_orig = original_df.set_index('card_id')

            update_data = []
            for card_id, row in existing_edited.iterrows():
                orig_row = existing_orig.loc[card_id]
                
                # Check if user modified key fields
                if (row['front'] != orig_row['front'] or 
                    row['back'] != orig_row['back'] or 
                    row['subject_name'] != orig_row['subject_name']):
                    
                    subj_id = subject_map.get(row['subject_name'])
                    if subj_id:
                        update_data.append((subj_id, row['front'], row['back'], card_id))

            if update_data:
                update_query = """
                    UPDATE fact_flashcards 
                    SET subject_id = %s, front = %s, back = %s
                    WHERE card_id = %s::uuid;
                """
                cur.executemany(update_query, update_data)

            conn.commit()
            return True, f"Successfully saved changes: {len(insert_data)} inserted, {len(update_data)} updated, {len(deleted_ids)} deleted."

    except Exception as e:
        conn.rollback()
        return False, f"Database Error: {str(e)}"
    finally:
        release_db_connection(conn)

# Initialize pooled connection using Streamlit secrets
@st.cache_resource
def init_connection_pool():
    # Pass secret key-values as keyword arguments to psycopg2
    db_config = st.secrets["postgres"]
    return psycopg2.pool.SimpleConnectionPool(
        minconn=1,
        maxconn=10,
        host=db_config["aws-0-ap-northeast-1.pooler.supabase.com"],
        port=db_config["5432"],
        dbname=db_config["postgres"],
        user=db_config["postgres.lweashhyaaakimafiegr"],
        password=db_config["Supabase!@#234"]
    )

db_pool = init_connection_pool()

def get_db_connection():
    """Gets a connection from the pool."""
    return db_pool.getconn()

def release_db_connection(conn):
    """Returns a connection back to the pool."""
    db_pool.putconn(conn)