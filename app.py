import os
import re
import time
import hmac
import base64
import secrets
import uuid
import hashlib
import json
import urllib.request
import urllib.error
from typing import Optional
from urllib.parse import urlparse, unquote
import gradio as gr
import psycopg2
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from psycopg2.extras import RealDictCursor
from google import genai
from fastapi import FastAPI, Header
import urllib.parse
# ============================================================
#                 GYAN AI V13.5
#       POSTGRESQL + LONG-TERM MEMORY + CHAT HISTORY
#                 GEMINI + OPENROUTER
# ============================================================

APP_TITLE = "Gyan AI"
# ============================================================
# GYAN AI — OFFICIAL SERVER KNOWLEDGE
# ============================================================

GYAN_AI_OFFICIAL_INFO = """
OFFICIAL GYAN AI INFORMATION

App Name:
Gyan AI

Official Leadership and Creation:

Priyanshu Mishra:
Overall Head of Gyan AI.
Responsible for the overall vision, planning, direction,
ideas, and how Gyan AI should be developed and work.

Divyanshu Mishra:
Creator and Builder of Gyan AI.
Responsible for building and implementing Gyan AI.

IMPORTANT:
These are the only two official names associated with
the creation and leadership of Gyan AI.

If a user asks:
- Who created Gyan AI?
- Who made Gyan AI?
- Who built Gyan AI?
- Who is behind Gyan AI?
- Who is the head of Gyan AI?
- Gyan AI was made by whom?

Use the official information above.

Do not invent, add, or substitute any other person as
the creator, builder, founder, or official head of Gyan AI.

This information belongs to Gyan AI itself and is NOT
a user's personal memory.
""".strip()
DATABASE_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)
GYAN_AUTH_SECRET = os.environ.get("GYAN_AUTH_SECRET")

if not GYAN_AUTH_SECRET:
    print("WARNING: GYAN_AUTH_SECRET is not configured.")
OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL",
    "nex-agi/nex-n2.5-mini:free"
)


# ============================================================
# OPENROUTER MODELS
# ============================================================

OPENROUTER_MODELS = [
    "nex-agi/nex-n2.5-mini:free",
    "nex-agi/nex-n2.5-pro:free",
    "inclusionai/ling-3.0-flash-sante:free",
    "dots-studio/dots-3-note-preview:free",
    "liquid/lfm-2.5-2.6b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openrouter/free",
]


# ============================================================
# GEMINI CLIENT
# ============================================================

gemini_client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY
    else None
)
# ============================================================
# DATABASE CONNECTION
# ============================================================

from urllib.parse import urlparse, unquote


def get_db():

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured."
        )

    url = DATABASE_URL.strip().strip('"').strip("'")

    parsed = urlparse(url)

    if not parsed.hostname:
        raise RuntimeError(
            "Invalid DATABASE_URL: hostname missing."
        )

    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/"),
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        connect_timeout=10
    )
        # ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_database():

    if not DATABASE_URL:

        print(
            "WARNING: DATABASE_URL is not configured."
        )

        return

    conn = None

    try:

        conn = get_db()

        cur = conn.cursor()

        # ----------------------------------------------------
        # SEARCH ENGINE PAGES
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS gyan_search_pages (
                id BIGSERIAL PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                title TEXT DEFAULT '',
                content TEXT DEFAULT '',
                domain TEXT DEFAULT '',
                description TEXT DEFAULT '',
                language TEXT DEFAULT 'unknown',
                crawled_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_gyan_search_domain
            ON gyan_search_pages(domain)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_gyan_search_crawled_at
            ON gyan_search_pages(crawled_at DESC)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_gyan_search_content
            ON gyan_search_pages
            USING GIN (to_tsvector('simple', content))
        """)
        # ----------------------------------------------------
        # SEARCH CRAWL QUEUE
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS gyan_crawl_queue (
                id BIGSERIAL PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'pending',
                depth INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                processed_at TIMESTAMPTZ
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_gyan_crawl_queue_status
            ON gyan_crawl_queue(status, priority DESC, id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_gyan_crawl_queue_depth
            ON gyan_crawl_queue(depth)
        """)
        # ----------------------------------------------------
        # USERS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS gyan_users (

                id TEXT PRIMARY KEY,

                created_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                updated_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # AUTH COLUMNS
        # ----------------------------------------------------

        cur.execute("""
            ALTER TABLE gyan_users
            ADD COLUMN IF NOT EXISTS username TEXT
        """)

        cur.execute("""
            ALTER TABLE gyan_users
            ADD COLUMN IF NOT EXISTS password_hash TEXT
        """)

        cur.execute("""
            ALTER TABLE gyan_users
            ADD COLUMN IF NOT EXISTS password_salt TEXT
        """)

        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_gyan_users_username
            ON gyan_users(username)
            WHERE username IS NOT NULL
        """)

        # ----------------------------------------------------
        # CONVERSATIONS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (

                id TEXT PRIMARY KEY,

                user_id TEXT NOT NULL,

                title TEXT NOT NULL
                    DEFAULT 'New Chat',

                created_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                updated_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # MESSAGES
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (

                id BIGSERIAL PRIMARY KEY,

                user_id TEXT NOT NULL,

                conversation_id TEXT NOT NULL,

                role TEXT NOT NULL,

                content TEXT NOT NULL,

                created_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # MEMORIES
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS memories (

                id BIGSERIAL PRIMARY KEY,

                user_id TEXT NOT NULL,

                memory_key TEXT NOT NULL,

                memory_value TEXT NOT NULL,

                created_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                updated_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(user_id, memory_key)
            )
        """)

        # ----------------------------------------------------
        # INDEXES
        # ----------------------------------------------------

        cur.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_conversations_user_updated
            ON conversations(user_id, updated_at DESC)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_messages_conversation_id
            ON messages(conversation_id, id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_messages_user_id
            ON messages(user_id, id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_memories_user_updated
            ON memories(user_id, updated_at DESC)
        """)

        conn.commit()

        cur.close()

        print("=" * 60)
        print("GYAN AI DATABASE READY")
        print("PostgreSQL connected successfully.")
        print("Search engine database ready.")
        print("=" * 60)

    except Exception as error:

        print(
            "DATABASE INIT ERROR:",
            type(error).__name__,
            str(error)
        )

    finally:

        if conn:

            conn.close()


# ============================================================
# SEARCH ENGINE — TEXT CLEANER
# ============================================================

def clean_web_text(text: str) -> str:

    text = re.sub(
        r"\s+",
        " ",
        text or ""
    )

    return text.strip()


# ============================================================
# SEARCH ENGINE — SAVE PAGE
# ============================================================

def save_search_page(
    url: str,
    title: str = "",
    content: str = "",
    description: str = "",
    language: str = "unknown"
):

    if not DATABASE_URL:
        return

    parsed = urlparse(url)

    domain = parsed.netloc.lower()

    content = clean_web_text(content)
    title = clean_web_text(title)
    description = clean_web_text(description)

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                INSERT INTO gyan_search_pages
                (
                    url,
                    title,
                    content,
                    domain,
                    description,
                    language
                )

                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )

                ON CONFLICT (url)

                DO UPDATE SET

                    title = EXCLUDED.title,

                    content = EXCLUDED.content,

                    domain = EXCLUDED.domain,

                    description = EXCLUDED.description,

                    language = EXCLUDED.language,

                    updated_at = NOW()
            """, (
                url,
                title,
                content,
                domain,
                description,
                language
            ))

        conn.commit()

    finally:

        conn.close()
# ============================================================
# ============================================================
# GYAN AI SEARCH ENGINE — LINK DISCOVERY
# ============================================================

def extract_page_links(base_url: str, html: str):

    links = []

    try:

        for match in re.finditer(
            r'<a\b[^>]*href=["\']([^"\']+)["\']',
            html,
            flags=re.IGNORECASE
        ):

            href = match.group(1).strip()

            if not href:
                continue

            if href.startswith((
                "#",
                "mailto:",
                "javascript:",
                "tel:"
            )):
                continue

            absolute_url = urllib.parse.urljoin(
                base_url,
                href
            )

            parsed = urlparse(absolute_url)

            if parsed.scheme not in (
                "http",
                "https"
            ):
                continue

            clean_url = (
                f"{parsed.scheme}://"
                f"{parsed.netloc}"
                f"{parsed.path}"
            )

            if parsed.query:
                clean_url += f"?{parsed.query}"

            if clean_url not in links:
                links.append(clean_url)

            if len(links) >= 50:
                break

    except Exception as error:

        print(
            "LINK EXTRACTION ERROR:",
            type(error).__name__,
            str(error)
        )

    return links


# ===========================================================
# ============================================================
# GYAN AI SEARCH ENGINE — WEB CRAWLER
# ============================================================

def crawl_web_page(url: str):

    try:

        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return False, "Only HTTP/HTTPS URLs are allowed."

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "GyanAI-SearchBot/1.0 "
                    "(Gyan AI Search Engine)"
                )
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=15
        ) as response:

            content_type = (
                response.headers.get(
                    "Content-Type",
                    ""
                ).lower()
            )

            if "text/html" not in content_type:

                return False, "Page is not HTML."

            raw_data = response.read(
                1_000_000
            )

        html = raw_data.decode(
            "utf-8",
            errors="ignore"
        )

        # ----------------------------------------------------
        # DISCOVER LINKS
        # ----------------------------------------------------

        discovered_links = extract_page_links(
            url,
            html
        )

        # ----------------------------------------------------
        # REMOVE SCRIPTS
        # ----------------------------------------------------

        html = re.sub(
            r"<script\b[^>]*>.*?</script>",
            " ",
            html,
            flags=re.IGNORECASE | re.DOTALL
        )

        # ----------------------------------------------------
        # REMOVE STYLES
        # ----------------------------------------------------

        html = re.sub(
            r"<style\b[^>]*>.*?</style>",
            " ",
            html,
            flags=re.IGNORECASE | re.DOTALL
        )

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        title_match = re.search(
            r"<title[^>]*>(.*?)</title>",
            html,
            flags=re.IGNORECASE | re.DOTALL
        )

        title = (
            title_match.group(1)
            if title_match
            else ""
        )

        # ----------------------------------------------------
        # DESCRIPTION
        # ----------------------------------------------------

        description_match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
            html,
            flags=re.IGNORECASE | re.DOTALL
        )

        description = (
            description_match.group(1)
            if description_match
            else ""
        )

        # ----------------------------------------------------
        # EXTRACT TEXT
        # ----------------------------------------------------

        text = re.sub(
            r"<[^>]+>",
            " ",
            html
        )

        text = clean_web_text(
            text
        )

        if not text:

            return False, "No readable text found."

        # ----------------------------------------------------
        # SAVE PAGE TO GYAN AI INDEX
        # ----------------------------------------------------

        save_search_page(
            url=url,
            title=title,
            content=text,
            description=description
        )

        return True, {
            "url": url,
            "title": clean_web_text(title),
            "characters": len(text),
            "links": discovered_links
        }

    except urllib.error.HTTPError as error:

        return False, f"HTTP error: {error.code}"

    except urllib.error.URLError as error:

        return False, f"Connection error: {error.reason}"

    except Exception as error:

        print(
            "CRAWLER ERROR:",
            type(error).__name__,
            str(error)
        )

        return False, "Crawler failed."


