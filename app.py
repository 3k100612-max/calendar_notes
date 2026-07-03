import streamlit as st
import streamlit.components.v1 as components
import psycopg2
import json
import hashlib
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fpdf import FPDF
import io

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
    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, txt=f"Calendar Notes Report: {user_name}", ln=True, align='C')
    pdf.set_font("Arial", "", 10)
    pdf.cell(200, 10, txt=f"Range: {start_date} to {end_date}", ln=True, align='C')
    pdf.ln(10)
    
    # Filter notes in range
    sorted_dates = sorted(notes.keys())
    has_content = False
    
    for d_str in sorted_dates:
        if start_date <= d_str <= end_date:
            has_content = True
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, txt=f"Date: {d_str}", ln=True)
            pdf.set_font("Arial", "", 11)
            pdf.multi_cell(0, 7, txt=notes[d_str])
            pdf.ln(5)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(5)
            
    if not has_content:
        pdf.cell(0, 10, txt="No notes found for this period.", ln=True)
        
    return pdf.output()

# --- APP LOGIC ---
st.set_page_config(layout="wide", page_title="Secure Fluid Calendar")
init_db()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_id = None

# Handle URL parameters for editing
params = st.query_params
selected_date = params.get("edit_date", None)

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
                st.success("Account created! Go to Login.")

else:
    # --- SIDEBAR: USER & EXPORT ---
    st.sidebar.title(f"👤 {st.session_state.username}")
    
    # Export Section
    st.sidebar.markdown("---")
    st.sidebar.subheader("📄 Export Notes")
    export_type = st.sidebar.selectbox("Range", ["Daily", "Weekly", "Monthly"])
    
    notes = load_notes(st.session_state.user_id)
    
    # Date calculations for export
    today = datetime.now().date()
    if export_type == "Daily":
        s_date, e_date = str(today), str(today)
    elif export_type == "Weekly":
        s_date = str(today - timedelta(days=today.weekday()))
        e_date = str(today + timedelta(days=(6 - today.weekday())))
    else:
        s_date = str(today.replace(day=1))
        # Simple end of month logic
        e_date = str((today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1))

    pdf_bytes = generate_pdf(st.session_state.username, notes, s_date, e_date)
    st.sidebar.download_button(
        label=f"Download {export_type} PDF",
        data=pdf_bytes,
        file_name=f"notes_{export_type.lower()}_{s_date}.pdf",
        mime="application/pdf"
    )

    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()

    # --- MAIN INTERFACE: EDITOR & CALENDAR ---
    col1, col2 = st.columns([1, 3])

    with col1:
        if selected_date:
            st.subheader(f"📝 Edit: {selected_date}")
            current_content = notes.get(selected_date, "")
            new_note = st.text_area("Note Content", value=current_content, height=300)
            
            c_save, c_cancel = st.columns(2)
            if c_save.button("Save Note", use_container_width=True):
                save_note(st.session_state.user_id, selected_date, new_note)
                st.query_params.clear()
                st.rerun()
            if c_cancel.button("Cancel", use_container_width=True):
                st.query_params.clear()
                st.rerun()
        else:
            st.info("Click a date on the calendar to add or edit a multi-line note.")
            # Display today's note if it exists
            today_str = str(today)
            if today_str in notes:
                st.markdown(f"**Today's Note ({today_str}):**")
                st.write(notes[today_str])

    with col2:
        # Prepare events for FullCalendar
        events = []
        for d, content in notes.items():
            # Show first 30 chars in calendar, full note on click
            display_title = (content[:30] + '...') if len(content) > 30 else content
            events.append({
                "title": display_title,
                "start": d,
                "allDay": True,
                "backgroundColor": "#007bff",
                "borderColor": "#0056b3"
            })

        calendar_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <script src='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.js'></script>
            <style>
                #calendar {{ height: 80vh; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
                .fc-event {{ cursor: pointer; }}
            </style>
        </head>
        <body>
            <div id='calendar'></div>
            <script>
                document.addEventListener('DOMContentLoaded', function() {{
                    var calendarEl = document.getElementById('calendar');
                    var calendar = new FullCalendar.Calendar(calendarEl, {{
                        initialView: 'dayGridMonth',
                        headerToolbar: {{
                            left: 'prev,next today',
                            center: 'title',
                            right: 'dayGridMonth,timeGridWeek'
                        }},
                        events: {json.dumps(events)},
                        dateClick: function(info) {{
                            const url = new URL(window.parent.location.href);
                            url.searchParams.set('edit_date', info.dateStr);
                            window.parent.location.href = url.toString();
                        }},
                        eventClick: function(info) {{
                            const dateStr = info.event.startStr;
                            const url = new URL(window.parent.location.href);
                            url.searchParams.set('edit_date', dateStr);
                            window.parent.location.href = url.toString();
                        }}
                    }});
                    calendar.render();
                }});
            </script>
        </body>
        </html>
        """
        components.html(calendar_html, height=800)
