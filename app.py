import os
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
    page_icon="📓",
    layout="wide",
    initial_sidebar_state="expanded"
)


# =========================================================
# PAGE STYLE
# =========================================================

st.markdown(
    """
    <style>
        [data-testid="stSidebar"] {
            min-width: 300px;
            max-width: 340px;
        }

        .notebook-header {
            padding: 18px 22px;
            border-radius: 12px;
            background: linear-gradient(
                135deg,
                #2563eb,
                #7c3aed
            );
            color: white;
            margin-bottom: 20px;
        }

        .notebook-header h1 {
            margin: 0;
            font-size: 30px;
        }

        .notebook-header p {
            margin: 5px 0 0 0;
            opacity: 0.9;
        }

        .page-preview {
            min-height: 300px;
            padding: 24px;
            border: 1px solid #d1d5db;
            border-radius: 12px;
            background-color: #ffffff;
            color: #202124;
            line-height: 1.7;
            font-size: 16px;
            overflow-wrap: anywhere;
        }

        .page-preview h1,
        .page-preview h2,
        .page-preview h3 {
            color: #1f2937;
        }

        .page-preview blockquote {
            border-left: 4px solid #9ca3af;
            padding-left: 14px;
            color: #4b5563;
        }

        .page-preview pre {
            padding: 14px;
            border-radius: 8px;
            background-color: #f3f4f6;
            white-space: pre-wrap;
        }

        .page-preview img {
            max-width: 100%;
            height: auto;
        }

        .page-preview a {
            color: #2563eb;
            text-decoration: underline;
        }

        .section-label {
            color: #6b7280;
            font-size: 14px;
            margin-bottom: 5px;
        }

        .footer {
            text-align: center;
            color: #888888;
            margin-top: 35px;
            padding: 15px;
        }

        button[kind="secondary"] {
            border-radius: 8px;
        }
    </style>
    """,
    unsafe_allow_html=True
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

    if conn is None:
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

    except Exception as error:
        conn.rollback()
        st.error(f"Database setup error: {error}")

    finally:
        conn.close()


# =========================================================
# USER AUTHENTICATION
# =========================================================

def create_user(username, password):
    username = username.strip()

    if not username:
        st.error("Username cannot be empty.")
        return False

    if len(password) < 6:
        st.error("Password must contain at least 6 characters.")
        return False

    conn = get_connection()

    if conn is None:
        return False

    try:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO users (username, password_hash)
            VALUES (%s, crypt(%s, gen_salt('bf')))
            """,
            (username, password)
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

    if conn is None:
        return None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, username
            FROM users
            WHERE username = %s
            AND password_hash = crypt(%s, password_hash)
            """,
            (username.strip(), password)
        )

        user = cur.fetchone()
        cur.close()

        if user:
            return {
                "id": user[0],
                "username": user[1]
            }

        return None

    except Exception as error:
        st.error(f"Login error: {error}")
        return None

    finally:
        conn.close()


# =========================================================
# NOTEBOOK DATABASE FUNCTIONS
# =========================================================

def get_notebooks(user_id):
    conn = get_connection()

    if conn is None:
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

        rows = cur.fetchall()
        cur.close()

        return rows

    finally:
        conn.close()


def create_notebook(user_id, name):
    name = name.strip()

    if not name:
        return None

    conn = get_connection()

    if conn is None:
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
    name = name.strip()

    if not name:
        return False

    conn = get_connection()

    if conn is None:
        return False

    try:
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE notebooks
            SET name = %s
            WHERE id = %s
            """,
            (name, notebook_id)
        )

        conn.commit()
        cur.close()

        return True

    finally:
        conn.close()


def delete_notebook(notebook_id):
    conn = get_connection()

    if conn is None:
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


def get_sections(notebook_id):
    conn = get_connection()

    if conn is None:
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

        rows = cur.fetchall()
        cur.close()

        return rows

    finally:
        conn.close()


def create_section(notebook_id, name):
    name = name.strip()

    if not name:
        return None

    conn = get_connection()

    if conn is None:
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
    name = name.strip()

    if not name:
        return False

    conn = get_connection()

    if conn is None:
        return False

    try:
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE sections
            SET name = %s
            WHERE id = %s
            """,
            (name, section_id)
        )

        conn.commit()
        cur.close()

        return True

    finally:
        conn.close()


