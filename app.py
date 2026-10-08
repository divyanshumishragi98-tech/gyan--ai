# ============================================================
#                         GYAN AI
#                         V14.0
#
# PostgreSQL
# Long-Term Memory
# Chat History
# Gemini
# OpenRouter Fallback
# Gyan AI Own Search Engine
# Web Crawler
# Crawl Queue
# Robots.txt
# SSRF Protection
# FastAPI
# Gradio
#
# API BASE:
# https://gyan-ai-ef7h.onrender.com
# ============================================================

import os
import re
import time
import hmac
import base64
import secrets
import uuid
import hashlib
import json
import socket
import ipaddress
import threading
import urllib.request
import urllib.error
import urllib.parse

from typing import Optional
from urllib.parse import urlparse, unquote

import gradio as gr
import psycopg2
import uvicorn

from psycopg2.extras import RealDictCursor

from google import genai

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Body,
    Depends
)

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from fastapi.middleware.cors import CORSMiddleware


# ============================================================
#                         BASIC CONFIG
# ============================================================

APP_TITLE = "Gyan AI"

APP_VERSION = "14.0"

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


# ============================================================
#                         ENVIRONMENT
# ============================================================

DATABASE_URL = os.environ.get(
    "DATABASE_URL"
)

GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY"
)

OPENROUTER_API_KEY = os.environ.get(
    "OPENROUTER_API_KEY"
)

GYAN_AUTH_SECRET = os.environ.get(
    "GYAN_AUTH_SECRET"
)

if not GYAN_AUTH_SECRET:
    print(
        "WARNING: GYAN_AUTH_SECRET is not configured."
    )

    GYAN_AUTH_SECRET = secrets.token_hex(32)


GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)

OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL",
    "nex-agi/nex-n2.5-mini:free"
)


# ============================================================
#                    OPENROUTER FALLBACKS
# ============================================================

OPENROUTER_MODELS = [
    OPENROUTER_MODEL,
    "nex-agi/nex-n2.5-mini:free",
    "nex-agi/nex-n2.5-pro:free",
    "inclusionai/ling-3.0-flash-sante:free",
    "dots-studio/dots-3-note-preview:free",
    "liquid/lfm-2.5-2.6b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openrouter/free",
]


# Remove duplicates
OPENROUTER_MODELS = list(
    dict.fromkeys(
        OPENROUTER_MODELS
    )
)


# ============================================================
#                         GEMINI
# ============================================================

gemini_client = (
    genai.Client(
        api_key=GEMINI_API_KEY
    )
    if GEMINI_API_KEY
    else None
)


# ============================================================
#                         DATABASE
# ============================================================

def get_db():

    if not DATABASE_URL:

        raise RuntimeError(
            "DATABASE_URL is not configured."
        )

    url = (
        DATABASE_URL
        .strip()
        .strip('"')
        .strip("'")
    )

    parsed = urlparse(url)

    if not parsed.hostname:

        raise RuntimeError(
            "Invalid DATABASE_URL."
        )

    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/"),
        user=unquote(
            parsed.username or ""
        ),
        password=unquote(
            parsed.password or ""
        ),
        connect_timeout=10
    )