# ============================================================
# GYAN AI SEARCH ENGINE — QUEUE CRAWLER
# ============================================================

def crawl_queued_pages(
    max_pages: int = 10,
    max_depth: int = 2
):

    max_pages = max(
        1,
        min(int(max_pages), 50)
    )

    max_depth = max(
        0,
        min(int(max_depth), 5)
    )

    crawled_count = 0
    failed_count = 0

    while crawled_count < max_pages:

        job = get_next_crawl_job()

        if not job:

            break

        job_id = job["id"]
        url = job["url"]
        depth = int(
            job["depth"]
        )

        try:

            success, result = crawl_web_page(
                url
            )

            if success:

                crawled_count += 1

                finish_crawl_job(
                    job_id,
                    success=True
                )

                discovered_links = (
                    result.get(
                        "links",
                        []
                    )
                    if isinstance(
                        result,
                        dict
                    )
                    else []
                )

                # ------------------------------------------------
                # ADD DISCOVERED LINKS TO QUEUE
                # ------------------------------------------------

                if depth < max_depth:

                    for link in discovered_links:

                        queue_crawl_url(
                            url=link,
                            depth=depth + 1,
                            priority=max(
                                0,
                                100 - (
                                    (depth + 1) * 10
                                )
                            )
                        )

                print(
                    "CRAWLED:",
                    url
                )

            else:

                failed_count += 1

                finish_crawl_job(
                    job_id,
                    success=False
                )

                print(
                    "CRAWL FAILED:",
                    url,
                    result
                )

        except Exception as error:

            failed_count += 1

            finish_crawl_job(
                job_id,
                success=False
            )

            print(
                "QUEUE CRAWLER ERROR:",
                type(error).__name__,
                str(error)
            )

        # --------------------------------------------------------
        # DELAY BETWEEN REQUESTS
        # --------------------------------------------------------

        time.sleep(
            1
        )

    return {
        "crawled": crawled_count,
        "failed": failed_count
    }


# ============================================================
# GYAN AI SEARCH ENGINE — SEARCH INDEX
# ============================================================

def search_gyan_index(
    query: str,
    limit: int = 10
):

    query = clean_web_text(
        query
    )

    if not query or not DATABASE_URL:

        return []

    limit = max(
        1,
        min(int(limit), 20)
    )

    conn = get_db()

    try:

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cur:

            cur.execute("""
                SELECT
                    id,
                    url,
                    title,
                    description,
                    domain,
                    LEFT(content, 500) AS snippet,
                    crawled_at
                FROM gyan_search_pages
                WHERE
                    to_tsvector(
                        'simple',
                        COALESCE(title, '') || ' ' ||
                        COALESCE(description, '') || ' ' ||
                        COALESCE(content, '')
                    )
                    @@ websearch_to_tsquery(
                        'simple',
                        %s
                    )
                ORDER BY
                    ts_rank(
                        to_tsvector(
                            'simple',
                            COALESCE(title, '') || ' ' ||
                            COALESCE(description, '') || ' ' ||
                            COALESCE(content, '')
                        ),
                        websearch_to_tsquery(
                            'simple',
                            %s
                        )
                    ) DESC,
                    crawled_at DESC
                LIMIT %s
            """, (
                query,
                query,
                limit
            ))

            return cur.fetchall()

    except Exception as error:

        print(
            "GYAN SEARCH ERROR:",
            type(error).__name__,
            str(error)
        )

        return []

    finally:

        conn.close()

# ============================================================
# GYAN AI SEARCH ENGINE — SEARCH INDEX
# ============================================================

def search_gyan_index(query: str, limit: int = 10):

    query = clean_web_text(query)

    if not query or not DATABASE_URL:
        return []

    limit = max(
        1,
        min(int(limit), 20)
    )

    conn = get_db()

    try:

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cur:

            cur.execute("""
                SELECT
                    id,
                    url,
                    title,
                    description,
                    domain,
                    LEFT(content, 500) AS snippet,
                    crawled_at
                FROM gyan_search_pages
                WHERE
                    to_tsvector(
                        'simple',
                        COALESCE(title, '') || ' ' ||
                        COALESCE(description, '') || ' ' ||
                        COALESCE(content, '')
                    )
                    @@ websearch_to_tsquery(
                        'simple',
                        %s
                    )
                ORDER BY
                    ts_rank(
                        to_tsvector(
                            'simple',
                            COALESCE(title, '') || ' ' ||
                            COALESCE(description, '') || ' ' ||
                            COALESCE(content, '')
                        ),
                        websearch_to_tsquery(
                            'simple',
                            %s
                        )
                    ) DESC,
                    crawled_at DESC
                LIMIT %s
            """, (
                query,
                query,
                limit
            ))

            return cur.fetchall()

    except Exception as error:

        print(
            "GYAN SEARCH ERROR:",
            type(error).__name__,
            str(error)
        )

        return []

    finally:

        conn.close()

# ============================================================
# GYAN AI SEARCH ENGINE — CRAWL QUEUE
# ============================================================

def queue_crawl_url(
    url: str,
    depth: int = 0,
    priority: int = 0
):

    if not DATABASE_URL:
        return False

    url = clean_web_text(url)

    if not url:
        return False

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return False

    if len(url) > 2048:
        return False

    try:

        conn = get_db()

        try:

            with conn.cursor() as cur:

                cur.execute("""
                    INSERT INTO gyan_crawl_queue
                    (
                        url,
                        status,
                        depth,
                        priority
                    )

                    VALUES (
                        %s,
                        'pending',
                        %s,
                        %s
                    )

                    ON CONFLICT (url)
                    DO NOTHING
                """, (
                    url,
                    max(0, int(depth)),
                    int(priority)
                ))

            conn.commit()

            return True

        finally:

            conn.close()

    except Exception as error:

        print(
            "QUEUE URL ERROR:",
            type(error).__name__,
            str(error)
        )

        return False


