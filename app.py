import os
import re
import html
import json
import hashlib
import secrets
from datetime import datetime, timedelta

import psycopg2
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from fpdf import FPDF


# =========================================================
# CONFIGURATION
# =========================================================

load_dotenv()

st.set_page_config(
    page_title="Calendar Notes",
    page_icon="📝",
    layout="wide"
)


# =========================================================
# CUSTOM CSS
# =========================================================

st.markdown(
    """
    <style>
    .note-preview {
        min-height: 300px;
        padding: 20px;
        border: 1px solid #d0d7de;
        border-radius: 12px;
        background-color: white;
        color: #222222;
        line-height: 1.8;
        font-size: 16px;
        overflow-wrap: anywhere;
    }

    mark {
        padding: 3px 6px;
        border-radius: 5px;
    }

    mark.yellow {
        background-color: #fff176;
    }

    mark.red {
        background-color: #ff9e9e;
    }

    mark.green {
        background-color: #a5d6a7;
    }

    .stTextArea textarea {
        font-size: 16px;
        line-height: 1.6;
    }

    .app-footer {
        text-align: center;
        color: grey;
        margin-top: 20px;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# DATABASE
# =========================================================

def get_connection():
    try:
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "postgres"),
            database=os.getenv("DB_NAME", "cal_notes"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "P12345"),
            port=os.getenv("DB_PORT", "5432"),
            connect_timeout=5
        )
    except Exception as error:
        st.error(f"Database connection error: {error}")
        return None


def init_db():
    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS calendar_notes (
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                note_date DATE NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (user_id, note_date)
            );
            """
        )

        conn.commit()
        cur.close()
        conn.close()

    except Exception as error:
        st.error(f"Database setup error: {error}")


# =========================================================
# PASSWORD SECURITY
# =========================================================

def hash_password(password):
    salt = secrets.token_bytes(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        200_000
    )

    return f"{salt.hex()}${password_hash.hex()}"


def verify_password(password, stored_password):
    try:
        salt_hex, hash_hex = stored_password.split("$")

        salt = bytes.fromhex(salt_hex)

        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            200_000
        )

        return secrets.compare_digest(
            password_hash.hex(),
            hash_hex
        )

    except Exception:
        return False


def verify_user(username, password):
    conn = get_connection()

    if not conn:
        return None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, password_hash
            FROM users
            WHERE username = %s
            """,
            (username.strip(),)
        )

        user = cur.fetchone()

        cur.close()

        if user and verify_password(password, user[1]):
            return user[0]

    except Exception as error:
        st.error(f"Login error: {error}")

    finally:
        conn.close()

    return None


def create_user(username, password):
    username = username.strip()

    if not username:
        st.error("Username cannot be empty.")
        return False

    if len(password) < 6:
        st.error("Password must contain at least 6 characters.")
        return False

    conn = get_connection()

    if not conn:
        return False

    try:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO users (username, password_hash)
            VALUES (%s, %s)
            """,
            (username, hash_password(password))
        )

        conn.commit()
        cur.close()

        return True

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        st.error("That username already exists.")
        return False

    except Exception as error:
        conn.rollback()
        st.error(f"Registration error: {error}")
        return False

    finally:
        conn.close()


# =========================================================
# NOTES
# =========================================================

def load_notes(user_id):
    conn = get_connection()

    if not conn:
        return {}

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT note_date, content
            FROM calendar_notes
            WHERE user_id = %s
            ORDER BY note_date
            """,
            (user_id,)
        )

        rows = cur.fetchall()
        cur.close()

        return {
            str(note_date): content
            for note_date, content in rows
        }

    except Exception as error:
        st.error(f"Could not load notes: {error}")
        return {}

    finally:
        conn.close()


def save_note(user_id, date_string, content):
    conn = get_connection()

    if not conn:
        return False

    try:
        cur = conn.cursor()

        if content.strip():
            cur.execute(
                """
                INSERT INTO calendar_notes
                    (user_id, note_date, content)
                VALUES
                    (%s, %s, %s)
                ON CONFLICT (user_id, note_date)
                DO UPDATE SET content = EXCLUDED.content
                """,
                (user_id, date_string, content)
            )
        else:
            cur.execute(
                """
                DELETE FROM calendar_notes
                WHERE user_id = %s
                AND note_date = %s
                """,
                (user_id, date_string)
            )

        conn.commit()
        cur.close()

        return True

    except Exception as error:
        conn.rollback()
        st.error(f"Could not save note: {error}")
        return False

    finally:
        conn.close()


def delete_note(user_id, date_string):
    conn = get_connection()

    if not conn:
        return False

    try:
        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM calendar_notes
            WHERE user_id = %s
            AND note_date = %s
            """,
            (user_id, date_string)
        )

        conn.commit()
        cur.close()

        return True

    except Exception as error:
        conn.rollback()
        st.error(f"Could not delete note: {error}")
        return False

    finally:
        conn.close()