# ============================================================
#                    DATABASE INITIALIZATION
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
        # SEARCH PAGES
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

                crawled_at
                    TIMESTAMPTZ DEFAULT NOW(),

                updated_at
                    TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_gyan_search_domain
            ON gyan_search_pages(domain)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_gyan_search_crawled_at
            ON gyan_search_pages(
                crawled_at DESC
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_gyan_search_content
            ON gyan_search_pages
            USING GIN (
                to_tsvector(
                    'simple',
                    content
                )
            )
        """)

        # ----------------------------------------------------
        # CRAWL QUEUE
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS gyan_crawl_queue (

                id BIGSERIAL PRIMARY KEY,

                url TEXT UNIQUE NOT NULL,

                status TEXT DEFAULT 'pending',

                depth INTEGER DEFAULT 0,

                priority INTEGER DEFAULT 0,

                created_at
                    TIMESTAMPTZ DEFAULT NOW(),

                processed_at
                    TIMESTAMPTZ
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_gyan_crawl_queue_status
            ON gyan_crawl_queue(
                status,
                priority DESC,
                id
            )
        """)

        # ----------------------------------------------------
        # USERS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS gyan_users (

                id TEXT PRIMARY KEY,

                username TEXT UNIQUE,

                password_hash TEXT,

                password_salt TEXT,

                created_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                updated_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Existing databases
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

                UNIQUE(
                    user_id,
                    memory_key
                )
            )
        """)

        # ----------------------------------------------------
        # INDEXES
        # ----------------------------------------------------

        cur.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_conversations_user_updated
            ON conversations(
                user_id,
                updated_at DESC
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_messages_conversation_id
            ON messages(
                conversation_id,
                id
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_messages_user_id
            ON messages(
                user_id,
                id
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_memories_user_updated
            ON memories(
                user_id,
                updated_at DESC
            )
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
#                         TEXT HELPERS
# ============================================================

def clean_web_text(
    text: str
) -> str:

    text = re.sub(
        r"\s+",
        " ",
        text or ""
    )

    return text.strip()


def clean_username(
    username: str
) -> str:

    username = (
        username or ""
    ).strip()

    username = re.sub(
        r"[^a-zA-Z0-9_.-]",
        "",
        username
    )

    return username[:100]


def hash_password(
    password: str,
    salt: Optional[str] = None
):

    if salt is None:

        salt = secrets.token_hex(
            16
        )

    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(
            "utf-8"
        ),
        salt.encode(
            "utf-8"
        ),
        120000
    )

    return (
        base64.b64encode(
            hashed
        ).decode(
            "utf-8"
        ),
        salt
    )


def verify_password(
    password: str,
    stored_hash: str,
    salt: str
):

    calculated_hash, _ = hash_password(
        password,
        salt
    )

    return hmac.compare_digest(
        calculated_hash,
        stored_hash
    )



# ============================================================
#                         AUTH TOKENS
# ============================================================

def create_token(
    user_id: str
) -> str:

    timestamp = str(
        int(time.time())
    )

    payload = (
        f"{user_id}.{timestamp}"
    )

    signature = hmac.new(
        GYAN_AUTH_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

    return (
        base64.urlsafe_b64encode(
            payload.encode()
        )
        .decode()
        .rstrip("=")
        + "."
        + signature
    )


def verify_token(
    token: Optional[str]
):

    if not token:
        return None

    try:

        encoded, signature = (
            token.split(
                ".",
                1
            )
        )

        padding = "=" * (
            (-len(encoded)) % 4
        )

        payload = base64.urlsafe_b64decode(
            encoded + padding
        ).decode()

        user_id, timestamp = (
            payload.split(
                ".",
                1
            )
        )

        expected = hmac.new(
            GYAN_AUTH_SECRET.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(
            signature,
            expected
        ):
            return None

        if (
            int(time.time())
            - int(timestamp)
            > 60 * 60 * 24 * 30
        ):
            return None

        return user_id

    except Exception:

        return None

bearer_scheme = HTTPBearer(
    auto_error=False
)
def get_user_id_from_header(
    authorization: Optional[str]
):

    if not authorization:

        return None

    if authorization.lower().startswith(
        "bearer "
    ):

        token = authorization[7:].strip()

    else:

        token = authorization.strip()

    return verify_token(
        token
    )


# ============================================================
#                         USER FUNCTIONS
# ============================================================

def create_user(
    username: str,
    password: str
):

    username = clean_username(
        username
    )

    if len(username) < 3:

        return None, "Username is too short."

    if len(password or "") < 4:

        return None, "Password is too short."

    password_hash, salt = (
        hash_password(password)
    )

    user_id = str(
        uuid.uuid4()
    )

    conn = get_db()

    try:

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cur:

            cur.execute("""
                INSERT INTO gyan_users
                (
                    id,
                    username,
                    password_hash,
                    password_salt
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s
                )
                RETURNING id, username
            """, (
                user_id,
                username,
                password_hash,
                salt
            ))

            user = cur.fetchone()

        conn.commit()

        return dict(user), None

    except psycopg2.errors.UniqueViolation:

        conn.rollback()

        return None, "Username already exists."

    except Exception as error:

        conn.rollback()

        print(
            "CREATE USER ERROR:",
            type(error).__name__,
            str(error)
        )

        return None, "Could not create user."

    finally:

        conn.close()


def authenticate_user(
    username: str,
    password: str
):

    username = clean_username(
        username
    )

    conn = get_db()

    try:

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cur:

            cur.execute("""
                SELECT
                    id,
                    username,
                    password_hash,
                    password_salt
                FROM gyan_users
                WHERE username = %s
                LIMIT 1
            """, (
                username,
            ))

            user = cur.fetchone()

        if not user:

            return None

        if not verify_password(
            password,
            user["password_hash"],
            user["password_salt"]
        ):

            return None

        return dict(user)

    finally:

        conn.close()


# ============================================================
#                       MEMORY FUNCTIONS
# ============================================================

def get_memories(
    user_id: str,
    limit: int = 30
):

    limit = max(
        1,
        min(
            int(limit),
            100
        )
    )

    conn = get_db()

    try:

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
                LIMIT %s
            """, (
                user_id,
                limit
            ))

            return [
                dict(row)
                for row in cur.fetchall()
            ]

    finally:

        conn.close()


def save_memory(
    user_id: str,
    memory_key: str,
    memory_value: str
):

    memory_key = clean_web_text(
        memory_key
    )

    memory_value = clean_web_text(
        memory_value
    )

    if not memory_key or not memory_value:
        return False

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                INSERT INTO memories
                (
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
                    updated_at = NOW()
            """, (
                user_id,
                memory_key,
                memory_value
            ))

        conn.commit()

        return True

    finally:

        conn.close()


def delete_memory(
    user_id: str,
    memory_id: int
):

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                DELETE FROM memories
                WHERE
                    id = %s
                    AND user_id = %s
            """, (
                memory_id,
                user_id
            ))

            deleted = (
                cur.rowcount > 0
            )

        conn.commit()

        return deleted

    finally:

        conn.close()


def clear_memories(
    user_id: str
):

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                DELETE FROM memories
                WHERE user_id = %s
            """, (
                user_id,
            ))

            count = cur.rowcount

        conn.commit()

        return count

    finally:

        conn.close()


# ============================================================
#                       CHAT FUNCTIONS
# ============================================================

def create_conversation(
    user_id: str,
    title: str = "New Chat"
):

    conversation_id = str(
        uuid.uuid4()
    )

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                INSERT INTO conversations
                (
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
                title[:200]
            ))

        conn.commit()

        return conversation_id

    finally:

        conn.close()


def conversation_exists(
    user_id: str,
    conversation_id: str
):

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT 1
                FROM conversations
                WHERE
                    id = %s
                    AND user_id = %s
                LIMIT 1
            """, (
                conversation_id,
                user_id
            ))

            return cur.fetchone() is not None

    finally:

        conn.close()


