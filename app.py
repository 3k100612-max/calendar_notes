import base64
import os
import re
from html import escape

import bleach
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
    initial_sidebar_state="expanded",
)


# =========================================================
# HTML AND IMAGE SANITIZATION
# =========================================================

ALLOWED_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "u",
    "s",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
    "pre",
    "code",
    "ol",
    "ul",
    "li",
    "a",
    "span",
    "img",
]


ALLOWED_ATTRIBUTES = {
    "a": [
        "href",
        "target",
        "rel",
    ],
    "span": [
        "style",
    ],
    "img": [
        "src",
        "alt",
        "width",
        "height",
    ],
}


ALLOWED_IMAGE_TYPES = (
    "data:image/png;base64,",
    "data:image/jpeg;base64,",
    "data:image/jpg;base64,",
    "data:image/gif;base64,",
    "data:image/webp;base64,",
)


def remove_unsafe_images(content):
    """
    Keep only Base64 embedded images.

    External image URLs are removed so that pasted content
    cannot load arbitrary remote resources.
    """

    if not content:
        return ""

    image_pattern = re.compile(
        r"""(<img\b[^>]*\bsrc\s*=\s*["'])([^"']+)(["'][^>]*>)""",
        flags=re.IGNORECASE,
    )

    def replace_image(match):
        prefix = match.group(1)
        source = match.group(2)
        suffix = match.group(3)

        if source.lower().startswith(ALLOWED_IMAGE_TYPES):
            return prefix + source + suffix

        return ""

    return image_pattern.sub(replace_image, content)


def clean_html(content):
    """
    Sanitize Quill HTML while preserving rich-text formatting
    and pasted Base64 images.
    """

    content = content or ""
    content = remove_unsafe_images(content)

    cleaner = bleach.Cleaner(
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=[
            "http",
            "https",
            "mailto",
            "data",
        ],
        strip=True,
    )

    cleaned = cleaner.clean(content)

    cleaned = re.sub(
        r"javascript\s*:",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"expression\s*\([^)]*\)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    return cleaned


def count_embedded_images(content):
    if not content:
        return 0

    return len(
        re.findall(
            r'<img[^>]+src=["\']data:image/',
            content,
            flags=re.IGNORECASE,
        )
    )


def content_size_mb(content):
    if not content:
        return 0

    return len(content.encode("utf-8")) / (1024 * 1024)


# =========================================================
# PAGE STYLE
# =========================================================

st.markdown(
    """
    <style>
        [data-testid="stSidebar"] {
            min-width: 300px;
            max-width: 350px;
        }

        .notebook-header {
            padding: 20px 24px;
            border-radius: 14px;
            background: linear-gradient(
                135deg,
                #2563eb,
                #7c3aed
            );
            color: white;
            margin-bottom: 22px;
        }

        .notebook-header h1 {
            margin: 0;
            font-size: 30px;
        }

        .notebook-header p {
            margin: 6px 0 0 0;
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

        .page-preview img {
            display: block;
            max-width: 100%;
            height: auto;
            margin: 12px 0;
        }

        .page-preview p {
            margin: 8px 0;
        }

        .page-preview ul,
        .page-preview ol {
            margin-left: 24px;
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
            overflow-x: auto;
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
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_connection():
    try:
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            database=os.getenv("DB_NAME", "cal_notes"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "P12345"),
            port=os.getenv("DB_PORT", "5432"),
            connect_timeout=5,
        )

    except Exception as error:
        st.error(f"Database connection error: {error}")
        return None


def init_db():
    conn = get_connection()

    if conn is None:
        return

    cur = None

    try:
        cur = conn.cursor()

        cur.execute(
            "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
        )

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
                    REFERENCES users(id)
                    ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sections (
                id SERIAL PRIMARY KEY,
                notebook_id INTEGER NOT NULL
                    REFERENCES notebooks(id)
                    ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pages (
                id SERIAL PRIMARY KEY,
                section_id INTEGER NOT NULL
                    REFERENCES sections(id)
                    ON DELETE CASCADE,
                title TEXT NOT NULL
                    DEFAULT 'Untitled Page',
                content TEXT NOT NULL
                    DEFAULT '',
                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_notebooks_user_id
                ON notebooks(user_id);

            CREATE INDEX IF NOT EXISTS idx_sections_notebook_id
                ON sections(notebook_id);

            CREATE INDEX IF NOT EXISTS idx_pages_section_id
                ON pages(section_id);

            CREATE INDEX IF NOT EXISTS idx_pages_updated_at
                ON pages(updated_at);
            """
        )

        conn.commit()

    except Exception as error:
        conn.rollback()
        st.error(f"Database setup error: {error}")

    finally:
        if cur:
            cur.close()

        conn.close()


# =========================================================
# AUTHENTICATION
# =========================================================

def create_user(username, password):
    username = (username or "").strip()

    if not username:
        st.error("Username cannot be empty.")
        return False

    if len(password or "") < 6:
        st.error("Password must contain at least 6 characters.")
        return False

    conn = get_connection()

    if conn is None:
        return False

    cur = None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO users (
                username,
                password_hash
            )
            VALUES (
                %s,
                crypt(%s, gen_salt('bf'))
            )
            """,
            (username, password),
        )

        conn.commit()
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
        if cur:
            cur.close()

        conn.close()


def login_user(username, password):
    conn = get_connection()

    if conn is None:
        return None

    cur = None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, username
            FROM users
            WHERE username = %s
              AND password_hash = crypt(
                    %s,
                    password_hash
              )
            """,
            (
                (username or "").strip(),
                password,
            ),
        )

        user = cur.fetchone()

        if user:
            return {
                "id": user[0],
                "username": user[1],
            }

        return None

    except Exception as error:
        st.error(f"Login error: {error}")
        return None

    finally:
        if cur:
            cur.close()

        conn.close()


