import os
import time
import json
import re
import uuid
import hashlib
import urllib.request
import urllib.error

import gradio as gr
import psycopg2
from psycopg2.extras import RealDictCursor
from google import genai


# ============================================================
#                 GYAN AI V13.3
#      POSTGRESQL + LONG-TERM MEMORY + CHAT HISTORY
# ============================================================

APP_TITLE = "Gyan AI"

DATABASE_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)

gemini_client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY
    else None
)

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
# DATABASE CONNECTION
# ============================================================

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10
    )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_database():
    if not DATABASE_URL:
        print("WARNING: DATABASE_URL is not configured.")
        return

    conn = None

    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS gyan_users (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT 'New Chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id BIGSERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id BIGSERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                memory_key TEXT NOT NULL,
                memory_value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, memory_key)
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
            ON conversations(user_id, updated_at DESC)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
            ON messages(conversation_id, id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_user_id
            ON messages(user_id, id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user_updated
            ON memories(user_id, updated_at DESC)
        """)

        conn.commit()
        cur.close()

        print("============================================================")
        print("             GYAN AI DATABASE READY")
        print("============================================================")
        print("PostgreSQL connected successfully.")
        print("============================================================")

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
# USER MANAGEMENT
# ============================================================

def ensure_user(user_id):
    if not user_id or not isinstance(user_id, str):
        user_id = str(uuid.uuid4())

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
            DO UPDATE SET updated_at = CURRENT_TIMESTAMP
        """, (user_id,))

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
    user_id,
    title="New Chat"
):
    conversation_id = str(uuid.uuid4())

    if not DATABASE_URL:
        return conversation_id

    conn = None

    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO conversations
            (id, user_id, title)
            VALUES (%s, %s, %s)
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


def update_conversation_title(
    conversation_id,
    user_id,
    title
):
    if not DATABASE_URL or not conversation_id:
        return

    conn = None

    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            UPDATE conversations
            SET title = %s,
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


def get_user_conversations(
    user_id,
    limit=100
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
    user_id,
    conversation_id,
    role,
    content
):
    if not DATABASE_URL or not conversation_id:
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
            INSERT INTO messages
            (
                user_id,
                conversation_id,
                role,
                content
            )
            VALUES (%s, %s, %s, %s)
        """, (
            user_id,
            conversation_id,
            role,
            content
        ))

        cur.execute("""
            UPDATE conversations
            SET updated_at = CURRENT_TIMESTAMP
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
# GET CHAT MESSAGES
# ============================================================

def get_conversation_messages(
    user_id,
    conversation_id,
    limit=80
):
    if not DATABASE_URL or not conversation_id:
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

def extract_search_words(text):
    if not text:
        return []

    words = re.findall(
        r"[A-Za-z0-9\u0900-\u097F]+",
        str(text).lower()
    )

    stop_words = {
        "the",
        "is",
        "am",
        "are",
        "was",
        "were",
        "what",
        "why",
        "how",
        "when",
        "where",
        "who",
        "which",
        "can",
        "could",
        "would",
        "should",
        "do",
        "does",
        "did",
        "and",
        "or",
        "to",
        "of",
        "in",
        "on",
        "for",
        "a",
        "an",
        "my",
        "me",
        "i",
        "you",
        "your",
        "it",
        "this",
        "that",
        "hai",
        "ho",
        "hoga",
        "kya",
        "kaise",
        "kyon",
        "kyun",
        "mujhe",
        "mera",
        "meri",
        "main",
        "mai",
        "ke",
        "ki",
        "ka",
        "ko",
        "se",
        "mein",
        "और",
        "या",
        "है",
        "हूँ",
        "मैं",
        "मेरा",
        "मेरी",
        "मुझे",
        "क्या",
        "कैसे",
        "क्यों",
        "अब",
        "यह",
        "इस",
        "के",
        "की",
        "का",
        "को",
        "में",
        "से"
    }

    result = []

    for word in words:
        if (
            len(word) >= 3
            and word not in stop_words
        ):
            if word not in result:
                result.append(word)

    return result[:15]


# ============================================================
# SEARCH RELEVANT OLD CHATS
# ============================================================

def search_relevant_old_messages(
    user_id,
    current_conversation_id,
    query,
    limit=15
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

        conditions = []

        params = [
            user_id,
            current_conversation_id
        ]

        for keyword in keywords:
            conditions.append(
                "LOWER(content) LIKE %s"
            )

            params.append(
                "%" + keyword + "%"
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
    prefix,
    value
):
    digest = hashlib.sha256(
        value.strip()
        .lower()
        .encode("utf-8")
    ).hexdigest()[:16]

    return f"{prefix}:{digest}"


# ============================================================
# SAVE MEMORY
# ============================================================

def save_memory(
    user_id,
    memory_key,
    memory_value
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
            INSERT INTO memories
            (
                user_id,
                memory_key,
                memory_value
            )
            VALUES (%s, %s, %s)

            ON CONFLICT
            (user_id, memory_key)

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
    user_id,
    limit=50
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
    user_id
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
# CLEAN MEMORY TEXT
# ============================================================

def clean_captured_value(
    value
):
    value = str(
        value or ""
    ).strip()

    value = re.split(
        r"[।!?]\s+",
        value,
        maxsplit=1
    )[0]

    value = re.sub(
        r"\s+(?:है|हैं|हूँ|हूं|hai|hain|ho)$",
        "",
        value,
        flags=re.IGNORECASE
    )

    value = value.strip(
        " \t\n\r.,;:!?।"
    )

    return value


# ============================================================
# EXTRACT LONG-TERM MEMORIES
# ============================================================

def extract_memories(
    user_id,
    message
):
    if not message:
        return

    text = str(
        message
    ).strip()

    # --------------------------------------------------------
    # NAME
    # --------------------------------------------------------

    name_patterns = [
        r"मेरा\s+नाम\s+है\s+([A-Za-z\u0900-\u097F][A-Za-z\u0900-\u097F .'-]{1,60})",
        r"मेरा\s+नाम\s+([A-Za-z\u0900-\u097F][A-Za-z\u0900-\u097F .'-]{1,60})",
        r"my\s+name\s+is\s+([A-Za-z][A-Za-z .'-]{1,60})",
        r"my\s+name's\s+([A-Za-z][A-Za-z .'-]{1,60})",
        r"mera\s+naam\s+hai\s+([A-Za-z\u0900-\u097F][A-Za-z\u0900-\u097F .'-]{1,60})",
        r"mera\s+naam\s+([A-Za-z\u0900-\u097F][A-Za-z\u0900-\u097F .'-]{1,60})"
    ]

    for pattern in name_patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:

            name = clean_captured_value(
                match.group(1)
            )

            if 2 <= len(name) <= 60:

                save_memory(
                    user_id,
                    "profile:name",
                    name
                )

                print(
                    "Memory saved: name =",
                    name
                )

                break

    # --------------------------------------------------------
    # AGE
    # --------------------------------------------------------

    age_patterns = [
        r"मेरी\s+उम्र\s+(\d{1,3})",
        r"मेरी\s+एज\s+(\d{1,3})",
        r"my\s+age\s+is\s+(\d{1,3})",
        r"meri\s+umar\s+(\d{1,3})",
        r"meri\s+age\s+(\d{1,3})",
        r"\bI\s+am\s+(\d{1,3})\s*(?:years?\s*old)?"
    ]

    for pattern in age_patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:

            try:

                age = int(
                    match.group(1)
                )

                if 5 <= age <= 120:

                    save_memory(
                        user_id,
                        "profile:age",
                        str(age)
                    )

                    print(
                        "Memory saved: age =",
                        age
  