def save_message(
    user_id: str,
    conversation_id: str,
    role: str,
    content: str
):

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                INSERT INTO messages
                (
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
                    updated_at = NOW()
                WHERE
                    id = %s
                    AND user_id = %s
            """, (
                conversation_id,
                user_id
            ))

        conn.commit()

    finally:

        conn.close()


def get_recent_messages(
    user_id: str,
    conversation_id: str,
    limit: int = 20
):

    conn = get_db()

    try:

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cur:

            cur.execute("""
                SELECT
                    role,
                    content,
                    created_at
                FROM messages
                WHERE
                    user_id = %s
                    AND conversation_id = %s
                ORDER BY id DESC
                LIMIT %s
            """, (
                user_id,
                conversation_id,
                limit
            ))

            rows = cur.fetchall()

            rows.reverse()

            return [
                dict(row)
                for row in rows
            ]

    finally:

        conn.close()


def get_conversations(
    user_id: str
):

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
                WHERE user_id = %s
                ORDER BY updated_at DESC
            """, (
                user_id,
            ))

            return [
                dict(row)
                for row in cur.fetchall()
            ]

    finally:

        conn.close()


def get_conversation_messages(
    user_id: str,
    conversation_id: str
):

    conn = get_db()

    try:

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cur:

            cur.execute("""
                SELECT
                    id,
                    role,
                    content,
                    created_at
                FROM messages
                WHERE
                    user_id = %s
                    AND conversation_id = %s
                ORDER BY id ASC
            """, (
                user_id,
                conversation_id
            ))

            return [
                dict(row)
                for row in cur.fetchall()
            ]

    finally:

        conn.close()