# =========================================================
# NOTE FORMATTING
# =========================================================

def clean_markup(text):
    """
    Removes formatting markers before exporting to PDF.
    """

    text = re.sub(r"==(.+?)==", r"\1", text)
    text = re.sub(r"!!(.+?)!!", r"\1", text)
    text = re.sub(r"##(.+?)##", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)

    return text


def format_note_html(text):
    """
    Supported formatting:

    **text** -> bold
    ==text== -> yellow highlight
    !!text!! -> red highlight
    ##text## -> green highlight
    """

    safe_text = html.escape(text)

    safe_text = re.sub(
        r"\*\*(.+?)\*\*",
        r"<strong>\1</strong>",
        safe_text
    )

    safe_text = re.sub(
        r"==(.+?)==",
        r'<mark class="yellow">\1</mark>',
        safe_text
    )

    safe_text = re.sub(
        r"!!(.+?)!!",
        r'<mark class="red">\1</mark>',
        safe_text
    )

    safe_text = re.sub(
        r"##(.+?)##",
        r'<mark class="green">\1</mark>',
        safe_text
    )

    return safe_text.replace("\n", "<br>")


def add_highlight(text, color):
    if not text.strip():
        return text

    markers = {
        "Yellow": ("==", "=="),
        "Red": ("!!", "!!"),
        "Green": ("##", "##")
    }

    start_marker, end_marker = markers[color]

    return f"{start_marker}{text}{end_marker}"


def remove_formatting(text):
    return clean_markup(text)


# =========================================================
# PDF EXPORT
# =========================================================

def generate_pdf(username, notes, start_date, end_date):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(
        0,
        10,
        f"Calendar Notes: {username}",
        new_x="LMARGIN",
        new_y="NEXT",
        align="C"
    )

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        10,
        f"Period: {start_date} to {end_date}",
        new_x="LMARGIN",
        new_y="NEXT",
        align="C"
    )

    pdf.ln(8)

    found_notes = False

    for date_string in sorted(notes.keys()):
        if str(start_date) <= date_string <= str(end_date):
            found_notes = True

            pdf.set_fill_color(225, 235, 250)
            pdf.set_font("Helvetica", "B", 12)

            pdf.cell(
                0,
                9,
                f"Date: {date_string}",
                fill=True,
                new_x="LMARGIN",
                new_y="NEXT"
            )

            pdf.set_font("Helvetica", "", 11)

            note_text = clean_markup(str(notes[date_string]))

            # Helvetica does not support every Unicode character.
            note_text = (
                note_text
                .encode("latin-1", "replace")
                .decode("latin-1")
            )

            pdf.multi_cell(
                0,
                7,
                note_text
            )

            pdf.ln(4)

            pdf.set_draw_color(180, 180, 180)
            pdf.line(
                10,
                pdf.get_y(),
                200,
                pdf.get_y()
            )

            pdf.ln(5)

    if not found_notes:
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(
            0,
            10,
            "No notes found for this period."
        )

    return bytes(pdf.output())


# =========================================================
# CALENDAR
# =========================================================