# =========================================================
# NOTEBOOK FUNCTIONS
# =========================================================

def get_notebooks(user_id):
    conn = get_connection()

    if conn is None:
        return []

    cur = None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, name
            FROM notebooks
            WHERE user_id = %s
            ORDER BY name
            """,
            (user_id,),
        )

        return cur.fetchall()

    finally:
        if cur:
            cur.close()

        conn.close()


def create_notebook(user_id, name):
    name = (name or "").strip()

    if not name:
        return None

    conn = get_connection()

    if conn is None:
        return None

    cur = None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO notebooks (
                user_id,
                name
            )
            VALUES (%s, %s)
            RETURNING id
            """,
            (user_id, name),
        )

        notebook_id = cur.fetchone()[0]
        conn.commit()
        return notebook_id

    except Exception as error:
        conn.rollback()
        st.error(f"Could not create notebook: {error}")
        return None

    finally:
        if cur:
            cur.close()

        conn.close()


def get_sections(notebook_id):
    conn = get_connection()

    if conn is None:
        return []

    cur = None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, name
            FROM sections
            WHERE notebook_id = %s
            ORDER BY name
            """,
            (notebook_id,),
        )

        return cur.fetchall()

    finally:
        if cur:
            cur.close()

        conn.close()


def create_section(notebook_id, name):
    name = (name or "").strip()

    if not name:
        return None

    conn = get_connection()

    if conn is None:
        return None

    cur = None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO sections (
                notebook_id,
                name
            )
            VALUES (%s, %s)
            RETURNING id
            """,
            (notebook_id, name),
        )

        section_id = cur.fetchone()[0]
        conn.commit()
        return section_id

    except Exception as error:
        conn.rollback()
        st.error(f"Could not create section: {error}")
        return None

    finally:
        if cur:
            cur.close()

        conn.close()


# =========================================================
# PAGE FUNCTIONS
# =========================================================

def get_pages(section_id):
    conn = get_connection()

    if conn is None:
        return []

    cur = None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, title, updated_at
            FROM pages
            WHERE section_id = %s
            ORDER BY updated_at DESC
            """,
            (section_id,),
        )

        return cur.fetchall()

    finally:
        if cur:
            cur.close()

        conn.close()


def get_page(page_id):
    conn = get_connection()

    if conn is None:
        return None

    cur = None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                id,
                section_id,
                title,
                content,
                updated_at
            FROM pages
            WHERE id = %s
            """,
            (page_id,),
        )

        return cur.fetchone()

    finally:
        if cur:
            cur.close()

        conn.close()