def delete_conversation(
    user_id: str,
    conversation_id: str
):

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                DELETE FROM messages
                WHERE
                    user_id = %s
                    AND conversation_id = %s
            """, (
                user_id,
                conversation_id
            ))

            cur.execute("""
                DELETE FROM conversations
                WHERE
                    user_id = %s
                    AND id = %s
            """, (
                user_id,
                conversation_id
            ))

            deleted = (
                cur.rowcount > 0
            )

        conn.commit()

        return deleted

    finally:

        conn.close()


# ============================================================
#                    GYAN SEARCH ENGINE
# ============================================================

def normalize_url(
    url: str
):

    url = (
        url or ""
    ).strip()

    if not url:
        return None

    parsed = urlparse(
        url
    )

    if parsed.scheme not in (
        "http",
        "https"
    ):
        return None

    if not parsed.hostname:
        return None

    if parsed.username or parsed.password:
        return None

    clean_path = (
        parsed.path
        or "/"
    )

    return urllib.parse.urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            clean_path,
            "",
            parsed.query,
            ""
        )
    )


# ============================================================
#                SSRF / PUBLIC URL PROTECTION
# ============================================================

def is_private_ip(
    ip_string: str
):

    try:

        ip = ipaddress.ip_address(
            ip_string
        )

        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )

    except ValueError:

        return True


def is_safe_public_url(
    url: str
):

    normalized = normalize_url(
        url
    )

    if not normalized:
        return False

    parsed = urlparse(
        normalized
    )

    hostname = (
        parsed.hostname
        or ""
    ).lower()

    blocked_names = {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
        "host.docker.internal"
    }

    if hostname in blocked_names:
        return False

    try:

        addresses = socket.getaddrinfo(
            hostname,
            parsed.port or (
                443
                if parsed.scheme == "https"
                else 80
            ),
            type=socket.SOCK_STREAM
        )

        if not addresses:
            return False

        for address in addresses:

            ip = address[
                4
            ][0]

            if is_private_ip(
                ip
            ):
                return False

        return True

    except Exception:

        return False


# ============================================================
#                     ROBOTS.TXT
# ============================================================

robots_cache = {}

robots_lock = threading.Lock()


def robots_allowed(
    url: str
):

    parsed = urlparse(
        url
    )

    base = (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
    )

    robots_url = (
        base +
        "/robots.txt"
    )

    now = time.time()

    with robots_lock:

        cached = robots_cache.get(
            base
        )

        if cached and (
            now - cached["time"] < 3600
        ):

            rules = cached[
                "rules"
            ]

        else:

            rules = []

            try:

                if is_safe_public_url(
                    robots_url
                ):

                    request = (
                        urllib.request.Request(
                            robots_url,
                            headers={
                                "User-Agent":
                                    "GyanAI-SearchBot/1.0"
                            }
                        )
                    )

                    with urllib.request.urlopen(
                        request,
                        timeout=10
                    ) as response:

                        raw = response.read(
                            200000
                        )

                        robots_text = (
                            raw.decode(
                                "utf-8",
                                errors="ignore"
                            )
                        )

                    current_agent = False

                    for line in robots_text.splitlines():

                        line = line.strip()

                        if not line:
                            continue

                        if line.startswith("#"):
                            continue

                        if ":" not in line:
                            continue

                        key, value = (
                            line.split(
                                ":",
                                1
                            )
                        )

                        key = key.strip().lower()
                        value = value.strip()

                        if key == "user-agent":

                            current_agent = (
                                value == "*"
                                or
                                value.lower()
                                == "gyanai-searchbot"
                            )

                        elif (
                            key == "disallow"
                            and current_agent
                        ):

                            rules.append(
                                value
                            )

            except Exception:

                # If robots.txt cannot be read,
                # do not crash the crawler.
                rules = []

            robots_cache[
                base
            ] = {
                "time": now,
                "rules": rules
            }

    path = (
        parsed.path
        or "/"
    )

    for rule in rules:

        if rule == "/":
            return False

        if rule and path.startswith(
            rule
        ):
            return False

    return True


# ============================================================
#                     DOMAIN RATE LIMIT
# ============================================================

domain_last_request = {}

domain_lock = threading.Lock()


def wait_for_domain(
    url: str,
    delay: float = 1.0
):

    parsed = urlparse(
        url
    )

    domain = (
        parsed.netloc.lower()
    )

    with domain_lock:

        last = domain_last_request.get(
            domain,
            0
        )

        now = time.time()

        wait = (
            delay
            - (now - last)
        )

        if wait > 0:

            time.sleep(
                min(
                    wait,
                    5
                )
            )

        domain_last_request[
            domain
        ] = time.time()


# ============================================================
#                    LINK EXTRACTION
# ============================================================

def extract_page_links(
    base_url: str,
    html: str
):

    links = []

    try:

        for match in re.finditer(
            r'<a\b[^>]*href=["\']([^"\']+)["\']',
            html,
            flags=re.IGNORECASE
        ):

            href = (
                match.group(1)
                .strip()
            )

            if not href:
                continue

            if href.startswith(
                (
                    "#",
                    "mailto:",
                    "javascript:",
                    "tel:",
                    "data:"
                )
            ):
                continue

            absolute_url = (
                urllib.parse.urljoin(
                    base_url,
                    href
                )
            )

            clean_url = normalize_url(
                absolute_url
            )

            if not clean_url:
                continue

            if not is_safe_public_url(
                clean_url
            ):
                continue

            if clean_url not in links:

                links.append(
                    clean_url
                )

            if len(links) >= 50:
                break

    except Exception as error:

        print(
            "LINK EXTRACTION ERROR:",
            type(error).__name__,
            str(error)
        )

    return links


# ============================================================
#                    SAVE SEARCH PAGE
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

    url = normalize_url(
        url
    )

    if not url:
        return

    parsed = urlparse(
        url
    )

    domain = (
        parsed.netloc.lower()
    )

    content = clean_web_text(
        content
    )

    title = clean_web_text(
        title
    )

    description = clean_web_text(
        description
    )

    # Keep database growth bounded.
    content = content[
        :500000
    ]

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
                    language,
                    crawled_at,
                    updated_at
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (url)
                DO UPDATE SET
                    title =
                        EXCLUDED.title,
                    content =
                        EXCLUDED.content,
                    domain =
                        EXCLUDED.domain,
                    description =
                        EXCLUDED.description,
                    language =
                        EXCLUDED.language,
                    crawled_at =
                        NOW(),
                    updated_at =
                        NOW()
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
#                       WEB CRAWLER
# ============================================================

def crawl_web_page(
    url: str
):

    url = normalize_url(
        url
    )

    if not url:

        return (
            False,
            "Invalid URL."
        )

    if not is_safe_public_url(
        url
    ):

        return (
            False,
            "URL is not a public web address."
        )

    if not robots_allowed(
        url
    ):

        return (
            False,
            "robots.txt does not allow crawling this URL."
        )

    try:

        wait_for_domain(
            url,
            delay=1.0
        )

        request = (
            urllib.request.Request(
                url,
                headers={
                    "User-Agent":
                        "GyanAI-SearchBot/1.0"
                }
            )
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

            if (
                "text/html"
                not in content_type
            ):

                return (
                    False,
                    "Page is not HTML."
                )

            raw_data = response.read(
                1_000_000
            )

        html = raw_data.decode(
            "utf-8",
            errors="ignore"
        )

        discovered_links = (
            extract_page_links(
                url,
                html
            )
        )

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        title_match = re.search(
            r"<title[^>]*>(.*?)</title>",
            html,
            flags=(
                re.IGNORECASE |
                re.DOTALL
            )
        )

        title = (
            title_match.group(1)
            if title_match
            else ""
        )

        # ----------------------------------------------------
        # DESCRIPTION
        # ----------------------------------------------------

        description = ""

        description_match = re.search(
            r'<meta[^>]+(?:name|property)=["\']'
            r'(?:description|og:description)'
            r'["\'][^>]+content=["\'](.*?)["\']',
            html,
            flags=(
                re.IGNORECASE |
                re.DOTALL
            )
        )

        if description_match:

            description = (
                description_match.group(1)
            )

        # ----------------------------------------------------
        # REMOVE SCRIPT
        # ----------------------------------------------------

        html = re.sub(
            r"<script\b[^>]*>.*?</script>",
            " ",
            html,
            flags=(
                re.IGNORECASE |
                re.DOTALL
            )
        )

        # ----------------------------------------------------
        # REMOVE STYLE
        # ----------------------------------------------------

        html = re.sub(
            r"<style\b[^>]*>.*?</style>",
            " ",
            html,
            flags=(
                re.IGNORECASE |
                re.DOTALL
            )
        )

        # ----------------------------------------------------
        # REMOVE NOSCRIPT
        # ----------------------------------------------------

        html = re.sub(
            r"<noscript\b[^>]*>.*?</noscript>",
            " ",
            html,
            flags=(
                re.IGNORECASE |
                re.DOTALL
            )
        )

        # ----------------------------------------------------
        # REMOVE HTML
        # ----------------------------------------------------

        text = re.sub(
            r"<[^>]+>",
            " ",
            html
        )

        text = (
            text
            .replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
        )

        text = clean_web_text(
            text
        )

        if not text:

            return (
                False,
                "No readable text found."
            )

        save_search_page(
            url=url,
            title=title,
            content=text,
            description=description
        )

        return (
            True,
            {
                "url": url,
                "title": clean_web_text(
                    title
                ),
                "characters": len(text),
                "links": discovered_links
            }
        )

    except urllib.error.HTTPError as error:

        return (
            False,
            f"HTTP error: {error.code}"
        )

    except urllib.error.URLError as error:

        return (
            False,
            f"Connection error: {error.reason}"
        )

    except Exception as error:

        print(
            "CRAWLER ERROR:",
            type(error).__name__,
            str(error)
        )

        return (
            False,
            "Crawler failed."
        )


# ============================================================
#                  CRAWL QUEUE FUNCTIONS
# ============================================================

def queue_crawl_url(
    url: str,
    depth: int = 0,
    priority: int = 0
):

    url = normalize_url(
        url
    )

    if not url:
        return False

    if not is_safe_public_url(
        url
    ):
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
                    max(
                        0,
                        int(depth)
                    ),
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

            return dict(
                job
            )

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


def crawl_queued_pages(
    max_pages: int = 10,
    max_depth: int = 2,
    same_domain: bool = True
):

    max_pages = max(
        1,
        min(
            int(max_pages),
            50
        )
    )

    max_depth = max(
        0,
        min(
            int(max_depth),
            5
        )
    )

    crawled_count = 0
    failed_count = 0

    root_domain = None

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

            if (
                same_domain
                and depth == 0
            ):

                root_domain = (
                    urlparse(url)
                    .netloc
                    .lower()
                )

            if (
                same_domain
                and root_domain
                and urlparse(url).netloc.lower()
                != root_domain
            ):

                finish_crawl_job(
                    job_id,
                    success=False
                )

                continue

            success, result = (
                crawl_web_page(
                    url
                )
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

                if depth < max_depth:

                    for link in discovered_links:

                        if (
                            same_domain
                            and root_domain
                            and urlparse(
                                link
                            ).netloc.lower()
                            != root_domain
                        ):
                            continue

                        queue_crawl_url(
                            url=link,
                            depth=depth + 1,
                            priority=max(
                                0,
                                100 -
                                (
                                    (depth + 1)
                                    * 10
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

        time.sleep(
            1
        )

    return {
        "crawled": crawled_count,
        "failed": failed_count
    }


# ============================================================
#                       SEARCH ENGINE
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
        min(
            int(limit),
            20
        )
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
                    LEFT(
                        content,
                        700
                    ) AS snippet,
                    crawled_at
                FROM gyan_search_pages
                WHERE
                    to_tsvector(
                        'simple',
                        COALESCE(title, '')
                        || ' ' ||
                        COALESCE(
                            description,
                            ''
                        )
                        || ' ' ||
                        COALESCE(
                            content,
                            ''
                        )
                    )
                    @@ websearch_to_tsquery(
                        'simple',
                        %s
                    )
                ORDER BY
                    ts_rank(
                        to_tsvector(
                            'simple',
                            COALESCE(
                                title,
                                ''
                            )
                            || ' ' ||
                            COALESCE(
                                description,
                                ''
                            )
                            || ' ' ||
                            COALESCE(
                                content,
                                ''
                            )
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

            return [
                dict(row)
                for row in cur.fetchall()
            ]

    except Exception as error:

        print(
            "GYAN SEARCH ERROR:",
            type(error).__name__,
            str(error)
        )

        return []

    finally:

        conn.close()


def format_search_context(
    results
):

    if not results:
        return ""

    parts = []

    for index, item in enumerate(
        results,
        start=1
    ):

        parts.append(
            f"""