def create_calendar(notes):
    events = []

    for date_string, content in notes.items():
        preview = content.split("\n")[0]
        preview = clean_markup(preview).strip()

        if len(preview) > 25:
            preview = preview[:25] + "..."

        events.append(
            {
                "title": preview or "Note",
                "start": date_string,
                "allDay": True,
                "backgroundColor": "#007bff",
                "borderColor": "#0056b3"
            }
        )

    calendar_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.js"></script>

        <style>
            body {
                margin: 0;
                font-family: Arial, sans-serif;
            }

            #calendar {
                height: 80vh;
            }

            .fc-event {
                cursor: pointer;
            }
        </style>
    </head>

    <body>
        <div id="calendar"></div>

        <script>
            document.addEventListener("DOMContentLoaded", function() {
                const calendarElement =
                    document.getElementById("calendar");

                const calendar = new FullCalendar.Calendar(
                    calendarElement,
                    {
                        initialView: "dayGridMonth",
                        height: "100%",
                        events: __EVENTS__,

                        dateClick: function(info) {
                            const url = new URL(
                                window.parent.location.href
                            );

                            url.searchParams.set(
                                "edit_date",
                                info.dateStr
                            );

                            window.parent.location.href =
                                url.toString();
                        },

                        eventClick: function(info) {
                            const url = new URL(
                                window.parent.location.href
                            );

                            url.searchParams.set(
                                "edit_date",
                                info.event.startStr
                            );

                            window.parent.location.href =
                                url.toString();
                        }
                    }
                );

                calendar.render();
            });
        </script>
    </body>
    </html>
    """

    html_to_render = calendar_template.replace(
        "__EVENTS__",
        json.dumps(events)
    )

    components.html(
        html_to_render,
        height=800,
        scrolling=False
    )


# =========================================================
# SESSION STATE
# =========================================================

init_db()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "user_id" not in st.session_state:
    st.session_state.user_id = None

if "username" not in st.session_state:
    st.session_state.username = None


# =========================================================
# LOGIN AND REGISTRATION
# =========================================================

if not st.session_state.authenticated:

    st.title("Calendar Notes")

    login_tab, register_tab = st.tabs(
        ["Login", "Register"]
    )

    with login_tab:
        username = st.text_input(
            "Username",
            key="login_username"
        )

        password = st.text_input(
            "Password",
            type="password",
            key="login_password"
        )

        if st.button(
            "Login",
            use_container_width=True
        ):
            user_id = verify_user(
                username,
                password
            )

            if user_id:
                st.session_state.authenticated = True
                st.session_state.user_id = user_id
                st.session_state.username = username.strip()

                st.rerun()
            else:
                st.error("Invalid username or password.")

    with register_tab:
        new_username = st.text_input(
            "New username",
            key="register_username"
        )

        new_password = st.text_input(
            "New password",
            type="password",
            key="register_password"
        )

        confirm_password = st.text_input(
            "Confirm password",
            type="password",
            key="confirm_password"
        )

        if st.button(
            "Create Account",
            use_container_width=True
        ):
            if new_password != confirm_password:
                st.error("Passwords do not match.")
            elif create_user(new_username, new_password):
                st.success(
                    "Account created. You can now log in."
                )

    st.markdown("---")
    st.markdown(
        '<div class="app-footer">© 2026 timothymarkbal-e</div>',
        unsafe_allow_html=True
    )

    st.stop()


# =========================================================
# AUTHENTICATED APPLICATION
# =========================================================

st.sidebar.title(
    f"User: {st.session_state.username}"
)

notes = load_notes(
    st.session_state.user_id
)

st.sidebar.markdown("---")

# ---------------------------------------------------------
# PDF EXPORT
# ---------------------------------------------------------

st.sidebar.subheader("PDF Export")

export_range = st.sidebar.selectbox(
    "Export range",
    ["Daily", "Weekly", "Monthly", "All Notes"]
)

today = datetime.now().date()

if export_range == "Daily":
    start_date = today
    end_date = today

elif export_range == "Weekly":
    start_date = today - timedelta(days=today.weekday())
    end_date = start_date + timedelta(days=6)

elif export_range == "Monthly":
    start_date = today.replace(day=1)

    next_month = (
        today.replace(day=28) + timedelta(days=4)
    ).replace(day=1)

    end_date = next_month - timedelta(days=1)

else:
    if notes:
        start_date = datetime.strptime(
            min(notes.keys()),
            "%Y-%m-%d"
        ).date()

        end_date = datetime.strptime(
            max(notes.keys()),
            "%Y-%m-%d"
        ).date()
    else:
        start_date = today
        end_date = today

pdf_data = generate_pdf(
    st.session_state.username,
    notes,
    start_date,
    end_date
)

st.sidebar.download_button(
    label=f"Download {export_range} PDF",
    data=pdf_data,
    file_name=(
        f"calendar_notes_"
        f"{start_date}_{end_date}.pdf"
    ),
    mime="application/pdf",
    use_container_width=True
)

# ---------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------

if st.sidebar.button(
    "Logout",
    use_container_width=True
):
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.username = None

    st.query_params.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("© 2026 timothymarkbal-e")


# =========================================================
# MAIN INTERFACE
# =========================================================

query_date = st.query_params.get(
    "edit_date",
    None
)

default_date = today

if query_date:
    try:
        default_date = datetime.strptime(
            query_date,
            "%Y-%m-%d"
        ).date()
    except ValueError:
        default_date = today

column_editor, column_calendar = st.columns(
    [1, 3],
    gap="large"
)


# =========================================================
# NOTE EDITOR
# =========================================================

with column_editor:

    st.subheader("Note Editor")

    active_date = st.date_input(
        "Select date",
        value=default_date
    )

    active_date_string = str(active_date)
    note_state_key = f"note_{active_date_string}"

    if note_state_key not in st.session_state:
        st.session_state[note_state_key] = notes.get(
            active_date_string,
            ""
        )

    st.info(
        """
        Formatting shortcuts:

        `**text**` = bold

        `==text==` = yellow highlight

        `!!text!!` = red highlight

        `##text##` = green highlight
        """
    )

    highlight_color = st.selectbox(
        "Highlight color",
        ["Yellow", "Red", "Green"],
        key=f"highlight_color_{active_date_string}"
    )

    note_text = st.text_area(
        f"Notes for {active_date_string}",
        height=400,
        key=note_state_key,
        placeholder=(
            "Write your note here...\n\n"
            "Example:\n"
            "**Project meeting**\n"
            "==Important deadline==\n"
            "!!Urgent task!!\n"
            "##Ideas##"
        )
    )

    button_col1, button_col2 = st.columns(2)

    with button_col1:
        if st.button(
            "Highlight note",
            use_container_width=True
        ):
            st.session_state[note_state_key] = add_highlight(
                note_text,
                highlight_color
            )
            st.rerun()

    with button_col2:
        if st.button(
            "Remove formatting",
            use_container_width=True
        ):
            st.session_state[note_state_key] = remove_formatting(
                note_text
            )
            st.rerun()

    st.subheader("Preview")

    preview_text = st.session_state[note_state_key]
    preview_html = format_note_html(preview_text)

    st.markdown(
        f"""
        <div class="note-preview">
            {preview_html}
        </div>
        """,
        unsafe_allow_html=True
    )

    save_col, delete_col = st.columns(2)

    with save_col:
        if st.button(
            "Save Note",
            use_container_width=True
        ):
            if save_note(
                st.session_state.user_id,
                active_date_string,
                st.session_state[note_state_key]
            ):
                st.query_params.clear()
                st.success("Note saved.")
                st.rerun()

    with delete_col:
        if st.button(
            "Delete Note",
            use_container_width=True
        ):
            if delete_note(
                st.session_state.user_id,
                active_date_string
            ):
                st.session_state[note_state_key] = ""
                st.query_params.clear()
                st.success("Note deleted.")
                st.rerun()

    if query_date:
        if st.button(
            "Clear date selection",
            use_container_width=True
        ):
            st.query_params.clear()
            st.rerun()


# =========================================================
# CALENDAR
# =========================================================

with column_calendar:
    st.subheader("Calendar")
    create_calendar(notes)


# =========================================================
# FOOTER
# =========================================================

st.markdown("---")

st.markdown(
    '<div class="app-footer">© 2026 timothymarkbal-e</div>',
    unsafe_allow_html=True
)