def create_page(section_id, title="Untitled Page"):
    conn = get_connection()

    if conn is None:
        return None

    cur = None

    try:
        cur = conn.cursor()

        title = (title or "").strip()
        title = title or "Untitled Page"

        cur.execute(
            """
            INSERT INTO pages (
                section_id,
                title,
                content
            )
            VALUES (%s, %s, '')
            RETURNING id
            """,
            (section_id, title),
        )

        page_id = cur.fetchone()[0]
        conn.commit()
        return page_id

    except Exception as error:
        conn.rollback()
        st.error(f"Could not create page: {error}")
        return None

    finally:
        if cur:
            cur.close()

        conn.close()


def save_page(page_id, title, content):
    content = clean_html(content)

    # Maximum page size: 10 MB
    if content_size_mb(content) > 10:
        st.error(
            "This page is larger than 10 MB. "
            "Please resize or remove some images."
        )
        return False

    title = (title or "").strip()
    title = title or "Untitled Page"

    conn = get_connection()

    if conn is None:
        return False

    cur = None

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
                title,
                content,
                page_id,
            ),
        )

        if cur.rowcount == 0:
            conn.rollback()
            st.error("Page not found.")
            return False

        conn.commit()
        return True

    except Exception as error:
        conn.rollback()
        st.error(f"Could not save page: {error}")
        return False

    finally:
        if cur:
            cur.close()

        conn.close()


def delete_page(page_id):
    conn = get_connection()

    if conn is None:
        return False

    cur = None

    try:
        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM pages
            WHERE id = %s
            """,
            (page_id,),
        )

        conn.commit()
        return cur.rowcount > 0

    finally:
        if cur:
            cur.close()

        conn.close()


def search_pages(user_id, search_text):
    conn = get_connection()

    if conn is None:
        return []

    cur = None

    try:
        cur = conn.cursor()

        search_pattern = f"%{search_text}%"

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
                search_pattern,
            ),
        )

        return cur.fetchall()

    finally:
        if cur:
            cur.close()

        conn.close()


# =========================================================
# QUILL RICH-TEXT TOOLBAR
# =========================================================

QUILL_TOOLBAR = [
    [
        "bold",
        "italic",
        "underline",
        "strike",
    ],
    [
        {
            "header": [1, 2, 3, 4, 5, 6, False]
        }
    ],
    [
        {
            "color": []
        },
        {
            "background": []
        },
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
        },
    ],
    [
        {
            "indent": "-1"
        },
        {
            "indent": "+1"
        },
    ],
    [
        "blockquote",
        "code-block",
    ],
    [
        "link",
        "image",
        "clean",
    ],
]


# =========================================================
# PDF FUNCTIONS
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

    .rich-content {
        line-height: 1.6;
        overflow-wrap: anywhere;
    }

    .rich-content img {
        display: block;
        max-width: 100%;
        height: auto;
        margin: 12px 0;
    }

    .rich-content blockquote {
        border-left: 4px solid #9ca3af;
        padding-left: 12px;
        color: #4b5563;
    }

    .rich-content pre {
        background-color: #f3f4f6;
        padding: 12px;
        border-radius: 6px;
        white-space: pre-wrap;
    }

    .rich-content a {
        color: #2563eb;
    }

    .section-page {
        page-break-after: always;
    }

    .section-page:last-child {
        page-break-after: auto;
    }
    """


