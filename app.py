import streamlit as st
import streamlit.components.v1 as components
import psycopg2
import json
import hashlib
import os
from dotenv import load_dotenv

# --- LOAD ENVIRONMENT VARIABLES ---
load_dotenv()

def get_connection():
    try:
        # Dokploy uses internal service names as hosts
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'calendarnotes-calendarnotes-qiqn5q'),      
            database=os.getenv('DB_NAME', 'cal_notes'), 
            user=os.getenv('DB_USER', 'user'),
            password=os.getenv('DB_PASSWORD'),          
            port=os.getenv('DB_PORT', '5432'),          
            connect_timeout=5
        )
        return conn
    except Exception as e:
        st.error(f"❌ Database Connection Error: {e}")
        
        # Debugging helper for Dokploy
        missing = []
        if not os.getenv('DB_HOST'): missing.append('DB_HOST')
        if not os.getenv('DB_PASSWORD'): missing.append('DB_PASSWORD')
        if missing:
            st.warning(f"Missing Env Vars in Dokploy: {', '.join(missing)}")
        return None

# --- NEW: DATABASE INITIALIZATION ---
# This creates your tables automatically if they were deleted
def init_db():
    conn = get_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Create users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                );
            """)
            # Create calendar_notes table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS calendar_notes (
                    user_id INTEGER REFERENCES users(id),
                    note_date DATE NOT NULL,
                    content TEXT,
                    PRIMARY KEY (user_id, note_date)
                );
            """)
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            st.error(f"❌ Setup Error: {e}")

# --- SECURITY ---
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def verify_user(username, password):
    conn = get_connection()
    if not conn: return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        if user and user[1] == hash_password(password):
            return user[0]
    except Exception as e:
        st.error(f"Login Error: {e}")
    finally:
        if conn: conn.close()
    return None

def create_user(username, password):
    conn = get_connection()
    if not conn: return False
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", 
                    (username, hash_password(password)))
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        st.error(f"Registration Error: {e}")
        return False
    finally:
        if conn: conn.close()

# --- DATA HANDLING ---
def load_notes(user_id):
    conn = get_connection()
    if not conn: return {}
    try:
        cur = conn.cursor()
        cur.execute("SELECT note_date, content FROM calendar_notes WHERE user_id = %s", (user_id,))
        rows = cur.fetchall()
        cur.close()
        return {str(row[0]): row[1] for row in rows}
    except Exception:
        return {}
    finally:
        if conn: conn.close()

def save_note(user_id, date_str, content):
    conn = get_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO calendar_notes (user_id, note_date, content) 
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, note_date) DO UPDATE SET content = EXCLUDED.content;
        """, (user_id, date_str, content))
        conn.commit()
        cur.close()
    except Exception as e:
        st.error(f"Save Error: {e}")
    finally:
        if conn: conn.close()

# --- APP LOGIC ---
st.set_page_config(layout="wide", page_title="Secure Fluid Calendar")

# Initialize Database on Startup
init_db()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_id = None

# --- LOGIN / REGISTRATION PAGE ---
if not st.session_state.authenticated:
    st.title("📅 Calendar Login")
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        u = st.text_input("Username", key="login_u")
        p = st.text_input("Password", type="password", key="login_p")
        if st.button("Login"):
            uid = verify_user(u, p)
            if uid:
                st.session_state.authenticated = True
                st.session_state.user_id = uid
                st.session_state.username = u
                st.rerun()
            else:
                st.error("Invalid credentials.")
                
    with tab2:
        new_u = st.text_input("New Username")
        new_p = st.text_input("New Password", type="password")
        if st.button("Register"):
            if create_user(new_u, new_p):
                st.success("Account created! Go to the Login tab.")

# --- MAIN CALENDAR INTERFACE ---
else:
    st.sidebar.title(f"User: {st.session_state.username}")
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.rerun()

    notes = load_notes(st.session_state.user_id)

    calendar_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.js'></script>
        <style>
            #calendar {{ height: 85vh; font-family: 'Segoe UI', sans-serif; }}
        </style>
    </head>
    <body>
        <div id='calendar'></div>
        <script>
            document.addEventListener('DOMContentLoaded', function() {{
                var calendarEl = document.getElementById('calendar');
                var notesData = {json.dumps(notes)};
                var events = Object.keys(notesData).map(date => ({{
                    title: notesData[date],
                    start: date,
                    allDay: true,
                    backgroundColor: '#007bff'
                }}));
                var calendar = new FullCalendar.Calendar(calendarEl, {{
                    initialView: 'dayGridMonth',
                    events: events,
                    dateClick: function(info) {{
                        let note = prompt("Note for " + info.dateStr, notesData[info.dateStr] || "");
                        if (note !== null) {{
                            window.parent.postMessage({{
                                type: 'streamlit:setComponentValue',
                                value: {{date: info.dateStr, note: note}}
                            }}, '*');
                        }}
                    }}
                }});
                calendar.render();
            }});
        </script>
    </body>
    </html>
    """

    result = components.html(calendar_html, height=750)

    if result:
        save_note(st.session_state.user_id, result['date'], result['note'])
        st.rerun()