def delete_section(section_id):
    conn = get_connection()

    if conn is None:
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


def get_pages(section_id):
    conn = get_connection()

    if conn is None:
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

        rows = cur.fetchall()
        cur.close()

        return rows

    finally:
        conn.close()


def get_page(page_id):
    conn = get_connection()

    if conn is None:
        return None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, section_id, title, content, updated_at
            FROM pages
            WHERE id = %s
            """,
            (page_id,)
        )

        row = cur.fetchone()
        cur.close()

        return row

    finally:
        conn.close()


def create_page(section_id, title="Untitled Page"):
    conn = get_connection()

    if conn is None:
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

    if conn is None:
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
                content or "",
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

    if conn is None:
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


def search_pages(user_id, search_text):
    conn = get_connection()

    if conn is None:
        return []

    try:
        cur = conn.cursor()
        pattern = f"%{search_text}%"

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
            (user_id, pattern, pattern)
        )

        rows = cur.fetchall()
        cur.close()

        return rows

    finally:
        conn.close()


# =========================================================
# RICH TEXT EDITOR
# =========================================================

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
        "link",
        "clean"
    ]
]


# =========================================================
# PDF EXPORT
# =========================================================

def pdf_css():
    return """
    @page {
        size: A4;
        margin: 20mm 18mm 20mm 18mm;

        @bottom-right {
            content: "Page " counter(page);
            font-size: 9pt;
            color: #777777;
        }
    }

    body {
        font-family: Arial, sans-serif;
        color: #222222;
        font-size: 11pt;
        line-height: 1.55;
    }

    h1 {
        color: #1f2937;
        font-size: 24pt;
        margin-bottom: 4px;
    }

    h2 {
        color: #374151;
        font-size: 18pt;
    }

    h3 {
        color: #4b5563;
        font-size: 14pt;
    }

    .metadata {
        color: #6b7280;
        font-size: 9pt;
        border-bottom: 1px solid #d1d5db;
        padding-bottom: 10px;
        margin-bottom: 20px;
    }

    blockquote {
        border-left: 4px solid #9ca3af;
        padding-left: 12px;
        color: #4b5563;
    }

    pre {
        background-color: #f3f4f6;
        padding: 12px;
        border-radius: 6px;
        white-space: pre-wrap;
    }

    code {
        background-color: #f3f4f6;
        padding: 2px 4px;
        border-radius: 3px;
    }

    img {
        max-width: 100%;
        height: auto;
    }

    .section-page {
        page-break-after: always;
    }

    .section-page:last-child {
        page-break-after: auto;
    }
    """


def build_page_pdf(username, title, content):
    document = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            {pdf_css()}
        </style>
    </head>
    <body>
        <h1>{title or "Untitled Page"}</h1>

        <div class="metadata">
            Created for {username}
        </div>

        <div>
            {content or "<p>No content.</p>"}
        </div>
    </body>
    </html>
    """

    return HTML(string=document).write_pdf()