def build_page_pdf(username, title, content):
    safe_username = escape(username or "")
    safe_title = escape(title or "Untitled Page")
    safe_content = clean_html(content)

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
        <h1>{safe_title}</h1>

        <div class="metadata">
            Created for {safe_username}
        </div>

        <div class="rich-content">
            {safe_content or "<p>No content.</p>"}
        </div>
    </body>
    </html>
    """

    return HTML(string=document).write_pdf()


def build_section_pdf(username, section_name, pages):
    safe_username = escape(username or "")
    safe_section_name = escape(
        section_name or "Untitled Section"
    )

    pages_html = ""

    for page_id, title, updated_at in pages:
        page = get_page(page_id)

        if not page:
            continue

        safe_title = escape(
            page[2] or "Untitled Page"
        )

        safe_content = clean_html(
            page[3] or ""
        )

        safe_updated_at = escape(
            str(updated_at)
        )

        pages_html += f"""
        <section class="section-page">
            <h1>{safe_title}</h1>

            <div class="metadata">
                Updated: {safe_updated_at}
            </div>

            <div class="rich-content">
                {safe_content or "<p>No content.</p>"}
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
        <h1>{safe_section_name}</h1>

        <div class="metadata">
            Created for {safe_username}
        </div>

        {pages_html or "<p>This section has no pages.</p>"}
    </body>
    </html>
    """

    return HTML(string=document).write_pdf()


# =========================================================
# SESSION STATE
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
            <p>Your personal rich-text notebook</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    login_tab, register_tab = st.tabs(
        [
            "Login",
            "Register",
        ]
    )

    with login_tab:
        login_username = st.text_input(
            "Username",
            key="login_username",
        )

        login_password = st.text_input(
            "Password",
            type="password",
            key="login_password",
        )

        if st.button(
            "Login",
            type="primary",
            use_container_width=True,
        ):
            user = login_user(
                login_username,
                login_password,
            )

            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with register_tab:
        register_username = st.text_input(
            "New username",
            key="register_username",
        )

        register_password = st.text_input(
            "New password",
            type="password",
            key="register_password",
        )

        confirm_password = st.text_input(
            "Confirm password",
            type="password",
            key="confirm_password",
        )

        if st.button(
            "Create account",
            use_container_width=True,
        ):
            if register_password != confirm_password:
                st.error("Passwords do not match.")

            elif create_user(
                register_username,
                register_password,
            ):
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
# NOTEBOOK SIDEBAR
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
        ),
    )

    st.session_state.selected_notebook = selected_notebook

else:
    selected_notebook = None
    st.sidebar.info(
        "Create your first notebook."
    )


with st.sidebar.expander("Create notebook"):
    notebook_name = st.text_input(
        "Notebook name",
        key="new_notebook_name",
    )

    if st.button(
        "Create notebook",
        use_container_width=True,
    ):
        notebook_id = create_notebook(
            user_id,
            notebook_name,
        )

        if notebook_id:
            st.session_state.selected_notebook = notebook_id
            st.rerun()


# =========================================================
# SECTION SIDEBAR
# =========================================================

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
            ),
        )

        st.session_state.selected_section = selected_section

    else:
        selected_section = None
        st.sidebar.info(
            "Create your first section."
        )

    with st.sidebar.expander("Create section"):
        section_name = st.text_input(
            "Section name",
            key="new_section_name",
        )

        if st.button(
            "Create section",
            use_container_width=True,
        ):
            section_id = create_section(
                selected_notebook,
                section_name,
            )

            if section_id:
                st.session_state.selected_section = section_id
                st.rerun()

else:
    selected_section = None


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
        unsafe_allow_html=True,
    )

    st.info(
        "Use the sidebar to create a notebook and section."
    )

    st.stop()


# =========================================================
# PAGE SIDEBAR
# =========================================================

pages = get_pages(selected_section)
page_ids = [page[0] for page in pages]

if not page_ids:
    new_page_id = create_page(
        selected_section,
        "Welcome Page",
    )

    if new_page_id:
        st.session_state.selected_page = new_page_id
        st.rerun()

    st.error("Could not create the first page.")
    st.stop()


if st.session_state.selected_page not in page_ids:
    st.session_state.selected_page = page_ids[0]


with st.sidebar:
    st.markdown("---")
    st.subheader("Pages")

    for current_page_id, title, updated_at in pages:
        page_label = title or "Untitled Page"

        if st.button(
            page_label,
            key=f"page_button_{current_page_id}",
            use_container_width=True,
        ):
            st.session_state.selected_page = current_page_id
            st.rerun()

    if st.button(
        "New page",
        use_container_width=True,
    ):
        new_page_id = create_page(
            selected_section,
            "Untitled Page",
        )

        if new_page_id:
            st.session_state.selected_page = new_page_id
            st.rerun()


# =========================================================
# CURRENT PAGE
# =========================================================

page = get_page(
    st.session_state.selected_page
)

if not page:
    st.error(
        "The selected page could not be found."
    )
    st.stop()


page_id = page[0]
page_title = page[2] or "Untitled Page"
page_content = page[3] or ""


# =========================================================
# PAGE HEADER
# =========================================================

safe_notebook_name = escape(
    notebook_names[selected_notebook]
)

safe_section_name = escape(
    section_names[selected_section]
)

st.markdown(
    f"""
    <div class="section-label">
        {safe_notebook_name} / {safe_section_name}
    </div>
    """,
    unsafe_allow_html=True,
)

header_col1, header_col2 = st.columns(
    [
        5,
        1,
    ]
)

with header_col1:
    st.title(page_title)

with header_col2:
    if st.button(
        "Delete page",
        use_container_width=True,
    ):
        if delete_page(page_id):
            st.session_state.selected_page = None
            st.rerun()
        else:
            st.error(
                "Could not delete the page."
            )


# =========================================================
# RICH-TEXT EDITOR
# =========================================================

title_input = st.text_input(
    "Page title",
    value=page_title,
    key=f"title_input_{page_id}",
)

st.caption(
    "Use the toolbar to format text. "
    "You can paste images directly into the editor. "
    "Pasted images are stored inside the page content."
)

content_input = st_quill(
    value=page_content,
    html=True,
    toolbar=QUILL_TOOLBAR,
    placeholder="Start writing your page...",
    key=f"quill_editor_{page_id}",
)

safe_content_input = clean_html(
    content_input
)

image_count = count_embedded_images(
    safe_content_input
)

page_size = content_size_mb(
    safe_content_input
)

if image_count > 0:
    st.info(
        f"{image_count} embedded image(s) detected. "
        f"Page size: {page_size:.2f} MB."
    )

if page_size > 8:
    st.warning(
        "This page is getting large. "
        "Consider resizing images before saving."
    )

if st.button(
    "Save page",
    type="primary",
    use_container_width=True,
):
    if save_page(
        page_id,
        title_input,
        safe_content_input,
    ):
        st.success(
            "Page and embedded images saved successfully."
        )
        st.rerun()
    else:
        st.error(
            "Could not save the page."
        )


# =========================================================
# PREVIEW
# =========================================================

st.markdown("---")
st.subheader("Preview")

preview_content = (
    safe_content_input
    or "<p>Your page preview will appear here.</p>"
)

st.markdown(
    f"""
    <div class="page-preview">
        {preview_content}
    </div>
    """,
    unsafe_allow_html=True,
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
        safe_content_input,
    )

    st.download_button(
        "Download current page PDF",
        data=current_page_pdf,
        file_name="current_page.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

with pdf_col2:
    section_pages = get_pages(
        selected_section
    )

    complete_section_pdf = build_section_pdf(
        username,
        section_names[selected_section],
        section_pages,
    )

    st.download_button(
        "Download entire section PDF",
        data=complete_section_pdf,
        file_name="section.pdf",
        mime="application/pdf",
        use_container_width=True,
    )


# =========================================================
# SEARCH
# =========================================================

st.sidebar.markdown("---")
st.sidebar.subheader("Search")

search_text = st.sidebar.text_input(
    "Search pages",
    key="page_search",
)

if search_text.strip():
    search_results = search_pages(
        user_id,
        search_text.strip(),
    )

    if search_results:
        st.sidebar.caption("Results:")

        for (
            result_page_id,
            result_title,
            result_section,
            result_notebook,
        ) in search_results:

            result_label = (
                f"{result_title} "
                f"({result_notebook} / {result_section})"
            )

            if st.sidebar.button(
                result_label,
                key=f"search_result_{result_page_id}",
                use_container_width=True,
            ):
                st.session_state.selected_page = (
                    result_page_id
                )
                st.rerun()

    else:
        st.sidebar.caption(
            "No pages found."
        )


# =========================================================
# LOGOUT
# =========================================================

st.sidebar.markdown("---")

if st.sidebar.button(
    "Logout",
    use_container_width=True,
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
    unsafe_allow_html=True,
)
