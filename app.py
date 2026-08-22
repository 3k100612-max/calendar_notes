import os
import hashlib
import secrets
from datetime import datetime

import psycopg2
import streamlit as st
from dotenv import load_dotenv
from streamlit_quill import st_quill
from weasyprint import HTML



# =========================================================
# CONFIGURATION
# =========================================================

load_dotenv()

st.set_page_config(
    page_title="My Notebook",
    page_icon="Notebook",
    layout="wide"
)


# =========================================================
# DATABASE CONNECTION
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
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS notebooks (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sections (
                id SERIAL PRIMARY KEY,
                notebook_id INTEGER NOT NULL
                    REFERENCES notebooks(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pages (
                id SERIAL PRIMARY KEY,
                section_id INTEGER NOT NULL
                    REFERENCES sections(id) ON DELETE CASCADE,
                title TEXT NOT NULL DEFAULT 'Untitled Page',
                content TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        conn.commit()
        cur.close()
        conn.close()

    except Exception as error:
        conn.rollback()
        st.error(f"Database setup error: {error}")

    finally:
        if conn:
            conn.close()


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


def login_user(username, password):
    conn = get_connection()

    if not conn:
        return None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, username, password_hash
            FROM users
            WHERE username = %s
            """,
            (username.strip(),)
        )

        user = cur.fetchone()
        cur.close()

        if user and verify_password(password, user[2]):
            return {
                "id": user[0],
                "username": user[1]
            }

    except Exception as error:
        st.error(f"Login error: {error}")

    finally:
        conn.close()

    return None


# =========================================================
# NOTEBOOK FUNCTIONS
# =========================================================

def get_notebooks(user_id):
    conn = get_connection()

    if not conn:
        return []

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, name
            FROM notebooks
            WHERE user_id = %s
            ORDER BY name
            """,
            (user_id,)
        )

        notebooks = cur.fetchall()
        cur.close()

        return notebooks

    finally:
        conn.close()


def create_notebook(user_id, name):
    name = name.strip()

    if not name:
        return None

    conn = get_connection()

    if not conn:
        return None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO notebooks (user_id, name)
            VALUES (%s, %s)
            RETURNING id
            """,
            (user_id, name)
        )

        notebook_id = cur.fetchone()[0]

        conn.commit()
        cur.close()

        return notebook_id

    except Exception as error:
        conn.rollback()
        st.error(f"Could not create notebook: {error}")
        return None

    finally:
        conn.close()


def rename_notebook(notebook_id, name):
    conn = get_connection()

    if not conn:
        return False

    try:
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE notebooks
            SET name = %s
            WHERE id = %s
            """,
            (name.strip(), notebook_id)
        )

        conn.commit()
        cur.close()

        return True

    finally:
        conn.close()


def delete_notebook(notebook_id):
    conn = get_connection()

    if not conn:
        return False

    try:
        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM notebooks
            WHERE id = %s
            """,
            (notebook_id,)
        )

        conn.commit()
        cur.close()

        return True

    finally:
        conn.close()


# =========================================================
# SECTION FUNCTIONS
# =========================================================

def get_sections(notebook_id):
    conn = get_connection()

    if not conn:
        return []

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, name
            FROM sections
            WHERE notebook_id = %s
            ORDER BY name
            """,
            (notebook_id,)
        )

        sections = cur.fetchall()
        cur.close()

        return sections

    finally:
        conn.close()


def create_section(notebook_id, name):
    name = name.strip()

    if not name:
        return None

    conn = get_connection()

    if not conn:
        return None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO sections (notebook_id, name)
            VALUES (%s, %s)
            RETURNING id
            """,
            (notebook_id, name)
        )

        section_id = cur.fetchone()[0]

        conn.commit()
        cur.close()

        return section_id

    except Exception as error:
        conn.rollback()
        st.error(f"Could not create section: {error}")
        return None

    finally:
        conn.close()


def rename_section(section_id, name):
    conn = get_connection()

    if not conn:
        return False

    try:
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE sections
            SET name = %s
            WHERE id = %s
            """,
            (name.strip(), section_id)
        )

        conn.commit()
        cur.close()

        return True

    finally:
        conn.close()


def delete_section(section_id):
    conn = get_connection()

    if not conn:
        return False

    try:
        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM sections
            WHERE id = %s
            """,
            (section_id,)
        )

        conn.commit()
        cur.close()

        return True

    finally:
        conn.close()


# =========================================================
# PAGE FUNCTIONS
# =========================================================

def get_pages(section_id):
    conn = get_connection()

    if not conn:
        return []

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, title, updated_at
            FROM pages
            WHERE section_id = %s
            ORDER BY updated_at DESC
            """,
            (section_id,)
        )

        pages = cur.fetchall()
        cur.close()

        return pages

    finally:
        conn.close()


