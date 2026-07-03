import streamlit as st
import streamlit.components.v1 as components
import psycopg2
import json
import hashlib
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fpdf import FPDF

# --- LOAD ENVIRONMENT VARIABLES ---
load_dotenv()

def get_connection():
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'postgres'),      
            database=os.getenv('DB_NAME', 'cal_notes'), 
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'P12345'),          
            port=os.getenv('DB_PORT', '5432'),          
            connect_timeout=5
        )
        return conn
    except Exception as e:
        st.error(f"❌ Database Connection Error: {e}")
        return None

def init_db():
    conn = get_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                );
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

# --- PDF GENERATION ---
def generate_pdf(user_name, notes, start_date, end_date):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, txt=f"Calendar Notes: {user_name}", ln=True, align='C')
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 10, txt=f"Period: {start_date} to {end_date}", ln=True, align='C')
    pdf.ln(10)
    
    sorted_dates = sorted(notes.keys())
    found = False
    for d_str in sorted_dates:
        if str(start_date) <= d_str <= str(end_date):
            found = True
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 10, txt=f"Date: {d_str}", ln=True)
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 7, txt=str(notes[d_str]))
            pdf.ln(5)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(5)
    
    if not found:
        pdf.cell(0, 10, txt="No notes found for this period.", ln=True)
        
    return bytes(pdf.output())

# --- APP LOGIC ---
st.set_page_config(layout="wide", page_title="Kim's Calendar Notes")
init_db()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_id = None

params = st.query_params
url_date = params.get("edit_date", None)

if not st.session_state.authenticated:
    st.title("📅 Kim's Calendar Login")
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
                st.success("Account created! Go to Login.")
    
    # Copyright on Login Page
    st.markdown("---")
    st.markdown("<div style='text-align: center; color: grey;'>© 2026 timothymarkbal-e</div>", unsafe_allow_html=True)

else:
    # Sidebar
    st.sidebar.title(f"👤 {st.session_state.username}")
    notes = load_notes(st.session_state.user_id)
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("📄 PDF Export")
    export_range = st.sidebar.selectbox("Range", ["Daily", "Weekly", "Monthly"])
    
    today = datetime.now().date()
    if export_range == "Daily":
        s, e = today, today
    elif export_range == "Weekly":
        s = today - timedelta(days=today.weekday())
        e = today + timedelta(days=(6 - today.weekday()))
    else:
        s = today.replace(day=1)
        e = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    pdf_data = generate_pdf(st.session_state.username, notes, s, e)
    st.sidebar.download_button(f"Download {export_range} PDF", data=pdf_data, file_name=f"notes_{s}.pdf", mime="application/pdf")

    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()

    # Sidebar Copyright
    st.sidebar.markdown("---")
    st.sidebar.caption("© 2026 timothymarkbal-e")

    # Main UI
    col_edit, col_cal = st.columns([1, 3])

    with col_edit:
        st.subheader("📝 Note Editor")
        
        default_date = today
        if url_date:
            try:
                default_date = datetime.strptime(url_date, '%Y-%m-%d').date()
            except:
                pass
        
        active_date = st.date_input("Select Date to View/Edit", value=default_date)
        active_date_str = str(active_date)
        
        existing_text = notes.get(active_date_str, "")
        new_text = st.text_area(f"Notes for {active_date_str}", value=existing_text, height=400)
        
        if st.button("💾 Save Note", use_container_width=True):
            save_note(st.session_state.user_id, active_date_str, new_text)
            st.query_params.clear() 
            st.success("Saved!")
            st.rerun()
            
        if url_date and st.button("Clear Selection"):
            st.query_params.clear()
            st.rerun()

    with col_cal:
        events = []
        for d, content in notes.items():
            preview = content.split('\n')[0]
            events.append({
                "title": preview[:25] + "..." if len(preview) > 25 else preview,
                "start": d,
                "allDay": True,
                "backgroundColor": "#007bff"
            })

        calendar_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <script src='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.js'></script>
            <style>
                #calendar { height: 80vh; font-family: sans-serif; }
                .fc-event { cursor: pointer; }
            </style>
        </head>
        <body>
            <div id='calendar'></div>
            <script>
                document.addEventListener('DOMContentLoaded', function() {
                    var calendarEl = document.getElementById('calendar');
                    var calendar = new FullCalendar.Calendar(calendarEl, {
                        initialView: 'dayGridMonth',
                        events: __EVENTS__,
                        dateClick: function(info) {
                            try {
                                const url = new URL(window.parent.location.href);
                                url.searchParams.set('edit_date', info.dateStr);
                                window.parent.location.href = url.toString();
                            } catch (e) {
                                console.log("URL Update blocked.");
                            }
                        },
                        eventClick: function(info) {
                            try {
                                const url = new URL(window.parent.location.href);
                                url.searchParams.set('edit_date', info.event.startStr);
                                window.parent.location.href = url.toString();
                            } catch (e) {
                                console.log("URL Update blocked.");
                            }
                        }
                    });
                    calendar.render();
                });
            </script>
        </body>
        </html>
        """
        html_to_render = calendar_template.replace("__EVENTS__", json.dumps(events))
        components.html(html_to_render, height=800)

    # Main Footer Copyright
    st.markdown("---")
    st.markdown("<div style='text-align: center; color: grey;'>© 2026 timothymarkbal-e</div>", unsafe_allow_html=True)