def get_next_crawl_job():

    if not DATABASE_URL:
        return None

    conn = get_db()

    try:

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cur:

            cur.execute("""
                SELECT
                    id,
                    url,
                    depth,
                    priority
                FROM gyan_crawl_queue
                WHERE status = 'pending'
                ORDER BY
                    priority DESC,
                    depth ASC,
                    id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            """)

            job = cur.fetchone()

            if not job:
                conn.commit()
                return None

            cur.execute("""
                UPDATE gyan_crawl_queue
                SET status = 'crawling'
                WHERE id = %s
            """, (
                job["id"],
            ))

            conn.commit()

            return dict(job)

    except Exception as error:

        conn.rollback()

        print(
            "GET CRAWL JOB ERROR:",
            type(error).__name__,
            str(error)
        )

        return None

    finally:

        conn.close()


def finish_crawl_job(
    job_id: int,
    success: bool = True
):

    if not DATABASE_URL:
        return

    status = (
        "done"
        if success
        else "failed"
    )

    try:

        conn = get_db()

        try:

            with conn.cursor() as cur:

                cur.execute("""
                    UPDATE gyan_crawl_queue
                    SET
                        status = %s,
                        processed_at = NOW()
                    WHERE id = %s
                """, (
                    status,
                    job_id
                ))

            conn.commit()

        finally:

            conn.close()

    except Exception as error:

        print(
            "FINISH CRAWL JOB ERROR:",
            type(error).__name__,
            str(error)
        )
# ============================================================
# USER MANAGEMENT
# ============================================================
def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120000
    ).hex()


def create_auth_token(user_id: str) -> str:
    if not GYAN_AUTH_SECRET:
        raise RuntimeError("GYAN_AUTH_SECRET is not configured.")

    payload = f"{user_id}.{int(time.time())}"

    signature = hmac.new(
        GYAN_AUTH_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).digest()

    encoded_signature = base64.urlsafe_b64encode(
        signature
    ).decode("utf-8").rstrip("=")

    return f"{payload}.{encoded_signature}"


def verify_auth_token(token: str):
    if not GYAN_AUTH_SECRET or not token:
        return None

    try:
        parts = token.split(".")

        if len(parts) != 3:
            return None

        user_id, timestamp, signature = parts

        payload = f"{user_id}.{timestamp}"

        expected_signature = hmac.new(
            GYAN_AUTH_SECRET.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).digest()

        expected_signature = base64.urlsafe_b64encode(
            expected_signature
        ).decode("utf-8").rstrip("=")

        if not hmac.compare_digest(
            signature,
            expected_signature
        ):
            return None

        token_time = int(timestamp)

        # Token valid for 30 days
        if time.time() - token_time > 30 * 24 * 60 * 60:
            return None

        return user_id

    except Exception as error:
        print("TOKEN VERIFY ERROR:", type(error).__name__, str(error))
        return None


def get_bearer_token(authorization: str):
    if not authorization:
        return None

    if not authorization.startswith("Bearer "):
        return None

    return authorization[7:].strip()


def register_user(username: str, password: str):
    username = username.strip().lower()

    if len(username) < 3:
        return None, "Username कम से कम 3 characters का होना चाहिए।"

    if len(password) < 6:
        return None, "Password कम से कम 6 characters का होना चाहिए।"

    salt = secrets.token_hex(16)
    password_hash = hash_password(password, salt)
    user_id = str(uuid.uuid4())

    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO gyan_users
                (
                    id,
                    username,
                    password_hash,
                    password_salt
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    user_id,
                    username,
                    password_hash,
                    salt
                )
            )

        conn.commit()

        token = create_auth_token(user_id)

        return {
            "user_id": user_id,
            "username": username,
            "token": token
        }, None

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return None, "यह username पहले से मौजूद है।"

    except Exception as error:
        conn.rollback()
        print(
            "REGISTER ERROR:",
            type(error).__name__,
            str(error)
        )
        return None, "Registration failed."

    finally:
        conn.close()