def build_section_pdf(username, section_name, pages):
    pages_html = ""

    for page_id, title, updated_at in pages:
        page = get_page(page_id)

        if not page:
            continue

        page_title = page[2] or "Untitled Page"
        page_content = page[3] or ""

        pages_html += f"""
        <section class="section-page">
            <h1>{page_title}</h1>

            <div class="metadata">
                Updated: {updated_at}
            </div>

            <div>
                {page_content or "<p>No content.</p>"}
            </div>
        </section>
        """

    document = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            {pdf_css()}
        </style>
    </head>
    <body>
        <h1>{section_name}</h1>

        <div class="metadata">
            Created for {username}
        </div>

        {pages_html}
    </body>
    </html>
    """

    return HTML(string=document).write_pdf()


# =========================================================
# INITIALIZATION
# =========================================================

init_db()

if "user" not in st.session_state:
    st.session_state.user = None

if "selected_notebook" not in st.session_state:
    st.session_state.selected_notebook = None

if "selected_section" not in st.session_state:
    st.session_state.selected_section = None

if "selected_page" not in st.session_state:
    st.session_state.selected_page = None


# =========================================================
# LOGIN PAGE
# =========================================================

if st.session_state.user is None:
    st.markdown(
        """
        <div class="notebook-header">
            <h1>My Notebook</h1>
            <p>Your personal OneNote-style workspace</p>
        </div>
        """,
        unsafe_allow_html=True
    )

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
            type="primary",
            use_container_width=True
        ):
            user = login_user(username, password)

            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with register_tab:
        new_username = st.text_input(
            "New username",
            key="new_username"
        )

        new_password = st.text_input(
            "New password",
            type="password",
            key="new_password"
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

    st.stop()


# =========================================================
# USER INFORMATION
# =========================================================

user_id = st.session_state.user["id"]
username = st.session_state.user["username"]


# =========================================================
# SIDEBAR: NOTEBOOKS
# =========================================================

st.sidebar.title("My Notebook")
st.sidebar.caption(f"Signed in as {username}")

st.sidebar.markdown("---")
st.sidebar.subheader("Notebooks")

notebooks = get_notebooks(user_id)
notebook_names = dict(notebooks)
notebook_ids = list(notebook_names.keys())

if notebook_ids:

    if st.session_state.selected_notebook not in notebook_ids:
        st.session_state.selected_notebook = notebook_ids[0]

    selected_notebook = st.sidebar.selectbox(
        "Choose notebook",
        notebook_ids,
        format_func=lambda value: notebook_names[value],
        index=notebook_ids.index(
            st.session_state.selected_notebook
        )
    )

    st.session_state.selected_notebook = selected_notebook

else:
    selected_notebook = None
    st.sidebar.info("Create your first notebook.")


with st.sidebar.expander("Create notebook"):
    notebook_name = st.text_input(
        "Notebook name",
        key="notebook_name"
    )

    if st.button(
        "Create notebook",
        use_container_width=True
    ):
        notebook_id = create_notebook(
            user_id,
            notebook_name
        )

        if notebook_id:
            st.session_state.selected_notebook = notebook_id
            st.rerun()


if selected_notebook:

    st.sidebar.markdown("---")
    st.sidebar.subheader("Sections")

    sections = get_sections(selected_notebook)
    section_names = dict(sections)
    section_ids = list(section_names.keys())

    if section_ids:

        if st.session_state.selected_section not in section_ids:
            st.session_state.selected_section = section_ids[0]

        selected_section = st.sidebar.selectbox(
            "Choose section",
            section_ids,
            format_func=lambda value: section_names[value],
            index=section_ids.index(
                st.session_state.selected_section
            )
        )

        st.session_state.selected_section = selected_section

    else:
        selected_section = None
        st.sidebar.info("Create your first section.")

    with st.sidebar.expander("Create section"):
        section_name = st.text_input(
            "Section name",
            key="section_name"
        )

        if st.button(
            "Create section",
            use_container_width=True
        ):
            if selected_notebook:
                section_id = create_section(
                    selected_notebook,
                    section_name
                )

                if section_id:
                    st.session_state.selected_section = section_id
                    st.rerun()


# =========================================================
# REQUIRE NOTEBOOK AND SECTION
# =========================================================

if not selected_notebook or not selected_section:
    st.markdown(
        """
        <div class="notebook-header">
            <h1>Welcome to My Notebook</h1>
            <p>Create a notebook and section from the sidebar.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.info(
        "Use the sidebar to create a notebook and a section."
    )

    st.stop()