SOURCE {index}
Title: {item.get("title", "")}
URL: {item.get("url", "")}
Domain: {item.get("domain", "")}
Description: {item.get("description", "")}
Content: {item.get("snippet", "")}
""".strip()
        )

    return "\n\n".join(
        parts
    )


# ============================================================
#                 AI PROVIDER — GEMINI
# ============================================================

def ask_gemini(
    prompt: str
):

    if not gemini_client:

        return None

    try:

        response = (
            gemini_client.models.generate_content(
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

    except Exception as error:

        print(
            "GEMINI ERROR:",
            type(error).__name__,
            str(error)
        )

    return None


# ============================================================
#                 AI PROVIDER — OPENROUTER
# ============================================================

def ask_openrouter(
    prompt: str
):

    if not OPENROUTER_API_KEY:
        return None

    for model in OPENROUTER_MODELS:

        try:

            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.7
            }

            data = json.dumps(
                payload
            ).encode(
                "utf-8"
            )

            request = (
                urllib.request.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    data=data,
                    headers={
                        "Authorization":
                            "Bearer "
                            + OPENROUTER_API_KEY,

                        "Content-Type":
                            "application/json",

                        "HTTP-Referer":
                            "https://gyan-ai-ef7h.onrender.com",

                        "X-Title":
                            "Gyan AI"
                    },
                    method="POST"
                )
            )

            with urllib.request.urlopen(
                request,
                timeout=60
            ) as response:

                raw = response.read()

            result = json.loads(
                raw.decode(
                    "utf-8"
                )
            )

            choices = result.get(
                "choices",
                []
            )

            if choices:

                message = choices[0].get(
                    "message",
                    {}
                )

                content = message.get(
                    "content"
                )

                if content:

                    return str(
                        content
                    ).strip()

        except Exception as error:

            print(
                "OPENROUTER MODEL ERROR:",
                model,
                type(error).__name__,
                str(error)
            )

            continue

    return None


# ============================================================
#                  BUILD AI PROMPT
# ============================================================

def build_ai_prompt(
    user_message: str,
    recent_messages,
    memories,
    search_results
):

    recent_text = []

    for item in recent_messages:

        recent_text.append(
            f'{item["role"]}: '
            f'{item["content"]}'
        )

    memory_text = []

    for memory in memories:

        memory_text.append(
            f'{memory["memory_key"]}: '
            f'{memory["memory_value"]}'
        )

    search_context = (
        format_search_context(
            search_results
        )
        if search_results
        else ""
    )

    prompt = f"""