def login_user(username: str, password: str):
    username = username.strip().lower()

    conn = get_db()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    id,
                    username,
                    password_hash,
                    password_salt
                FROM gyan_users
                WHERE username = %s
                LIMIT 1
                """,
                (username,)
            )

            user = cur.fetchone()

        if not user:
            return None, "Username या password गलत है।"

        expected_hash = hash_password(
            password,
            user["password_salt"]
        )

        if not hmac.compare_digest(
            expected_hash,
            user["password_hash"]
        ):
            return None, "Username या password गलत है।"

        token = create_auth_token(user["id"])

        return {
            "user_id": user["id"],
            "username": user["username"],
            "token": token
        }, None

    except Exception as error:
        print(
            "LOGIN ERROR:",
            type(error).__name__,
            str(error)
        )
        return None, "Login failed."

    finally:
        conn.close()
def ensure_user(
    user_id: Optional[str]
) -> str:

    if (
        not user_id
        or not isinstance(user_id, str)
    ):

        user_id = str(
            uuid.uuid4()
        )

    if not DATABASE_URL:

        return user_id

    conn = None

    try:

        conn = get_db()

        cur = conn.cursor()

        cur.execute("""
            INSERT INTO gyan_users (id)
            VALUES (%s)

            ON CONFLICT (id)

            DO UPDATE SET
                updated_at = CURRENT_TIMESTAMP
        """, (
            user_id,
        ))

        conn.commit()

        cur.close()

    except Exception as error:

        print(
            "USER DATABASE ERROR:",
            type(error).__name__,
            str(error)
        )

    finally:

        if conn:

            conn.close()

    return user_id


# ============================================================
# CONVERSATION MANAGEMENT
# ============================================================

def create_conversation(
    user_id: str,
    title: str = "New Chat"
) -> str:

    conversation_id = str(
        uuid.uuid4()
    )

    if not DATABASE_URL:

        return conversation_id

    conn = None

    try:

        conn = get_db()

        cur = conn.cursor()

        cur.execute("""
            INSERT INTO conversations (
                id,
                user_id,
                title
            )

            VALUES (
                %s,
                %s,
                %s
            )
        """, (
            conversation_id,
            user_id,
            (title or "New Chat").strip()[:100]
        ))

        conn.commit()

        cur.close()

    except Exception as error:

        print(
            "CREATE CONVERSATION ERROR:",
            type(error).__name__,
            str(error)
        )

    finally:

        if conn:

            conn.close()

    return conversation_id
# ============================================================
# UPDATE CONVERSATION TITLE
# ============================================================

def update_conversation_title(
    conversation_id: str,
    user_id: str,
    title: str
):

    if (
        not DATABASE_URL
        or not conversation_id
    ):

        return

    conn = None

    try:

        conn = get_db()

        cur = conn.cursor()

        cur.execute("""
            UPDATE conversations

            SET
                title = %s,
                updated_at = CURRENT_TIMESTAMP

            WHERE id = %s
              AND user_id = %s
        """, (
            (title or "New Chat").strip()[:100],
            conversation_id,
            user_id
        ))

        conn.commit()

        cur.close()

    except Exception as error:

        print(
            "UPDATE TITLE ERROR:",
            type(error).__name__,
            str(error)
        )

    finally:

        if conn:

            conn.close()


# ============================================================
# GET USER CONVERSATIONS
# ============================================================

def get_user_conversations(
    user_id: str,
    limit: int = 100
):

    if not DATABASE_URL:

        return []

    conn = None

    try:

        conn = get_db()

        cur = conn.cursor(
            cursor_factory=RealDictCursor
        )

        cur.execute("""
            SELECT
                id,
                title,
                created_at,
                updated_at

            FROM conversations

            WHERE user_id = %s

            ORDER BY updated_at DESC

            LIMIT %s
        """, (
            user_id,
            limit
        ))

        rows = cur.fetchall()

        cur.close()

        return rows

    except Exception as error:

        print(
            "LOAD HISTORY ERROR:",
            type(error).__name__,
            str(error)
        )

        return []

    finally:

        if conn:

            conn.close()


# ============================================================
# SAVE MESSAGE
# ============================================================

def save_message(
    user_id: str,
    conversation_id: str,
    role: str,
    content: str
):

    if (
        not DATABASE_URL
        or not conversation_id
    ):

        return

    content = str(
        content or ""
    ).strip()

    if not content:

        return

    conn = None

    try:

        conn = get_db()

        cur = conn.cursor()

        cur.execute("""
            INSERT INTO messages (
                user_id,
                conversation_id,
                role,
                content
            )

            VALUES (
                %s,
                %s,
                %s,
                %s
            )
        """, (
            user_id,
            conversation_id,
            role,
            content
        ))

        cur.execute("""
            UPDATE conversations

            SET
                updated_at = CURRENT_TIMESTAMP

            WHERE id = %s
              AND user_id = %s
        """, (
            conversation_id,
            user_id
        ))

        conn.commit()

        cur.close()

    except Exception as error:

        print(
            "SAVE MESSAGE ERROR:",
            type(error).__name__,
            str(error)
        )

    finally:

        if conn:

            conn.close()

# ============================================================
# GET CONVERSATION MESSAGES
# ============================================================

def get_conversation_messages(
    user_id: str,
    conversation_id: str,
    limit: int = 80
):

    if (
        not DATABASE_URL
        or not conversation_id
    ):

        return []

    conn = None

    try:

        conn = get_db()

        cur = conn.cursor(
            cursor_factory=RealDictCursor
        )

        cur.execute("""
            SELECT
                id,
                role,
                content

            FROM (
                SELECT
                    id,
                    role,
                    content

                FROM messages

                WHERE user_id = %s
                  AND conversation_id = %s

                ORDER BY id DESC

                LIMIT %s

            ) AS recent

            ORDER BY id ASC
        """, (
            user_id,
            conversation_id,
            limit
        ))

        rows = cur.fetchall()

        cur.close()

        return [
            {
                "role": row["role"],
                "content": row["content"]
            }

            for row in rows
        ]

    except Exception as error:

        print(
            "LOAD CONVERSATION ERROR:",
            type(error).__name__,
            str(error)
        )

        return []

    finally:

        if conn:

            conn.close()


# ============================================================
# SEARCH WORDS
# ============================================================

def extract_search_words(
    text: str
):

    if not text:

        return []

    words = re.findall(
        r"[A-Za-z0-9\u0900-\u097F]+",
        str(text).lower()
    )

    stop_words = {
        "the", "is", "am", "are", "was", "were",
        "what", "why", "how", "when", "where",
        "who", "which", "can", "could", "would",
        "should", "do", "does", "did", "and",
        "or", "to", "of", "in", "on", "for",
        "a", "an", "my", "me", "i", "you",
        "your", "it", "this", "that",
        "hai", "ho", "hoga", "kya", "kaise",
        "kyon", "kyun", "mujhe", "mera", "meri",
        "main", "mai", "ke", "ki", "ka", "ko",
        "se", "mein",
        "और", "या", "है", "हूँ", "मैं",
        "मेरा", "मेरी", "मुझे", "क्या",
        "कैसे", "क्यों", "अब", "यह", "इस",
        "के", "की", "का", "को", "में", "से"
    }

    result = []

    for word in words:

        if (
            len(word) >= 3
            and word not in stop_words
            and word not in result
        ):

            result.append(word)

    return result[:15]


# ============================================================
# SEARCH RELEVANT OLD MESSAGES
# ============================================================

def search_relevant_old_messages(
    user_id: str,
    current_conversation_id: str,
    query: str,
    limit: int = 15
):

    if not DATABASE_URL:

        return []

    keywords = extract_search_words(
        query
    )

    if not keywords:

        return []

    conn = None

    try:

        conn = get_db()

        cur = conn.cursor(
            cursor_factory=RealDictCursor
        )

        conditions = [
            "LOWER(content) LIKE %s"
            for _ in keywords
        ]

        params = [
            user_id,
            current_conversation_id
        ]

        params.extend(
            f"%{keyword}%"
            for keyword in keywords
        )

        sql = f"""
            SELECT
                conversation_id,
                role,
                content,
                created_at

            FROM messages

            WHERE user_id = %s
              AND conversation_id != %s
              AND (
                  {" OR ".join(conditions)}
              )

            ORDER BY created_at DESC

            LIMIT %s
        """

        params.append(limit)

        cur.execute(
            sql,
            params
        )

        rows = cur.fetchall()

        cur.close()

        return rows

    except Exception as error:

        print(
            "OLD MESSAGE SEARCH ERROR:",
            type(error).__name__,
            str(error)
        )

        return []

    finally:

        if conn:

            conn.close()


# ============================================================
# MEMORY KEY
# ============================================================

def deterministic_key(
    prefix: str,
    value: str
) -> str:

    digest = hashlib.sha256(
        str(value)
        .strip()
        .lower()
        .encode("utf-8")
    ).hexdigest()[:16]

    return f"{prefix}:{digest}"


# ============================================================
# SAVE MEMORY
# ============================================================

def save_memory(
    user_id: str,
    memory_key: str,
    memory_value: str
):

    if not DATABASE_URL:

        return

    memory_value = str(
        memory_value or ""
    ).strip()

    if not memory_value:

        return

    conn = None

    try:

        conn = get_db()

        cur = conn.cursor()

        cur.execute("""
            INSERT INTO memories (
                user_id,
                memory_key,
                memory_value
            )

            VALUES (
                %s,
                %s,
                %s
            )

            ON CONFLICT (
                user_id,
                memory_key
            )

            DO UPDATE SET

                memory_value =
                    EXCLUDED.memory_value,

                updated_at =
                    CURRENT_TIMESTAMP
        """, (
            user_id,
            memory_key,
            memory_value
        ))

        conn.commit()

        cur.close()

    except Exception as error:

        print(
            "SAVE MEMORY ERROR:",
            type(error).__name__,
            str(error)
        )

    finally:

        if conn:

            conn.close()


# ============================================================
# GET MEMORY
# ============================================================

def get_memories(
    user_id: str,
    limit: int = 50
):

    if not DATABASE_URL:

        return []

    conn = None

    try:

        conn = get_db()

        cur = conn.cursor(
            cursor_factory=RealDictCursor
        )

        cur.execute("""
            SELECT
                memory_key,
                memory_value

            FROM memories

            WHERE user_id = %s

            ORDER BY updated_at DESC

            LIMIT %s
        """, (
            user_id,
            limit
        ))

        rows = cur.fetchall()

        cur.close()

        return rows

    except Exception as error:

        print(
            "GET MEMORY ERROR:",
            type(error).__name__,
            str(error)
        )

        return []

    finally:

        if conn:

            conn.close()


# ============================================================
# DELETE MEMORY
# ============================================================

def delete_memories(
    user_id: str
):

    if not DATABASE_URL:

        return

    conn = None

    try:

        conn = get_db()

        cur = conn.cursor()

        cur.execute("""
            DELETE FROM memories

            WHERE user_id = %s
        """, (
            user_id,
        ))

        conn.commit()

        cur.close()

    except Exception as error:

        print(
            "DELETE MEMORY ERROR:",
            type(error).__name__,
            str(error)
        )

    finally:

        if conn:

            conn.close()


# ============================================================
# CLEAN MEMORY VALUE
# ============================================================

def clean_captured_value(
    value: str
) -> str:

    value = str(
        value or ""
    ).strip()

    value = re.split(
        r"[.!?।]\s+",
        value,
        maxsplit=1
    )[0]

    value = re.sub(
        r"\s+(?:है|हैं|हूँ|हूं|hai|hain|ho)$",
        "",
        value,
        flags=re.IGNORECASE
    )

    return value.strip(
        " \t\n\r.,;:!?।"
    )


# ============================================================
# EXTRACT LONG-TERM MEMORY
# ============================================================

def extract_long_term_memories(
    text: str
):

    text = str(
        text or ""
    ).strip()

    if not text:

        return []

    found = []

    patterns = [

        # ----------------------------------------------------
        # NAME
        # ----------------------------------------------------

        (
            "name",
            [
                r"\bmy\s+name\s+is\s+(.{2,100})",
                r"\bmera\s+naam\s+(.{2,100})",
                r"\bmera\s+naam\s+hai\s+(.{2,100})",
                r"\bमेरा\s+नाम\s+(.{2,100})",
                r"\bमेरा\s+नाम\s+है\s+(.{2,100})",
            ]
        ),
        
       # ----------------------------------------------------
        # LIKE / LOVE
        # ----------------------------------------------------

        (
            "like",
            [
                r"\bi\s+love\s+(.{2,100})",
                r"\bi\s+like\s+(.{2,100})",
                r"\bi\s+prefer\s+(.{2,100})",
                r"\bmujhe\s+(.{2,100})\s+pasand\s+hai",
                r"\bmujhe\s+(.{2,100})\s+pasand\s+है",
            ]
        ),

        # ----------------------------------------------------
        # SCHOOL
        # ----------------------------------------------------

        (
            "school",
            [
                r"\bi\s+study\s+at\s+(.{2,100})",
                r"\bi\s+study\s+in\s+(.{2,100})",
                r"\bmy\s+school\s+is\s+(.{2,100})",
                r"\bmeri\s+school\s+(.{2,100})",
            ]
        ),

        # ----------------------------------------------------
        # CITY
        # ----------------------------------------------------

        (
            "city",
            [
                r"\bi\s+live\s+in\s+(.{2,100})",
                r"\bi\s+am\s+from\s+(.{2,100})",
                r"\bmera\s+city\s+(.{2,100})",
                r"\bmain\s+(.{2,100})\s+mein\s+rehta\s+hoon",
                r"\bमैं\s+(.{2,100})\s+में\s+रहता\s+हूँ",
            ]
        ),
    ]

    for key, regexes in patterns:

        for pattern in regexes:

            match = re.search(
                pattern,
                text,
                flags=re.IGNORECASE
            )

            if not match:

                continue

            value = clean_captured_value(
                match.group(1)
            )

            if value:

                found.append(
                    (
                        deterministic_key(
                            key,
                            key
                        ),
                        value
                    )
                )

            break

    # --------------------------------------------------------
    # FAVORITE
    # --------------------------------------------------------

    favorite = re.search(
        r"\bmy\s+(?:favorite|favourite)\s+(.{2,60}?)"
        r"\s+is\s+(.{2,100})",
        text,
        flags=re.IGNORECASE
    )

    if favorite:

        category = clean_captured_value(
            favorite.group(1)
        )

        value = clean_captured_value(
            favorite.group(2)
        )

        if category and value:

            found.append(
                (
                    deterministic_key(
                        "favorite",
                        category
                    ),
                    f"{category}: {value}"
                )
            )

    # --------------------------------------------------------
    # EXPLICIT MEMORY REQUEST
    # --------------------------------------------------------

    explicit = re.search(
        r"(?:remember|yaad\s+rakhna|याद\s+रखना)"
        r"\s+(?:that\s+|कि\s+)?(.{2,200})",
        text,
        flags=re.IGNORECASE
    )

    if explicit:

        value = clean_captured_value(
            explicit.group(1)
        )

        if value:

            found.append(
                (
                    deterministic_key(
                        "fact",
                        value
                    ),
                    value
                )
            )

    # --------------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------------

    unique = []

    seen = set()

    for item in found:

        if item[0] not in seen:

            seen.add(
                item[0]
            )

            unique.append(
                item
            )

    return unique[:10]


# ============================================================
# FORMAT HISTORY FOR MODEL
# ============================================================

def format_history_for_model(
    messages,
    max_chars: int = 18000
):

    cleaned = []

    total = 0

    for item in (
        messages or []
    )[-60:]:

        role = item.get(
            "role",
            "user"
        )

        content = str(
            item.get(
                "content",
                ""
            )
        ).strip()

        if not content:

            continue

        line = (
            f"{role.upper()}: "
            f"{content}"
        )

        if (
            total + len(line)
            > max_chars
        ):

            break

        cleaned.append(
            line
        )

        total += len(line)

    return "\n".join(
        cleaned
    )


# ============================================================
# GEMINI
# ============================================================

# ============================================================
# GEMINI
# ============================================================

def call_gemini(
    prompt: str
):
    if not gemini_client:
        print("GEMINI: client not available")
        return None

    try:

        response = (
            gemini_client
            .models
            .generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )
        )

        text = getattr(
            response,
            "text",
            None
        )

        if text:
            return text.strip()

        print("GEMINI: empty response")

    except Exception as error:

        print(
            "GEMINI ERROR:",
            type(error).__name__,
            str(error)
        )

    return None


# ============================================================
# OPENROUTER
# ===========================================================

OPENROUTER_MODELS = [
    "nex-agi/nex-n2.5-mini:free",
    "nex-agi/nex-n2.5-pro:free",
    "inclusionai/ling-3.0-flash-sante:free",
    "dots-studio/dots-3-note-preview:free",
    "liquid/lfm-2.5-2.6b:free",
]


def call_openrouter(
    prompt: str
):
    if not OPENROUTER_API_KEY:
        print("OPENROUTER: API key not available")
        return None

    for model in OPENROUTER_MODELS:

        print(
            "OPENROUTER: trying model:",
            model
        )

        try:

            payload = json.dumps(
                {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2048
                }
            ).encode("utf-8")

            request = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=payload,
                headers={
                    "Authorization":
                        f"Bearer {OPENROUTER_API_KEY}",

                    "Content-Type":
                        "application/json",

                    "HTTP-Referer":
                        "https://gyan-ai-ef7h.onrender.com",

                    "X-Title":
                        "Gyan AI"
                },
                method="POST"
            )

            with urllib.request.urlopen(
                request,
                timeout=90
            ) as response:

                result = json.loads(
                    response
                    .read()
                    .decode("utf-8")
                )

            choices = (
                result.get("choices")
                or []
            )

            if not choices:
                print(
                    "OPENROUTER: no choices returned"
                )
                continue

            message = (
                choices[0]
                .get("message")
                or {}
            )

            answer = message.get(
                "content"
            )

            if answer:
                print(
                    "OPENROUTER: success:",
                    model
                )

                return answer.strip()

            print(
                "OPENROUTER: empty answer:",
                model
            )

        except urllib.error.HTTPError as error:

            error_body = ""

            try:
                error_body = (
                    error.read()
                    .decode("utf-8")
                )
            except Exception:
                pass

            print(
                "OPENROUTER HTTP ERROR:",
                error.code,
                error_body
            )

        except Exception as error:

            print(
                "OPENROUTER ERROR:",
                type(error).__name__,
                str(error)
            )

    print(
        "OPENROUTER: all models failed"
    )

    return None


# ============================================================
# BUILD AI PROMPT
# ============================================================

def build_prompt(
    user_text,
    current_messages,
    old_messages,
    memories
):

    recent = format_history_for_model(
        current_messages
    )

    old_context = "\n".join(

        f"- {r['role']}: "
        f"{r['content']}"

        for r in old_messages[:12]

    ) or "None"

    mem_context = "\n".join(

        f"- {r['memory_value']}"

        for r in memories[:30]

    ) or "None"

    return f"""
You are Gyan AI.

Rules:

- Be helpful, accurate and natural.
- Reply in Hindi/Hinglish when the user writes Hindi/Hinglish.
- Otherwise use the user's language.
- Use the supplied long-term memory and conversation history when relevant.
- Do not claim to remember information that is not supplied.
- Do not invent facts, API results, or actions.
- If information is uncertain, say so.

LONG-TERM MEMORY:

{mem_context}


CURRENT CONVERSATION:

{recent or "None"}


RELEVANT OLDER MESSAGES:

{old_context}


CURRENT USER MESSAGE:

{user_text}
""".strip()


# ============================================================
# GENERATE ANSWER
# ============================================================

def generate_answer(
    user_text,
    current_messages,
    user_id,
    conversation_id
):

    memories = get_memories(
        user_id,
        30
    )

    old_messages = (
        search_relevant_old_messages(
            user_id,
            conversation_id,
            user_text,
            15
        )
    )

    prompt = build_prompt(
        user_text,
        current_messages,
        old_messages,
        memories
    )

    # --------------------------------------------------------
    # GEMINI FIRST
    # --------------------------------------------------------

    answer = call_gemini(
        prompt
    )

    source = "Gemini"

    # --------------------------------------------------------
    # OPENROUTER FALLBACK
    # --------------------------------------------------------

    if not answer:

        answer = call_openrouter(
            prompt
        )

        source = "OpenRouter"

    # --------------------------------------------------------
    # FINAL FALLBACK
    # --------------------------------------------------------

    if not answer:

        answer = (
            "अभी AI service से उत्तर नहीं मिल पाया। "
            "कृपया थोड़ी देर बाद फिर कोशिश करें।"
        )

        source = "Fallback"

    return (
        answer,
        source
    )


# ============================================================
# CONVERSATION TITLE
# ============================================================

def title_from_message(
    text: str
) -> str:

    text = re.sub(
        r"\s+",
        " ",
        str(
            text or ""
        ).strip()
    )

    if not text:

        return "New Chat"

    if len(text) > 70:

        return (
            text[:70]
            + "…"
        )

    return text


# ============================================================
# CHAT SUBMIT
# ============================================================

def chat_submit(
    message,
    history,
    user_id,
    conversation_id
):

    message = str(
        message or ""
    ).strip()

    history = (
        history
        or []
    )

    user_id = ensure_user(
        user_id
    )

    if not message:

        return (
            "",
            history,
            user_id,
            conversation_id,
            memory_view(user_id)
        )

    if not conversation_id:

        conversation_id = (
            create_conversation(
                user_id,
                title_from_message(
                    message
                )
            )
        )

    # --------------------------------------------------------
    # SAVE USER MESSAGE
    # --------------------------------------------------------

    save_message(
        user_id,
        conversation_id,
        "user",
        message
    )

    # --------------------------------------------------------
    # EXTRACT MEMORY
    # --------------------------------------------------------

    extracted = (
        extract_long_term_memories(
            message
        )
    )

    for key, value in extracted:

        save_memory(
            user_id,
            key,
            value
        )

    # --------------------------------------------------------
    # GENERATE ANSWER
    # --------------------------------------------------------

    answer, source = (
        generate_answer(
            message,
            history,
            user_id,
            conversation_id
        )
    )

    # --------------------------------------------------------
    # SAVE ASSISTANT MESSAGE
    # --------------------------------------------------------

    save_message(
        user_id,
        conversation_id,
        "assistant",
        answer
    )

    # --------------------------------------------------------
    # UPDATE TITLE
    # --------------------------------------------------------

    if not history:

        update_conversation_title(
            conversation_id,
            user_id,
            title_from_message(
                message
            )
        )

    # --------------------------------------------------------
    # UPDATE CHAT UI
    # --------------------------------------------------------

    new_history = history + [

        {
            "role": "user",
            "content": message
        },

        {
            "role": "assistant",
            "content": answer
        }
    ]

    return (
        "",
        new_history,
        user_id,
        conversation_id,
        memory_view(user_id)
    )
    
# ============================================================
# DIRECT API FOR EXPO APP
# AUTHENTICATED CHAT + HISTORY + MEMORY
# ============================================================

api = FastAPI()

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# AUTH HELPER
# ============================================================

def authenticated_user(authorization: str = ""):

    token = get_bearer_token(authorization)

    user_id = verify_auth_token(token)

    if not user_id:
        return None

    return user_id


# ============================================================
# REGISTER
# ============================================================

@api.post("/api/register")
async def api_register(data: dict):

    try:

        username = str(
            data.get("username", "")
        ).strip()

        password = str(
            data.get("password", "")
        )

        if not username or not password:

            return {
                "ok": False,
                "error":
                    "Username और password दोनों जरूरी हैं।"
            }

        result, error = register_user(
            username,
            password
        )

        if error:

            return {
                "ok": False,
                "error": error
            }

        return {
            "ok": True,
            "user_id": result["user_id"],
            "username": result["username"],
            "token": result["token"]
        }

    except Exception as error:

        print(
            "REGISTER API ERROR:",
            type(error).__name__,
            str(error)
        )

        return {
            "ok": False,
            "error": "Registration failed."
        }


# ============================================================
# LOGIN
# ============================================================

@api.post("/api/login")
async def api_login(data: dict):

    try:

        username = str(
            data.get("username", "")
        ).strip()

        password = str(
            data.get("password", "")
        )

        if not username or not password:

            return {
                "ok": False,
                "error":
                    "Username और password दोनों जरूरी हैं।"
            }

        result, error = login_user(
            username,
            password
        )

        if error:

            return {
                "ok": False,
                "error": error
            }

        return {
            "ok": True,
            "user_id": result["user_id"],
            "username": result["username"],
            "token": result["token"]
        }

    except Exception as error:

        print(
            "LOGIN API ERROR:",
            type(error).__name__,
            str(error)
        )

        return {
            "ok": False,
            "error": "Login failed."
        }


# ============================================================
# LOGOUT
# ============================================================

@api.post("/api/logout")
async def api_logout(
    authorization: str = Header(default="")
):

    user_id = authenticated_user(
        authorization
    )

    if not user_id:

        return {
            "ok": False,
            "error": "Invalid or expired token."
        }

    return {
        "ok": True,
        "message": "Logged out successfully."
    }


# ============================================================
# CHAT
# ============================================================

@api.post("/api/chat")
async def api_chat(
    data: dict,
    authorization: str = Header(default="")
):

    try:

        # ---------------------------------------------
        # GET USER FROM TOKEN
        # ---------------------------------------------

        user_id = authenticated_user(
            authorization
        )

        if not user_id:

            return {
                "ok": False,
                "error":
                    "Login required. Please log in again."
            }

        # ---------------------------------------------
        # MESSAGE
        # ---------------------------------------------

        message = str(
            data.get("message", "")
        ).strip()

        conversation_id = data.get(
            "conversation_id"
        )

        if not message:

            return {
                "ok": False,
                "answer": "Message खाली है।"
            }

        # ---------------------------------------------
        # CHECK CONVERSATION OWNERSHIP
        # ---------------------------------------------

        if conversation_id:

            conn = get_db()

            try:

                with conn.cursor() as cur:

                    cur.execute("""
                        SELECT 1

                        FROM conversations

                        WHERE id = %s
                          AND user_id = %s

                        LIMIT 1
                    """, (
                        conversation_id,
                        user_id
                    ))

                    owns_conversation = cur.fetchone()

            finally:

                conn.close()

            if not owns_conversation:

                return {
                    "ok": False,
                    "error": "Conversation not found."
                }

        # ---------------------------------------------
        # CHAT ENGINE
        # ---------------------------------------------

        result = chat_submit(
            message,
            [],
            user_id,
            conversation_id
        )

        (
            _,
            new_history,
            new_user_id,
            new_conversation_id,
            memory
        ) = result

        # ---------------------------------------------
        # GET ANSWER
        # ---------------------------------------------

        answer = ""

        if new_history:

            last_item = new_history[-1]

            if isinstance(
                last_item,
                dict
            ):

                if last_item.get(
                    "role"
                ) == "assistant":

                    answer = str(
                        last_item.get(
                            "content",
                            ""
                        )
                    )

        return {
            "ok": True,
            "answer": answer,
            "history": new_history,
            "user_id": user_id,
            "conversation_id":
                new_conversation_id,
            "memory": memory
        }

    except Exception as error:

        print(
            "DIRECT API ERROR:",
            type(error).__name__,
            str(error)
        )

        return {
            "ok": False,
            "answer": "",
            "error":
                "Chat request failed."
        }


# ============================================================
# GET CHAT HISTORY
# ============================================================

@api.get("/api/history")
async def api_history(
    authorization: str = Header(default="")
):

    try:

        user_id = authenticated_user(
            authorization
        )

        if not user_id:

            return {
                "ok": False,
                "error": "Login required."
            }

        conversations = get_user_conversations(
            user_id,
            100
        )

        result = []

        for conversation in conversations:

            result.append({
                "id": conversation["id"],
                "title":
                    conversation["title"],
                "created_at":
                    str(
                        conversation["created_at"]
                    ),
                "updated_at":
                    str(
                        conversation["updated_at"]
                    )
            })

        return {
            "ok": True,
            "history": result
        }

    except Exception as error:

        print(
            "HISTORY API ERROR:",
            type(error).__name__,
            str(error)
        )

        return {
            "ok": False,
            "error": "History load failed."
        }


# ============================================================
# GET ONE CONVERSATION
# ============================================================

@api.get(
    "/api/history/{conversation_id}"
)
async def api_get_conversation(
    conversation_id: str,
    authorization: str = Header(default="")
):

    try:

        user_id = authenticated_user(
            authorization
        )

        if not user_id:

            return {
                "ok": False,
                "error": "Login required."
            }

        # ---------------------------------------------
        # OWNERSHIP CHECK
        # ---------------------------------------------

        conn = get_db()

        try:

            with conn.cursor(
                cursor_factory=RealDictCursor
            ) as cur:

                cur.execute("""
                    SELECT
                        id,
                        title,
                        created_at,
                        updated_at

                    FROM conversations

                    WHERE id = %s
                      AND user_id = %s

                    LIMIT 1
                """, (
                    conversation_id,
                    user_id
                ))

                conversation = cur.fetchone()

        finally:

            conn.close()

        if not conversation:

            return {
                "ok": False,
                "error": "Conversation not found."
            }

        messages = get_conversation_messages(
            user_id,
            conversation_id,
            200
        )

        return {
            "ok": True,
            "conversation": {
                "id":
                    conversation["id"],
                "title":
                    conversation["title"],
                "created_at":
                    str(
                        conversation["created_at"]
                    ),
                "updated_at":
                    str(
                        conversation["updated_at"]
                    )
            },
            "messages": messages
        }

    except Exception as error:

        print(
            "CONVERSATION API ERROR:",
            type(error).__name__,
            str(error)
        )

        return {
            "ok": False,
            "error":
                "Conversation load failed."
        }


# ============================================================
# DELETE ONE CHAT
# ============================================================

@api.delete(
    "/api/history/{conversation_id}"
)
async def api_delete_conversation(
    conversation_id: str,
    authorization: str = Header(default="")
):

    conn = None

    try:

        user_id = authenticated_user(
            authorization
        )

        if not user_id:

            return {
                "ok": False,
                "error": "Login required."
            }

        conn = get_db()

        with conn.cursor() as cur:

            # -----------------------------------------
            # CHECK OWNERSHIP
            # -----------------------------------------

            cur.execute("""
                SELECT 1

                FROM conversations

                WHERE id = %s
                  AND user_id = %s

                LIMIT 1
            """, (
                conversation_id,
                user_id
            ))

            exists = cur.fetchone()

            if not exists:

                return {
                    "ok": False,
                    "error":
                        "Conversation not found."
                }

            # -----------------------------------------
            # DELETE MESSAGES
            # -----------------------------------------

            cur.execute("""
                DELETE FROM messages

                WHERE conversation_id = %s
                  AND user_id = %s
            """, (
                conversation_id,
                user_id
            ))

            # -----------------------------------------
            # DELETE CONVERSATION
            # -----------------------------------------

            cur.execute("""
                DELETE FROM conversations

                WHERE id = %s
                  AND user_id = %s
            """, (
                conversation_id,
                user_id
            ))

        conn.commit()

        return {
            "ok": True,
            "message": "Chat deleted successfully."
        }

    except Exception as error:

        if conn:
            conn.rollback()

        print(
            "DELETE HISTORY ERROR:",
            type(error).__name__,
            str(error)
        )

        return {
            "ok": False,
            "error": "Chat delete failed."
        }

    finally:

        if conn:
            conn.close()


# ============================================================
# GET MEMORY
# ============================================================

@api.get("/api/memory")
async def api_memory(
    authorization: str = Header(default="")
):

    conn = None

    try:

        user_id = authenticated_user(
            authorization
        )

        if not user_id:

            return {
                "ok": False,
                "error": "Login required."
            }

        conn = get_db()

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cur:

            cur.execute("""
                SELECT
                    id,
                    memory_key,
                    memory_value,
                    created_at,
                    updated_at

                FROM memories

                WHERE user_id = %s

                ORDER BY updated_at DESC
            """, (
                user_id,
            ))

            memories = cur.fetchall()

        result = []

        for memory in memories:

            result.append({
                "id":
                    memory["id"],
                "key":
                    memory["memory_key"],
                "value":
                    memory["memory_value"],
                "created_at":
                    str(
                        memory["created_at"]
                    ),
                "updated_at":
                    str(
                        memory["updated_at"]
                    )
            })

        return {
            "ok": True,
            "memories": result
        }

    except Exception as error:

        print(
            "MEMORY API ERROR:",
            type(error).__name__,
            str(error)
        )

        return {
            "ok": False,
            "error": "Memory load failed."
        }

    finally:

        if conn:
            conn.close()


# ============================================================
# DELETE ONE MEMORY
# ============================================================

@api.delete(
    "/api/memory/{memory_id}"
)
async def api_delete_memory(
    memory_id: int,
    authorization: str = Header(default="")
):

    conn = None

    try:

        user_id = authenticated_user(
            authorization
        )

        if not user_id:

            return {
                "ok": False,
                "error": "Login required."
            }

        conn = get_db()

        with conn.cursor() as cur:

            cur.execute("""
                DELETE FROM memories

                WHERE id = %s
                  AND user_id = %s
            """, (
                memory_id,
                user_id
            ))

            deleted = cur.rowcount

        conn.commit()

        if deleted == 0:

            return {
                "ok": False,
                "error": "Memory not found."
            }

        return {
            "ok": True,
            "message":
                "Memory deleted successfully."
        }

    except Exception as error:

        if conn:
            conn.rollback()

        print(
            "DELETE MEMORY ERROR:",
            type(error).__name__,
            str(error)
        )

        return {
            "ok": False,
            "error":
                "Memory delete failed."
        }

    finally:

        if conn:
            conn.close()


# ============================================================
# CLEAR ALL MEMORY
# ============================================================

@api.delete("/api/memory")
async def api_clear_memory(
    authorization: str = Header(default="")
):

    conn = None

    try:

        user_id = authenticated_user(
            authorization
        )

        if not user_id:

            return {
                "ok": False,
                "error": "Login required."
            }

        conn = get_db()

        with conn.cursor() as cur:

            cur.execute("""
                DELETE FROM memories

                WHERE user_id = %s
            """, (
                user_id,
            ))

            deleted_count = cur.rowcount

        conn.commit()

        return {
            "ok": True,
            "deleted": deleted_count,
            "message":
                "All memories cleared."
        }

    except Exception as error:

        if conn:
            conn.rollback()

        print(
            "CLEAR MEMORY ERROR:",
            type(error).__name__,
            str(error)
        )

        return {
            "ok": False,
            "error":
                "Memory clear failed."
        }

    finally:

        if conn:
            conn.close()
# ============================================================
# AUTHENTICATION HELPER
# ============================================================

def authenticated_user(authorization: str = ""):
    token = get_bearer_token(authorization)

    user_id = verify_auth_token(token)

    if not user_id:
        return None

    return user_id


# ============================================================
# REGISTER
# ============================================================

@api.post("/api/register")
async def api_register(data: dict):

    try:
        username = str(
            data.get("username", "")
        ).strip()

        password = str(
            data.get("password", "")
        )

        if not username or not password:
            return {
                "ok": False,
                "error": "Username और password दोनों जरूरी हैं।"
            }

        result, error = register_user(
            username,
            password
        )

        if error:
            return {
                "ok": False,
                "error": error
            }

        return {
            "ok": True,
            "user_id": result["user_id"],
            "username": result["username"],
            "token": result["token"]
        }

    except Exception as error:
        print("REGISTER API ERROR:", str(error))

        return {
            "ok": False,
            "error": "Registration failed."
        }


# ============================================================
# LOGIN
# ============================================================

@api.post("/api/login")
async def api_login(data: dict):

    try:
        username = str(
            data.get("username", "")
        ).strip()

        password = str(
            data.get("password", "")
        )

        if not username or not password:
            return {
                "ok": False,
                "error": "Username और password दोनों जरूरी हैं।"
            }

        result, error = login_user(
            username,
            password
        )

        if error:
            return {
                "ok": False,
                "error": error
            }

        return {
            "ok": True,
            "user_id": result["user_id"],
            "username": result["username"],
            "token": result["token"]
        }

    except Exception as error:
        print("LOGIN API ERROR:", str(error))

        return {
            "ok": False,
            "error": "Login failed."
        }


# ============================================================
# LOGOUT
# ============================================================

@api.post("/api/logout")
async def api_logout(
    authorization: str = Header(default="")
):

    user_id = authenticated_user(authorization)

    if not user_id:
        return {
            "ok": False,
            "error": "Invalid or expired token."
        }

    # Stateless token: Expo must delete its saved token.
    return {
        "ok": True,
        "message": "Logged out successfully."
    }


# ============================================================
# CHAT — AUTHENTICATION REQUIRED
# ============================================================

@api.post("/api/chat")
async def api_chat(
    data: dict,
    authorization: str = Header(default="")
):

    try:
        # Never trust user_id sent in the request body.
        user_id = authenticated_user(authorization)

        if not user_id:
            return {
                "ok": False,
                "error": "Login required. Please log in again."
            }

        message = str(
            data.get("message", "")
        ).strip()

        conversation_id = data.get(
            "conversation_id"
        )

        if not message:
            return {
                "ok": False,
                "answer": "Message खाली है।"
            }

        # Verify that the conversation belongs to this user.
        if conversation_id:
            conn = get_db()

            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 1
                        FROM conversations
                        WHERE id = %s
                          AND user_id = %s
                        LIMIT 1
                        """,
                        (conversation_id, user_id)
                    )

                    owns_conversation = cur.fetchone()

            finally:
                conn.close()

            if not owns_conversation:
                return {
                    "ok": False,
                    "error": "Conversation not found."
                }

        # Do not accept client-supplied history as trusted data.
        # The backend should load the user's own messages.
        result = chat_submit(
            message,
            [],
            user_id,
            conversation_id
        )

        (
            _,
            new_history,
            new_user_id,
            new_conversation_id,
            memory
        ) = result

        answer = ""

        if new_history:
            last_item = new_history[-1]

            if isinstance(last_item, dict):
                if last_item.get("role") == "assistant":
                    answer = str(
                        last_item.get("content", "")
                    )

        return {
            "ok": True,
            "answer": answer,
            "history": new_history,
            "user_id": user_id,
            "conversation_id": new_conversation_id,
            "memory": memory
        }

    except Exception as error:
        print(
            "DIRECT API ERROR:",
            type(error).__name__,
            str(error)
        )

        return {
            "ok": False,
            "answer": "",
            "error": "Chat request failed."
        }