def get_page(page_id):
    conn = get_connection()

    if not conn:
        return None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, section_id, title, content, created_at, updated_at
            FROM pages
            WHERE id = %s
            """,
            (page_id,)
        )

        page = cur.fetchone()
        cur.close()

        return page

    finally:
        conn.close()


def create_page(section_id, title="Untitled Page"):
    conn = get_connection()

    if not conn:
        return None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO pages (section_id, title, content)
            VALUES (%s, %s, '')
            RETURNING id
            """,
            (section_id, title.strip() or "Untitled Page")
        )

        page_id = cur.fetchone()[0]

        conn.commit()
        cur.close()

        return page_id

    except Exception as error:
        conn.rollback()
        st.error(f"Could not create page: {error}")
        return None

    finally:
        conn.close()


def save_page(page_id, title, content):
    conn = get_connection()

    if not conn:
        return False

    try:
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE pages
            SET title = %s,
                content = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (
                title.strip() or "Untitled Page",
                content,
                page_id
            )
        )

        conn.commit()
        cur.close()

        return True

    except Exception as error:
        conn.rollback()
        st.error(f"Could not save page: {error}")
        return False

    finally:
        conn.close()


def delete_page(page_id):
    conn = get_connection()

    if not conn:
        return False

    try:
        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM pages
            WHERE id = %s
            """,
            (page_id,)
        )

        conn.commit()
        cur.close()

        return True

    finally:
        conn.close()


def search_pages(user_id, search_term):
    conn = get_connection()

    if not conn:
        return []

    try:
        cur = conn.cursor()

        search_pattern = f"%{search_term}%"

        cur.execute(
            """
            SELECT
                pages.id,
                pages.title,
                sections.name,
                notebooks.name
            FROM pages
            JOIN sections
                ON pages.section_id = sections.id
            JOIN notebooks
                ON sections.notebook_id = notebooks.id
            WHERE notebooks.user_id = %s
            AND (
                pages.title ILIKE %s
                OR pages.content ILIKE %s
            )
            ORDER BY pages.updated_at DESC
            """,
            (
                user_id,
                search_pattern,
                search_pattern
            )
        )

        results = cur.fetchall()
        cur.close()

        return results

    finally:
        conn.close()


# =========================================================
# TEXT FORMATTING
# =========================================================

def remove_markup(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"==(.+?)==", r"\1", text)
    text = re.sub(r"!!(.+?)!!", r"\1", text)
    text = re.sub(r"##(.+?)##", r"\1", text)

    return text


def note_to_html(text):
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


def highlight_text(text, color):
    markers = {
        "Yellow": ("==", "=="),
        "Red": ("!!", "!!"),
        "Green": ("##", "##")
    }

    start_marker, end_marker = markers[color]

    if text.strip():
        return f"{start_marker}{text}{end_marker}"

    return text


# =========================================================
# PDF EXPORT
# =========================================================

def pdf_text(text):
    text = remove_markup(text)

    return (
        text
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def build_page_pdf(username, title, content):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(
        0,
        12,
        pdf_text(title),
        new_x="LMARGIN",
        new_y="NEXT",
        align="C"
    )

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        8,
        f"Created for {pdf_text(username)}",
        new_x="LMARGIN",
        new_y="NEXT",
        align="C"
    )

    pdf.ln(10)

    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(
        0,
        7,
        pdf_text(content)
    )

    return bytes(pdf.output())


def build_section_pdf(username, section_name, pages):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(
        0,
        12,
        pdf_text(section_name),
        new_x="LMARGIN",
        new_y="NEXT",
        align="C"
    )

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        8,
        f"Created for {pdf_text(username)}",
        new_x="LMARGIN",
        new_y="NEXT",
        align="C"
    )

    pdf.ln(10)

    for page_id, title, updated_at in pages:
        page = get_page(page_id)

        if not page:
            continue

        content = page[3]

        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(
            0,
            10,
            pdf_text(title),
            new_x="LMARGIN",
            new_y="NEXT"
        )

        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(
            0,
            7,
            pdf_text(content)
        )

        pdf.ln(8)

        pdf.set_draw_color(180, 180, 180)
        pdf.line(
            10,
            pdf.get_y(),
            200,
            pdf.get_y()
        )

        pdf.ln(8)

    return bytes(pdf.output())


# =========================================================
# STYLING
# =========================================================

st.markdown(
    """
    <style>
    .note-preview {
        min-height: 300px;
        padding: 20px;
        border: 1px solid #d0d7de;
        border-radius: 10px;
        background-color: white;
        color: #222222;
        line-height: 1.8;
        font-size: 16px;
        overflow-wrap: anywhere;
    }

    mark {
        padding: 3px 6px;
        border-radius: 4px;
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

    .page-card {
        padding: 8px;
        border-radius: 6px;
        margin-bottom: 5px;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# INITIALIZE DATABASE
# =========================================================

init_db()


# =========================================================
# SESSION STATE
# =========================================================

if "user" not in st.session_state:
    st.session_state.user = None

if "selected_notebook" not in st.session_state:
    st.session_state.selected_notebook = None

if "selected_section" not in st.session_state:
    st.session_state.selected_section = None

if "selected_page" not in st.session_state:
    st.session_state.selected_page = None


# =========================================================
# LOGIN SCREEN
# =========================================================

if st.session_state.user is None:

    st.title("My Notebook")

    login_tab, register_tab = st.tabs(
        ["Login", "Register"]
    )

    with login_tab:
        login_username = st.text_input(
            "Username",
            key="login_username"
        )

        login_password = st.text_input(
            "Password",
            type="password",
            key="login_password"
        )

        if st.button(
            "Login",
            use_container_width=True
        ):
            user = login_user(
                login_username,
                login_password
            )

            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with register_tab:
        register_username = st.text_input(
            "New username",
            key="register_username"
        )

        register_password = st.text_input(
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
            if register_password != confirm_password:
                st.error("Passwords do not match.")
            elif create_user(
                register_username,
                register_password
            ):
                st.success(
                    "Account created. You can now log in."
                )

    st.stop()


# =========================================================
# CURRENT USER
# =========================================================

user_id = st.session_state.user["id"]
username = st.session_state.user["username"]

st.sidebar.title("My Notebook")
st.sidebar.caption(f"Signed in as {username}")


# =========================================================
# NOTEBOOK SIDEBAR
# =========================================================

st.sidebar.markdown("---")
st.sidebar.subheader("Notebooks")

notebooks = get_notebooks(user_id)

notebook_names = {
    notebook_id: notebook_name
    for notebook_id, notebook_name in notebooks
}

if notebooks:
    notebook_ids = list(notebook_names.keys())

    if (
        st.session_state.selected_notebook not in notebook_ids
    ):
        st.session_state.selected_notebook = notebook_ids[0]

    selected_notebook = st.sidebar.selectbox(
        "Select notebook",
        options=notebook_ids,
        format_func=lambda notebook_id: notebook_names[notebook_id],
        index=notebook_ids.index(
            st.session_state.selected_notebook
        )
    )

    st.session_state.selected_notebook = selected_notebook

else:
    st.sidebar.info("No notebooks yet.")
    selected_notebook = None


with st.sidebar.expander("Create notebook"):
    new_notebook_name = st.text_input(
        "Notebook name",
        key="new_notebook_name"
    )

    if st.button(
        "Create notebook",
        use_container_width=True
    ):
        notebook_id = create_notebook(
            user_id,
            new_notebook_name
        )

        if notebook_id:
            st.session_state.selected_notebook = notebook_id
            st.success("Notebook created.")
            st.rerun()


if selected_notebook:

    st.sidebar.markdown("---")
    st.sidebar.subheader("Sections")

    sections = get_sections(selected_notebook)

    section_names = {
        section_id: section_name
        for section_id, section_name in sections
    }

    if sections:
        section_ids = list(section_names.keys())

        if (
            st.session_state.selected_section not in section_ids
        ):
            st.session_state.selected_section = section_ids[0]

        selected_section = st.sidebar.selectbox(
            "Select section",
            options=section_ids,
            format_func=lambda section_id: section_names[section_id],
            index=section_ids.index(
                st.session_state.selected_section
            )
        )

        st.session_state.selected_section = selected_section

    else:
        st.sidebar.info("No sections yet.")
        selected_section = None

    with st.sidebar.expander("Create section"):
        new_section_name = st.text_input(
            "Section name",
            key="new_section_name"
        )

        if st.button(
            "Create section",
            use_container_width=True
        ):
            section_id = create_section(
                selected_notebook,
                new_section_name
            )

            if section_id:
                st.session_state.selected_section = section_id
                st.success("Section created.")
                st.rerun()

QUILL_TOOLBAR = [
    [
        "bold",
        "italic",
        "underline",
        "strike"
    ],
    [
        {
            "color": []
        },
        {
            "background": []
        }
    ],
    [
        {
            "header": [1, 2, 3, 4, 5, 6, False]
        }
    ],
    [
        {
            "align": []
        }
    ],
    [
        {
            "list": "ordered"
        },
        {
            "list": "bullet"
        }
    ],
    [
        {
            "indent": "-1"
        },
        {
            "indent": "+1"
        }
    ],
    [
        "blockquote",
        "code-block"
    ],
    [
        "link"
    ],
    [
        "clean"
    ]
]



# =========================================================
# MAIN APPLICATION
# =========================================================

if not selected_notebook or not selected_section:

    st.title("My Notebook")
    st.info(
        "Create a notebook and a section from the sidebar to begin."
    )
    st.stop()


# =========================================================
# PAGE LIST
# =========================================================

pages = get_pages(selected_section)

page_map = {
    page_id: title
    for page_id, title, updated_at in pages
}

if pages:
    page_ids = list(page_map.keys())

    if st.session_state.selected_page not in page_ids:
        st.session_state.selected_page = page_ids[0]

else:
    new_page_id = create_page(
        selected_section,
        "Welcome Page"
    )

    st.session_state.selected_page = new_page_id
    st.rerun()


with st.sidebar:

    st.markdown("---")
    st.subheader("Pages")

    for page_id, title, updated_at in pages:
        label = title or "Untitled Page"

        if st.button(
            label,
            key=f"page_button_{page_id}",
            use_container_width=True
        ):
            st.session_state.selected_page = page_id
            st.rerun()

    if st.button(
        "New page",
        use_container_width=True
    ):
        new_page_id = create_page(
            selected_section,
            "Untitled Page"
        )

        if new_page_id:
            st.session_state.selected_page = new_page_id
            st.rerun()


# =========================================================
# PAGE CONTENT
# =========================================================

page = get_page(st.session_state.selected_page)

if not page:
    st.error("Page not found.")
    st.stop()

page_id = page[0]
page_title = page[2]
page_content = page[3]


# =========================================================
# TOP BAR
# =========================================================

top_col1, top_col2, top_col3 = st.columns(
    [5, 1, 1]
)

with top_col1:
    st.title(page_title)

with top_col2:
    if st.button("Save"):
        st.session_state.save_page_clicked = True

with top_col3:
    if st.button("Delete"):
        delete_page(page_id)
        st.session_state.selected_page = None
        st.rerun()


# =========================================================
# RICH TEXT EDITOR
# =========================================================

title_input = st.text_input(
    "Page title",
    value=page_title,
    key=f"title_input_{page_id}"
)

st.caption(
    "Use the toolbar to format text, add highlights, colors, headings, "
    "lists, links, alignment, and indentation."
)

content_input = st_quill(
    value=page_content,
    html=True,
    key=f"quill_editor_{page_id}",
    toolbar=QUILL_TOOLBAR,
    placeholder="Start writing your page..."
)


# =========================================================
# SAVE PAGE
# =========================================================

if st.button(
    "Save Page",
    type="primary",
    use_container_width=True
):
    if save_page(
        page_id,
        title_input,
        content_input
    ):
        st.success("Page saved successfully.")
        st.rerun()


# =========================================================
# CONTENT PREVIEW
# =========================================================

st.subheader("Preview")

st.markdown(
    f"""
    <div class="note-preview">
        {content_input}
    </div>
    """,
    unsafe_allow_html=True
)



# =========================================================
# PREVIEW
# =========================================================

st.subheader("Preview")

preview_html = note_to_html(content_input)

st.markdown(
    f"""
    <div class="note-preview">
        {preview_html}
    </div>
    """,
    unsafe_allow_html=True
)


# =========================================================
# PDF EXPORT
# =========================================================

st.markdown("---")
st.subheader("Export")

export_col1, export_col2 = st.columns(2)

with export_col1:
    page_pdf = build_page_pdf(
        username,
        title_input,
        content_input
    )

    st.download_button(
        "Download current page PDF",
        data=page_pdf,
        file_name="page.pdf",
        mime="application/pdf",
        use_container_width=True
    )

with export_col2:
    section_pages = get_pages(selected_section)
    section_pdf = build_section_pdf(
        username,
        section_names[selected_section],
        section_pages
    )

    st.download_button(
        "Download section PDF",
        data=section_pdf,
        file_name="section.pdf",
        mime="application/pdf",
        use_container_width=True
    )


# =========================================================
# SEARCH
# =========================================================

st.sidebar.markdown("---")
st.sidebar.subheader("Search")

search_term = st.sidebar.text_input(
    "Search pages",
    key="search_term"
)

if search_term.strip():
    results = search_pages(
        user_id,
        search_term.strip()
    )

    if results:
        st.sidebar.markdown("Search results:")

        for result_page_id, result_title, result_section, result_notebook in results:
            if st.sidebar.button(
                f"{result_title} - {result_section}",
                key=f"search_result_{result_page_id}",
                use_container_width=True
            ):
                st.session_state.selected_page = result_page_id
                st.rerun()
    else:
        st.sidebar.caption("No pages found.")


# =========================================================
# LOGOUT
# =========================================================

st.sidebar.markdown("---")

if st.sidebar.button(
    "Logout",
    use_container_width=True
):
    st.session_state.user = None
    st.session_state.selected_notebook = None
    st.session_state.selected_section = None
    st.session_state.selected_page = None
    st.rerun()
