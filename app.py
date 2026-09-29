# ============================================================
#                 GYAN AI V13.1
#        LONG-TERM MEMORY + CHAT HISTORY ENGINE
# ============================================================

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
# CONFIG
# ============================================================

APP_TITLE = "Gyan AI"

DATABASE_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

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
# DATABASE
# ============================================================

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10
    )


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
                title TEXT DEFAULT 'New Chat',
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
            CREATE INDEX IF NOT EXISTS idx_messages_user
            ON messages(user_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_user
            ON conversations(user_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user
            ON memories(user_id)
        """)

        conn.commit()
        cur.close()

        print("============================================================")
        print("GYAN AI DATABASE READY")
        print("PostgreSQL connected successfully.")
        print("============================================================")

    except Exception as error:
        print("DATABASE INIT ERROR:", type(error).__name__, str(error))

    finally:
        if conn:
            conn.close()


# ============================================================
# USER
# ============================================================

def ensure_user(user_id):
    if not user_id:
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
        print("USER DATABASE ERROR:", type(error).__name__, str(error))

    finally:
        if conn:
            conn.close()

    return user_id


# ============================================================
# CONVERSATIONS
# ============================================================

def create_conversation(user_id, title="New Chat"):
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
            title[:100]
        ))

        conn.commit()
        cur.close()

    except Exception as error:
        print("CREATE CONVERSATION ERROR:", type(error).__name__, str(error))

    finally:
        if conn:
            conn.close()

    return conversation_id


def update_conversation_title(conversation_id, user_id, title):
    if not DATABASE_URL:
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
            title[:100],
            conversation_id,
            user_id
        ))

        conn.commit()
        cur.close()

    except Exception as error:
        print(
            "UPDATE CONVERSATION ERROR:",
            type(error).__name__,
            str(error)
        )

    finally:
        if conn:
            conn.close()


# ============================================================
# SAVE MESSAGE
# ============================================================

def save_message(user_id, conversation_id, role, content):
    if not DATABASE_URL:
        return

    if not content or not str(content).strip():
        return

    conn = None

    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO messages
            (user_id, conversation_id, role, content)
            VALUES (%s, %s, %s, %s)
        """, (
            user_id,
            conversation_id,
            role,
            str(content).strip()
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
# LOAD CURRENT CONVERSATION
# ============================================================

def get_conversation_messages(
    user_id,
    conversation_id,
    limit=80
):
    if not DATABASE_URL:
        return []

    conn = None

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT role, content
            FROM (
                SELECT id, role, content
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
# ALL CONVERSATIONS
# ============================================================

def get_user_conversations(user_id):
    if not DATABASE_URL:
        return []

    conn = None

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = %s
            ORDER BY updated_at DESC
            LIMIT 100
        """, (user_id,))

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
# RELEVANT OLD CHAT SEARCH
# ============================================================

def extract_search_words(text):
    if not text:
        return []

    words = re.findall(
        r"[A-Za-z0-9\u0900-\u097F]+",
        text.lower()
    )

    stop_words = {
        "the", "is", "am", "are", "was", "were",
        "what", "why", "how", "when", "where",
        "who", "which", "can", "could", "would",
        "should", "do", "does", "did",
        "and", "or", "to", "of", "in", "on",
        "for", "a", "an", "my", "me", "i",
        "you", "your", "it", "this", "that",
        "hai", "ho", "hoga", "kya", "kaise",
        "mujhe", "mera", "meri", "main", "mai",
        "ke", "ki", "ka", "ko", "se", "me",
        "और", "या", "है", "हूँ", "मैं", "मेरा",
        "मेरी", "मुझे", "क्या", "कैसे", "क्यों",
        "अब", "वो", "यह", "इस", "के", "की",
        "का", "को", "में", "से"
    }

    result = []

    for word in words:
        if len(word) >= 3 and word not in stop_words:
            if word not in result:
                result.append(word)

    return result[:15]


def search_relevant_old_messages(
    user_id,
    current_conversation_id,
    query,
    limit=15
):
    if not DATABASE_URL:
        return []

    keywords = extract_search_words(query)

    if not keywords:
        return []

    conn = None

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        conditions = []
        params = [user_id]

        for word in keywords:
            conditions.append(
                "LOWER(content) LIKE %s"
            )
            params.append("%" + word + "%")

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

        params.insert(1, current_conversation_id)
        params.append(limit)

        cur.execute(sql, params)

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
# LONG-TERM MEMORY
# ============================================================

def deterministic_key(prefix, value):
    digest = hashlib.sha256(
        value.strip().lower().encode("utf-8")
    ).hexdigest()[:16]

    return f"{prefix}:{digest}"


def save_memory(user_id, memory_key, memory_value):
    if not DATABASE_URL:
        return

    if not memory_value or not memory_value.strip():
        return

    conn = None

    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO memories
            (user_id, memory_key, memory_value)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, memory_key)
            DO UPDATE SET
                memory_value = EXCLUDED.memory_value,
                updated_at = CURRENT_TIMESTAMP
        """, (
            user_id,
            memory_key,
            memory_value.strip()
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


def get_memories(user_id, limit=50):
    if not DATABASE_URL:
        return []

    conn = None

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT memory_key, memory_value
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


def delete_memories(user_id):
    if not DATABASE_URL:
        return

    conn = None

    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            DELETE FROM memories
            WHERE user_id = %s
        """, (user_id,))

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
# MEMORY EXTRACTION
# ============================================================

def extract_memories(user_id, message):
    if not message:
        return

    text = message.strip()

    # ---------------- NAME ----------------

    name_patterns = [
        r"(?:मेरा नाम|मेरा नाम है)\s+([A-Za-z\u0900-\u097F][A-Za-z\u0900-\u097F .'-]{1,50})",
        r"(?:my name is|my name's)\s+([A-Za-z][A-Za-z .'-]{1,50})",
        r"(?:mera naam)\s+([A-Za-z\u0900-\u097F][A-Za-z\u0900-\u097F .'-]{1,50})",
    ]

    for pattern in name_patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            name = match.group(1).strip()

            name = re.sub(
                r"\s+(hai|है|हूँ|ho|is)$",
                "",
                name,
                flags=re.IGNORECASE
            ).strip()

            if 1 < len(name) <= 60:
                save_memory(
                    user_id,
                    "profile:name",
                    name
                )
                print("Memory saved: name =", name)
                break

    # ---------------- AGE ----------------

    age_patterns = [
        r"\bmeri age\s+(\d{1,3})",
        r"\bmeri umar\s+(\d{1,3})",
        r"\bmy age is\s+(\d{1,3})",
        r"\bI am\s+(\d{1,3})\s*(?:years old|year old|saal ka|saal ki)?",
        r"\bमैं\s+(\d{1,3})\s*(?:साल|वर्ष)?\s*(?:का|की)?\s*हूँ"
    ]

    for pattern in age_patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            age = match.group(1)

            try:
                age_number = int(age)

                if 5 <= age_number <= 120:
                    save_memory(
                        user_id,
                        "profile:age",
                        str(age_number)
                    )
                    print("Memory saved: age =", age_number)
                    break

            except Exception:
                pass

    # ---------------- LIKES / INTEREST ----------------

    interest_patterns = [
        r"मुझे\s+(.{2,100}?)\s+पसंद\s+है",
        r"मुझे\s+(.{2,100}?)\s+पसंद\s+हैं",
        r"mujhe\s+(.{2,100}?)\s+pasand\s+hai",
        r"i\s+like\s+(.{2,100})",
        r"i\s+love\s+(.{2,100})",
    ]

    for pattern in interest_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            value = match.group(1).strip()

            if 2 <= len(value) <= 120:
                key = deterministic_key(
                    "interest",
                    value
                )

                save_memory(
                    user_id,
                    key,
                    value
                )

                print(
                    "Memory saved: interest =",
                    value
                )

    # ---------------- PROJECT / GOAL ----------------

    project_patterns = [
        r"मैं\s+(.{2,150}?)\s+बना\s+रहा\s+हूँ",
        r"मैं\s+(.{2,150}?)\s+बना\s+रहा\s+हूं",
        r"मैं\s+(.{2,150}?)\s+बना\s+रही\s+हूँ",
        r"मैं\s+(.{2,150}?)\s+बना\s+रही\s+हूं",
        r"i\s+am\s+building\s+(.{2,150})",
        r"i\s+am\s+making\s+(.{2,150})",
        r"i\s+want\s+to\s+build\s+(.{2,150})",
        r"मैं\s+(.{2,150}?)\s+बनाना\s+चाहता\s+हूँ",
        r"मैं\s+(.{2,150}?)\s+बनाना\s+चाहता\s+हूं"
    ]

    for pattern in project_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            value = match.group(1).strip()

            if 3 <= len(value) <= 180:
                key = deterministic_key(
                    "goal",
                    value
                )

                save_memory(
                    user_id,
                    key,
                    value
                )

                print(
                    "Memory saved: goal =",
                    value
                )


# ============================================================
# MEMORY TEXT
# ============================================================

def format_memories(user_id):
    memories = get_memories(user_id)

    if not memories:
        return "अभी कोई long-term memory saved नहीं है।"

    lines = []

    for item in memories:
        key = item["memory_key"]
        value = item["memory_value"]

        if key.startswith("profile:name"):
            lines.append(f"नाम: {value}")

        elif key.startswith("profile:age"):
            lines.append(f"उम्र: {value}")

        elif key.startswith("interest:"):
            lines.append(f"पसंद/रुचि: {value}")

        elif key.startswith("goal:"):
            lines.append(f"लक्ष्य/प्रोजेक्ट: {value}")

        else:
            lines.append(f"{value}")

    return "\n".join(lines)


# ============================================================
# GEMINI
# ============================================================

def ask_gemini_model(
    message,
    current_messages,
    old_messages,
    memories
):
    if gemini_client is None:
        return None

    current_chat_lines = []

    for item in current_messages:
        role = item.get("role")
        content = item.get("content", "")

        if role == "user":