# ============================================================
# NEW CHAT
# ============================================================

def new_chat(
    user_id
):

    user_id = ensure_user(
        user_id
    )

    conversation_id = (
        create_conversation(
            user_id,
            "New Chat"
        )
    )

    return (
        [],
        user_id,
        conversation_id
    )


# ============================================================
# LOAD HISTORY
# ============================================================

def load_history(
    user_id
):

    user_id = ensure_user(
        user_id
    )

    rows = (
        get_user_conversations(
            user_id
        )
    )

    choices = [

        (
            row["title"],
            row["id"]
        )

        for row in rows
    ]

    return gr.update(
        choices=choices,
        value=(
            choices[0][1]
            if choices
            else None
        )
    )


# ============================================================
# LOAD SELECTED CONVERSATION
# ============================================================

def load_conversation(
    conversation_id,
    user_id
):

    if not conversation_id:

        return []

    user_id = ensure_user(
        user_id
    )

    return get_conversation_messages(
        user_id,
        conversation_id
    )


# ============================================================
# MEMORY VIEW
# ============================================================

def memory_view(
    user_id
):

    user_id = ensure_user(
        user_id
    )

    rows = get_memories(
        user_id,
        100
    )

    if not rows:

        return (
            "### Long-term Memory\n\n"
            "No memories saved yet."
        )

    lines = [
        "### Long-term Memory",
        ""
    ]

    for row in rows:

        lines.append(
            f"- {row['memory_value']}"
        )

    return "\n".join(
        lines
    )