You are Gyan AI, a helpful AI assistant.

You must answer naturally and clearly.

{GYAN_AI_OFFICIAL_INFO}

IMPORTANT RULES:

1. Never invent official Gyan AI leadership information.
2. Use the user's memories only when relevant.
3. Use the supplied Gyan AI search results when relevant.
4. Do not claim that you searched the live Internet unless
   actual search results are supplied below.
5. If the Gyan AI index has no information, say that the
   information is not currently available in the Gyan AI index.
6. Answer in the user's language whenever practical.
7. Be concise unless the user asks for detail.

USER MEMORIES:
{chr(10).join(memory_text) if memory_text else "No saved memories."}

RECENT CHAT:
{chr(10).join(recent_text) if recent_text else "No recent chat."}

GYAN AI SEARCH RESULTS:
{search_context if search_context else "No matching indexed pages."}

CURRENT USER MESSAGE:
{user_message}

Answer:
""".strip()

    return prompt


# ============================================================
#                  AUTOMATIC MEMORY DETECTION
# ============================================================

def detect_memory(
    user_message: str
):

    text = (
        user_message or ""
    ).strip()

    patterns = [
        (
            r"my name is\s+(.+)",
            "name"
        ),
        (
            r"mera naam\s+(.+?)\s*(?:hai|he)\b",
            "name"
        ),
        (
            r"मेरा नाम\s+(.+?)\s*(?:है|हे)\b",
            "name"
        ),
    ]

    for pattern, key in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:

            value = (
                match.group(1)
                .strip()
                .strip(".")
            )

            if value:

                return key, value

    return None, None


# ============================================================
#                         CHAT ENGINE
# ============================================================

def generate_chat_answer(
    user_id: str,
    conversation_id: str,
    user_message: str
):

    recent_messages = (
        get_recent_messages(
            user_id,
            conversation_id,
            limit=20
        )
    )

    memories = (
        get_memories(
            user_id,
            limit=30
        )
    )

    # Search Gyan AI's own index.
    search_results = (
        search_gyan_index(
            user_message,
            limit=5
        )
    )

    prompt = build_ai_prompt(
        user_message,
        recent_messages,
        memories,
        search_results
    )

    answer = ask_gemini(
        prompt
    )

    if not answer:

        answer = ask_openrouter(
            prompt
        )

    if not answer:

        return (
            None,
            search_results
        )

    return (
        answer,
        search_results
    )


# ============================================================
#                         FASTAPI
# ============================================================

app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description=(
        "Gyan AI official backend API"
    )
)


# ============================================================
#                            CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================
#                         ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "name": APP_TITLE,
        "version": APP_VERSION,
        "status": "online",
        "search_engine": "Gyan AI Own Index",
        "backend": "FastAPI"
    }


@app.get("/health")
def health():

    database_ok = False

    try:

        conn = get_db()

        conn.close()

        database_ok = True

    except Exception:
        database_ok = False

    return {
        "status": "ok",
        "database": database_ok,
        "gemini": bool(
            GEMINI_API_KEY
        ),
        "openrouter": bool(
            OPENROUTER_API_KEY
        )
    }


# ============================================================
#                         REGISTER
# ============================================================

@app.post("/api/register")
def api_register(
    data: dict = Body(...)
):

    username = str(
        data.get(
            "username",
            ""
        )
    )

    password = str(
        data.get(
            "password",
            ""
        )
    )

    user, error = create_user(
        username,
        password
    )

    if error:

        raise HTTPException(
            status_code=400,
            detail=error
        )

    token = create_token(
        user["id"]
    )

    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"]
        }
    }


# ============================================================
#                            LOGIN
# ============================================================

@app.post("/api/login")
def api_login(
    data: dict = Body(...)
):

    username = str(
        data.get(
            "username",
            ""
        )
    )

    password = str(
        data.get(
            "password",
            ""
        )
    )

    user = authenticate_user(
        username,
        password
    )

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Invalid username or password."
        )

    token = create_token(
        user["id"]
    )

    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"]
        }
    }


# ============================================================
#                           LOGOUT
# ============================================================

@app.post("/api/logout")
def api_logout(
    authorization: Optional[str] = Header(
        default=None
    )
):

    return {
        "success": True
    }


# ============================================================
#                             CHAT
# ============================================================

@app.post("/api/chat")
def api_chat(
    data: dict = Body(...),
    authorization: Optional[str] = Header(
        default=None
    )
):

    user_id = get_user_id_from_header(
        authorization
    )

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    message = str(
        data.get(
            "message",
            data.get(
                "prompt",
                ""
            )
        )
    ).strip()

    if not message:

        raise HTTPException(
            status_code=400,
            detail="Message is required."
        )

    conversation_id = data.get(
        "conversation_id"
    )

    if (
        not conversation_id
        or not conversation_exists(
            user_id,
            str(conversation_id)
        )
    ):

        conversation_id = (
            create_conversation(
                user_id,
                title=(
                    message[:60]
                    if message
                    else "New Chat"
                )
            )
        )

    else:

        conversation_id = str(
            conversation_id
        )

    save_message(
        user_id,
        conversation_id,
        "user",
        message
    )

    memory_key, memory_value = (
        detect_memory(
            message
        )
    )

    if memory_key and memory_value:

        save_memory(
            user_id,
            memory_key,
            memory_value
        )

    answer, search_results = (
        generate_chat_answer(
            user_id,
            conversation_id,
            message
        )
    )

    if not answer:

        # Search-only fallback.
        if search_results:

            answer = (
                "Gyan AI Search Index में "
                "कुछ matching results मिले हैं।\n\n"
                +
                "\n".join(
                    [
                        f"{i + 1}. "
                        f"{item.get('title', '')}\n"
                        f"{item.get('url', '')}"
                        for i, item
                        in enumerate(
                            search_results
                        )
                    ]
                )
            )

        else:

            answer = (
                "अभी AI service से उत्तर "
                "नहीं मिल पाया।"
            )

    save_message(
        user_id,
        conversation_id,
        "assistant",
        answer
    )

    return {
        "success": True,
        "answer": answer,
        "response": answer,
        "reply": answer,
        "message": answer,
        "text": answer,
        "content": answer,
        "conversation_id":
            conversation_id,
        "search_results":
            search_results
    }


# ============================================================
#                         NEW CHAT
# ============================================================

@app.post("/new_chat")
def api_new_chat(
    data: dict = Body(...),
    authorization: Optional[str] = Header(
        default=None
    )
):

    user_id = get_user_id_from_header(
        authorization
    )

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    title = str(
        data.get(
            "title",
            "New Chat"
        )
    )

    conversation_id = (
        create_conversation(
            user_id,
            title
        )
    )

    return {
        "success": True,
        "conversation_id":
            conversation_id
    }


# ============================================================
#                         HISTORY
# ============================================================

@app.get("/api/history")
def api_history(
    authorization: Optional[str] = Header(
        default=None
    )
):

    user_id = get_user_id_from_header(
        authorization
    )

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    return {
        "success": True,
        "history":
            get_conversations(
                user_id
            )
    }


@app.get("/api/history/{conversation_id}")
def api_history_detail(
    conversation_id: str,
    authorization: Optional[str] = Header(
        default=None
    )
):

    user_id = get_user_id_from_header(
        authorization
    )

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    if not conversation_exists(
        user_id,
        conversation_id
    ):

        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    return {
        "success": True,
        "conversation_id":
            conversation_id,
        "messages":
            get_conversation_messages(
                user_id,
                conversation_id
            )
    }


@app.delete("/api/history/{conversation_id}")
def api_history_delete(
    conversation_id: str,
    authorization: Optional[str] = Header(
        default=None
    )
):

    user_id = get_user_id_from_header(
        authorization
    )

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    deleted = delete_conversation(
        user_id,
        conversation_id
    )

    return {
        "success": deleted
    }


# ============================================================
#                           MEMORY
# ============================================================

@app.get("/api/memory")
def api_memory(
    authorization: Optional[str] = Header(
        default=None
    )
):

    user_id = get_user_id_from_header(
        authorization
    )

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    return {
        "success": True,
        "memories":
            get_memories(
                user_id
            )
    }


@app.delete("/api/memory/{memory_id}")
def api_memory_delete(
    memory_id: int,
    authorization: Optional[str] = Header(
        default=None
    )
):

    user_id = get_user_id_from_header(
        authorization
    )

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    deleted = delete_memory(
        user_id,
        memory_id
    )

    return {
        "success": deleted
    }


@app.delete("/api/memory")
def api_memory_clear(
    authorization: Optional[str] = Header(
        default=None
    )
):

    user_id = get_user_id_from_header(
        authorization
    )

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    count = clear_memories(
        user_id
    )

    return {
        "success": True,
        "deleted": count
    }


# ============================================================
#                    OWN GYAN SEARCH API
# ============================================================

@app.get("/api/search")
def api_search(
    q: str = "",
    limit: int = 10
):

    q = clean_web_text(
        q
    )

    if not q:

        raise HTTPException(
            status_code=400,
            detail="Search query is required."
        )

    results = search_gyan_index(
        q,
        limit
    )

    return {
        "success": True,
        "query": q,
        "engine":
            "Gyan AI Own Search Index",
        "results": results
    }


# ============================================================
#                       WEB SEARCH
# ============================================================

@app.post("/api/web-search")
def api_web_search(
    data: dict = Body(...),
    authorization: Optional[str] = Header(
        default=None
    )
):

    # Login is not mandatory for search,
    # but if token is supplied it is accepted.

    query = str(
        data.get(
            "query",
            data.get(
                "q",
                ""
            )
        )
    ).strip()

    if not query:

        raise HTTPException(
            status_code=400,
            detail="Search query is required."
        )

    results = search_gyan_index(
        query,
        limit=10
    )

    return {
        "success": True,
        "query": query,
        "engine":
            "Gyan AI Own Search Engine",
        "results": results
    }


# ============================================================
#                  CRAWL / INDEX API
# ============================================================

@app.post("/api/crawl")
def api_crawl(
    data: dict = Body(...),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        bearer_scheme
    )
):

    if not credentials:

        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    user_id = get_user_id_from_header(
        f"Bearer {credentials.credentials}"
    )

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token."
        )

    url = str(
        data.get(
            "url",
            ""
        )
    ).strip()

    if not url:

        raise HTTPException(
            status_code=400,
            detail="URL is required."
        )

    if not is_safe_public_url(
        url
    ):

        raise HTTPException(
            status_code=400,
            detail="Only safe public HTTP/HTTPS URLs can be crawled."
        )

    queued = queue_crawl_url(
        url,
        depth=0,
        priority=100
    )

    if not queued:

        return {
            "success": True,
            "message":
                "URL is already in the crawl queue."
        }

    result = crawl_queued_pages(
        max_pages=10,
        max_depth=2,
        same_domain=True
    )

    return {
        "success": True,
        "queued": True,
        "crawl": result
    }


# ============================================================
#                 YOUTUBE SEARCH COMPATIBILITY
# ============================================================

@app.post("/api/youtube-search")
def api_youtube_search(
    data: dict = Body(...)
):

    query = str(
        data.get(
            "query",
            ""
        )
    ).strip()

    if not query:

        raise HTTPException(
            status_code=400,
            detail="YouTube search query is required."
        )

    encoded = urllib.parse.quote_plus(
        query
    )

    search_url = (
        "https://www.youtube.com/results?search_query="
        + encoded
    )

    # This endpoint intentionally does not
    # use a YouTube API key.
    #
    # It returns the official YouTube search
    # URL so the app can open it.

    return {
        "success": True,
        "query": query,
        "url": search_url,
        "results": []
    }


# ============================================================
#                    IMAGE EDIT COMPATIBILITY
# ============================================================

@app.post("/api/image-edit")
def api_image_edit(
    data: dict = Body(...),
    authorization: Optional[str] = Header(
        default=None
    )
):

    return {
        "success": False,
        "message":
            "Image editing service is not configured yet.",
        "result": None
    }


# ============================================================
#                GRADIO CHAT COMPATIBILITY
# ============================================================

def gradio_chat(
    message,
    history
):

    message = str(
        message or ""
    ).strip()

    if not message:

        return ""

    # Gradio public demo mode does not
    # have an authenticated user.
    #
    # Create a temporary local context
    # only for the Gradio interface.

    demo_user_id = (
        "gradio_demo"
    )

    conversation_id = (
        "gradio_demo_conversation"
    )

    try:

        if not DATABASE_URL:

            prompt = (
                GYAN_AI_OFFICIAL_INFO
                + "\n\n"
                + message
            )

            answer = ask_gemini(
                prompt
            )

            if not answer:

                answer = ask_openrouter(
                    prompt
                )

            return (
                answer
                or
                "AI service से उत्तर नहीं मिला।"
            )

        # Ensure demo user exists.
        conn = get_db()

        try:

            with conn.cursor() as cur:

                cur.execute("""
                    INSERT INTO gyan_users
                    (
                        id,
                        username
                    )
                    VALUES (
                        %s,
                        %s
                    )
                    ON CONFLICT (id)
                    DO NOTHING
                """, (
                    demo_user_id,
                    "gradio_demo"
                ))

                cur.execute("""
                    INSERT INTO conversations
                    (
                        id,
                        user_id,
                        title
                    )
                    VALUES (
                        %s,
                        %s,
                        %s
                    )
                    ON CONFLICT (id)
                    DO NOTHING
                """, (
                    conversation_id,
                    demo_user_id,
                    "Gradio Chat"
                ))

            conn.commit()

        finally:

            conn.close()

        answer, _ = (
            generate_chat_answer(
                demo_user_id,
                conversation_id,
                message
            )
        )

        return (
            answer
            or
            "AI service से उत्तर नहीं मिला।"
        )

    except Exception as error:

        print(
            "GRADIO ERROR:",
            type(error).__name__,
            str(error)
        )

        return (
            "Gyan AI server error."
        )


# ============================================================
#                      STARTUP
# ============================================================

@app.on_event(
    "startup"
)
def startup_event():

    print("=" * 60)
    print("STARTING GYAN AI")
    print(
        "Version:",
        APP_VERSION
    )
    print("=" * 60)

    init_database()

    print(
        "GYAN AI SERVER STARTED"
    )


# ============================================================
#                       GRADIO UI
# ============================================================

try:

    demo = gr.ChatInterface(
        fn=gradio_chat,
        title="Gyan AI",
        description=(
            "Gyan AI — AI Assistant "
            "with memory, chat history "
            "and its own search index."
        )
    )

    gradio_app = demo.app

except Exception as error:

    print(
        "GRADIO INITIALIZATION ERROR:",
        type(error).__name__,
        str(error)
    )

    gradio_app = None


# ============================================================
#                      UVICORN START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "7860"
        )
    )

    print("=" * 60)
    print("GYAN AI SERVER")
    print(
        "PORT:",
        port
    )
    print(
        "API:",
        "FastAPI"
    )
    print(
        "SEARCH:",
        "GYAN AI OWN INDEX"
    )
    print("=" * 60)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )
