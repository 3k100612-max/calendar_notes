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
    # Use consistent naming: NAME, USER, PASS, HOST, PORT
    config = {
        "DB_NAME": os.getenv("DB_NAME"),
        "DB_USER": os.getenv("DB_USER"),
        "DB_PASS": os.getenv("DB_PASS"),
        "DB_HOST": os.getenv("DB_HOST"),
        "DB_PORT": os.getenv("DB_PORT"),
    }

    # 1. Check if any variables are missing in Dokploy
    missing = [k for k, v in config.items() if not v]
    if missing:
        st.error(f"❌ Missing Environment Variables in Dokploy: {', '.join(missing)}")
        st.info("Please add these keys in the Dokploy 'Environment' tab.")
        return None

    try:
        return psycopg2.connect(
            dbname=config["DB_NAME"],
            user=config["DB_USER"],
            password=config["DB_PASS"],
            host=config["DB_HOST"],
            port=config["DB_PORT"],
            connect_timeout=5
        )
    except Exception as e:
        # 2. Show the real connection error (e.g., 'Connection Refused' or 'Invalid Password')
        st.error(f"❌ Database Connection Failed: {e}")
        return None

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