# =========================================================
# SIDEBAR: PAGES
# =========================================================

pages = get_pages(selected_section)
page_ids = [page[0] for page in pages]

if not page_ids:
    new_page_id = create_page(
        selected_section,
        "Welcome Page"
    )

    st.session_state.selected_page = new_page_id
    st.rerun()

if st.session_state.selected_page not in page_ids:
    st.session_state.selected_page = page_ids[0]

with st.sidebar:
    st.markdown("---")
    st.subheader("Pages")

    for page_id, title, updated_at in pages:
        if st.button(
            title or "Untitled Page",
            key=f"page_{page_id}",
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
# CURRENT PAGE
# =========================================================

page = get_page(st.session_state.selected_page)

if not page:
    st.error("The selected page could not be found.")
    st.stop()

page_id = page[0]
page_title = page[2]
page_content = page[3]


# =========================================================
# PAGE HEADER
# =========================================================

st.markdown(
    f"""
    <div class="section-label">
        {notebook_names[selected_notebook]}
        / {section_names[selected_section]}
    </div>
    """,
    unsafe_allow_html=True
)

header_col1, header_col2 = st.columns([5, 1])

with header_col1:
    st.title(page_title)

with header_col2:
    if st.button(
        "Delete page",
        use_container_width=True
    ):
        delete_page(page_id)
        st.session_state.selected_page = None
        st.rerun()


# =========================================================
# PAGE EDITOR
# =========================================================

title_input = st.text_input(
    "Page title",
    value=page_title,
    key=f"title_{page_id}"
)

st.caption(
    "Use the toolbar to format text, add colors, highlights, "
    "headings, lists, links, alignment, and indentation."
)

content_input = st_quill(
    value=page_content or "",
    html=True,
    toolbar=QUILL_TOOLBAR,
    placeholder="Start writing your page...",
    key=f"editor_{page_id}"
)

if st.button(
    "Save page",
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
# PREVIEW
# =========================================================

st.markdown("---")
st.subheader("Preview")

st.markdown(
    f"""
    <div class="page-preview">
        {content_input or "<p>Your page preview will appear here.</p>"}
    </div>
    """,
    unsafe_allow_html=True
)


# =========================================================
# PDF EXPORT
# =========================================================

st.markdown("---")
st.subheader("PDF Export")

pdf_col1, pdf_col2 = st.columns(2)

with pdf_col1:
    current_page_pdf = build_page_pdf(
        username,
        title_input,
        content_input
    )

    st.download_button(
        "Download current page PDF",
        data=current_page_pdf,
        file_name="current_page.pdf",
        mime="application/pdf",
        use_container_width=True
    )

with pdf_col2:
    section_pages = get_pages(selected_section)

    complete_section_pdf = build_section_pdf(
        username,
        section_names[selected_section],
        section_pages
    )

    st.download_button(
        "Download entire section PDF",
        data=complete_section_pdf,
        file_name="section.pdf",
        mime="application/pdf",
        use_container_width=True
    )


# =========================================================
# SEARCH
# =========================================================

st.sidebar.markdown("---")
st.sidebar.subheader("Search")

search_text = st.sidebar.text_input(
    "Search pages",
    key="search_text"
)

if search_text.strip():
    search_results = search_pages(
        user_id,
        search_text.strip()
    )

    if search_results:
        st.sidebar.caption("Results:")

        for result_page_id, result_title, result_section, result_notebook in search_results:
            result_label = (
                f"{result_title} "
                f"({result_notebook} / {result_section})"
            )

            if st.sidebar.button(
                result_label,
                key=f"result_{result_page_id}",
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


st.markdown(
    """
    <div class="footer">
        My Notebook
    </div>
    """,
    unsafe_allow_html=True
)