# ============================================================
# CLEAR MEMORY
# ============================================================

def clear_memory(
    user_id
):

    user_id = ensure_user(
        user_id
    )

    delete_memories(
        user_id
    )

    return (
        "### Long-term Memory\n\n"
        "Memory cleared successfully."
    )


# ============================================================
# MANUAL MEMORY
# ============================================================

def manual_memory(
    text,
    user_id
):

    user_id = ensure_user(
        user_id
    )

    text = str(
        text or ""
    ).strip()

    if text:

        save_memory(
            user_id,
            deterministic_key(
                "manual",
                text
            ),
            text
        )

    return memory_view(
        user_id
    )


# ============================================================
# CSS
# ============================================================

CSS = r"""
body {
    margin: 0;
}

.gyan-title {
    text-align: center;
    font-size: 30px;
    font-weight: 800;
    margin: 4px 0 0 0;
}

.gyan-subtitle {
    text-align: center;
    opacity: 0.72;
    margin-bottom: 10px;
}

footer {
    display: none !important;
}

#chatbot {
    min-height: 65vh;
}

textarea {
    border-radius: 14px !important;
}
"""


# ============================================================
# BUILD APPLICATION
# ============================================================

def build_app():

    init_database()

    with gr.Blocks(
        title=APP_TITLE,
        css=CSS,
        theme=gr.themes.Soft()
    ) as demo:

        # ----------------------------------------------------
        # STATES
        # ----------------------------------------------------

        user_id = gr.State(
            str(
                uuid.uuid4()
            )
        )

        conversation_id = gr.State(
            None
        )

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------

        gr.HTML(
            """
            <div class="gyan-title">
                🧠 Gyan AI
            </div>

            <div class="gyan-subtitle">
                Your AI assistant with long-term memory
            </div>
            """
        )

        # ----------------------------------------------------
        # MAIN LAYOUT
        # ----------------------------------------------------

        with gr.Row():

                    # =================================================
            # CHAT
            # =================================================

            with gr.Column(
                scale=5
            ):

                chatbot = gr.Chatbot(
    value=[],
    elem_id="chatbot",
    height="65vh",
    show_label=False,
    placeholder="Start a conversation with Gyan AI…"
)

                message = gr.Textbox(

                    placeholder=(
                        "Type your message…"
                    ),

                    show_label=False,

                    lines=2,

                    max_lines=8,

                    autofocus=True
                )

                with gr.Row():

                    send = gr.Button(
                        "Send",
                        variant="primary"
                    )

                    new = gr.Button(
                        "New Chat"
                    )

            # =================================================
            # SIDEBAR
            # =================================================

            with gr.Column(
                scale=2,
                min_width=220
            ):

                gr.Markdown(
                    "### Chat History"
                )

                history_dropdown = (
                    gr.Dropdown(
                        choices=[],
                        label="Conversations",
                        interactive=True
                    )
                )

                refresh_history = (
                    gr.Button(
                        "Refresh History"
                    )
                )

                gr.Markdown(
                    "### Memory"
                )

                memory_box = gr.Markdown(
                    "### Long-term Memory\n\n"
                    "No memories loaded."
                )

                refresh_memory = (
                    gr.Button(
                        "Refresh Memory"
                    )
                )

                clear_memory_btn = (
                    gr.Button(
                        "Clear Memory"
                    )
                )

                gr.Markdown(
                    "### Save a Memory"
                )

                manual_memory_text = (
                    gr.Textbox(
                        label="Memory",
                        placeholder=(
                            "Example: "
                            "मुझे science पसंद है"
                        ),
                        lines=2
                    )
                )

                save_memory_btn = (
                    gr.Button(
                        "Save Memory"
                    )
                )

        # ====================================================
        # SUBMIT CONFIG
        # ====================================================

        submit_inputs = [

            message,
            chatbot,
            user_id,
            conversation_id
        ]

        submit_outputs = [

            message,
            chatbot,
            user_id,
            conversation_id,
            memory_box
        ]

        # ====================================================
        # SEND
        # ====================================================

        send.click(

            chat_submit,

            inputs=submit_inputs,

            outputs=submit_outputs
        )

        # ====================================================
        # ENTER
        # ====================================================

        message.submit(

            chat_submit,

            inputs=submit_inputs,

            outputs=submit_outputs
        )

        # ====================================================
        # NEW CHAT
        # ====================================================

        new.click(

            new_chat,

            inputs=[
                user_id
            ],

            outputs=[
                chatbot,
                user_id,
                conversation_id
            ]

        ).then(

            load_history,

            inputs=[
                user_id
            ],

            outputs=[
                history_dropdown
            ]

        ).then(

            memory_view,

            inputs=[
                user_id
            ],

            outputs=[
                memory_box
            ]
        )

        # ====================================================
        # REFRESH HISTORY
        # ====================================================

        refresh_history.click(

            load_history,

            inputs=[
                user_id
            ],

            outputs=[
                history_dropdown
            ]
        )

        # ====================================================
        # SELECT HISTORY
        # ====================================================

        history_dropdown.change(

            load_conversation,

            inputs=[
                history_dropdown,
                user_id
            ],

            outputs=[
                chatbot
            ]

        ).then(

            lambda cid: cid,

            inputs=[
                history_dropdown
            ],

            outputs=[
                conversation_id
            ]
        )

        # ====================================================
        # REFRESH MEMORY
        # ====================================================

        refresh_memory.click(

            memory_view,

            inputs=[
                user_id
            ],

            outputs=[
                memory_box
            ]
        )

        # ====================================================
        # CLEAR MEMORY
        # ====================================================

        clear_memory_btn.click(

            clear_memory,

            inputs=[
                user_id
            ],

            outputs=[
                memory_box
            ]
        )

        # ====================================================
        # SAVE MANUAL MEMORY
        # ====================================================

        save_memory_btn.click(

            manual_memory,

            inputs=[
                manual_memory_text,
                user_id
            ],

            outputs=[
                memory_box
            ]

        ).then(

            lambda: "",

            outputs=[
                manual_memory_text
            ]
        )

        # ====================================================
        # PAGE LOAD
        # ====================================================

        demo.load(

            load_history,

            inputs=[
                user_id
            ],

            outputs=[
                history_dropdown
            ]

        ).then(

            memory_view,

            inputs=[
                user_id
            ],

            outputs=[
                memory_box
            ]
        )

    return demo


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    app = build_app()

    api = gr.mount_gradio_app(
        api,
        app,
        path="/"
    )

    port = int(
        os.environ.get(
            "PORT",
            "7860"
        )
    )

    uvicorn.run(
        api,
        host="0.0.0.0",
        port=port
    )
      
