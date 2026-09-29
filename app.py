import os
import time
import json
import re
import uuid
import urllib.request
import urllib.error

import gradio as gr
import psycopg2
from psycopg2.extras import RealDictCursor
from google import genai


# =========================================================
# GYAN AI — V13
# POSTGRESQL + LONG TERM MEMORY + COMPLETE CHAT HISTORY
# =========================================================


APP_NAME = "Gyan AI"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Model can be changed from Render Environment Variables
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)

DATABASE_URL = os.environ.get("DATABASE_URL")


# =========================================================
# GEMINI CLIENT
# =========================================================

gemini_client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY
    else None
)


# =========================================================
# OPENROUTER MODELS
# =========================================================

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


# =========================================================
# DATABASE
# =========================================================

def get_db_connection():
    """
    Render PostgreSQL से connection बनाता है।
    """

    if not DATABASE_URL:
        return None

    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10
    )


def init_database():
    """
    पहली बार database में सभी tables बनाता है।
    """

    if not DATABASE_URL:
        print("WARNING: DATABASE_URL is not configured.")
        return

    connection = None

    try:

        connection = get_db_connection()

        with connection.cursor() as cursor:

            # -------------------------------------------------
            # USERS
            # -------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gyan_users (
                    user_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # -------------------------------------------------
            # CONVERSATIONS
            # -------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT DEFAULT 'New Chat',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # -------------------------------------------------
            # MESSAGES
            # -------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # -------------------------------------------------
            # LONG TERM MEMORIES
            # -------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    memory TEXT NOT NULL,
                    memory_type TEXT DEFAULT 'general',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, memory)
                )
            """)

            # -------------------------------------------------
            # INDEXES
            # -------------------------------------------------

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_user
                ON messages(user_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_user
                ON conversations(user_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_user
                ON memories(user_id)
            """)

        connection.commit()

        print("=================================================")
        print("GYAN AI DATABASE READY")
        print("PostgreSQL tables initialized successfully.")
        print("=================================================")

    except Exception as error:

        print(
            "DATABASE INIT ERROR:",
            type(error).__name__,
            str(error)
        )

        if connection:
            connection.rollback()

    finally:

        if connection:
            connection.close()


# Database initialize
init_database()


# =========================================================
# USER MANAGEMENT
# =========================================================

def ensure_user(user_id):

    if not user_id:
        return

    connection = None

    try:

        connection = get_db_connection()

        if not connection:
            return

        with connection.cursor() as cursor:

            cursor.execute("""
                INSERT INTO gyan_users (user_id)
                VALUES (%s)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id,))

        connection.commit()

    except Exception as error:

        print(
            "USER ERROR:",
            type(error).__name__,
            str(error)
        )

        if connection:
            connection.rollback()

    finally:

        if connection:
            connection.close()


# =========================================================
# CONVERSATION MANAGEMENT
# =========================================================

def create_conversation(user_id, title="New Chat"):

    conversation_id = str(uuid.uuid4())

    connection = None

    try:

        connection = get_db_connection()

        if not connection:
            return conversation_id

        with connection.cursor() as cursor:

            cursor.execute("""
                INSERT INTO conversations
                (
                    conversation_id,
                    user_id,
                    title
                )
                VALUES (%s, %s, %s)
            """, (
                conversation_id,
                user_id,
                title[:120]
            ))

        connection.commit()

    except Exception as error:

        print(
            "CREATE CONVERSATION ERROR:",
            type(error).__name__,
            str(error)
        )

        if connection:
            connection.rollback()

    finally:

        if connection:
            connection.close()

    return conversation_id


def update_conversation_title(
    user_id,
    conversation_id,
    message
):

    if not message:
        return

    title = message.strip().replace("\n", " ")

    if len(title) > 70:
        title = title[:67] + "..."

    connection = None

    try:

        connection = get_db_connection()

        if not connection:
            return

        with connection.cursor() as cursor:

            cursor.execute("""
                UPDATE conversations
                SET
                    title = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE
                    conversation_id = %s
                    AND user_id = %s
            """, (
                title,
                conversation_id,
                user_id
            ))

        connection.commit()

    except Exception as error:

        print(
            "TITLE UPDATE ERROR:",
            type(error).__name__,
            str(error)
        )

        if connection:
            connection.rollback()

    finally:

        if connection:
            connection.close()


def touch_conversation(
    user_id,
    conversation_id
):

    connection = None

    try:

        connection = get_db_connection()

        if not connection:
            return

        with connection.cursor() as cursor:

            cursor.execute("""
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE conversation_id = %s
                AND user_id = %s
            """, (
                conversation_id,
                user_id
            ))

        connection.commit()

    except Exception as error:

        print(
            "CONVERSATION UPDATE ERROR:",
            type(error).__name__,
            str(error)
        )

        if connection:
            connection.rollback()

    finally:

        if connection:
            connection.close()


# =========================================================
# SAVE MESSAGE
# =========================================================

def save_message(
    user_id,
    conversation_id,
    role,
    content
):

    if not user_id:
        return

    if not conversation_id:
        return

    if not content:
        return

    content = str(content).strip()

    if not content:
        return

    connection = None

    try:

        connection = get_db_connection()

        if not connection:
            return

        with connection.cursor() as cursor:

            cursor.execute("""
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

        connection.commit()

    except Exception as error:

        print(
            "SAVE MESSAGE ERROR:",
            type(error).__name__,
            str(error)
        )

        if connection:
            connection.rollback()

    finally:

        if connection:
            connection.close()


# =========================================================
# LOAD COMPLETE CONVERSATION
# =========================================================

def load_conversation(
    user_id,
    conversation_id
):

    if not user_id or not conversation_id:
        return []

    connection = None
    result = []

    try:

        connection = get_db_connection()

        if not connection:
            return []

        with connection.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute("""
                SELECT role, content
                FROM messages
                WHERE user_id = %s
                AND conversation_id = %s
                ORDER BY id ASC
            """, (
                user_id,
                conversation_id
            ))

            rows = cursor.fetchall()

            for row in rows:

                if row["role"] not in (
                    "user",
                    "assistant"
                ):
                    continue

                result.append({
                    "role": row["role"],
                    "content": row["content"]
                })

    except Exception as error:

        print(
            "LOAD CONVERSATION ERROR:",
            type(error).__name__,
            str(error)
        )

    finally:

        if connection:
            connection.close()

    return result


# =========================================================
# LOAD RECENT MESSAGES FROM ALL USER CHATS
# =========================================================

def load_recent_user_messages(
    user_id,
    limit=40
):

    if not user_id:
        return []

    connection = None
    result = []

    try:

        connection = get_db_connection()

        if not connection:
            return []

        with connection.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute("""
                SELECT
                    conversation_id,
                    role,
                    content,
                    created_at
                FROM messages
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT %s
            """, (
                user_id,
                limit
            ))

            rows = cursor.fetchall()

            for row in reversed(rows):

                result.append({
                    "conversation_id":
                        row["conversation_id"],
                    "role":
                        row["role"],
                    "content":
                        row["content"]
                })

    except Exception as error:

        print(
            "RECENT MESSAGE ERROR:",
            type(error).__name__,
            str(error)
        )

    finally:

        if connection:
            connection.close()

    return result


# =========================================================
# RELEVANT OLD CHAT SEARCH
# =========================================================

STOP_WORDS = {
    "the",
    "is",
    "are",
    "was",
    "were",
    "what",
    "why",
    "how",
    "when",
    "where",
    "who",
    "this",
    "that",
    "with",
    "from",
    "have",
    "has",
    "and",
    "for",
    "you",
    "your",
    "मेरी",
    "मेरा",
    "मेरे",
    "मुझे",
    "क्या",
    "कैसे",
    "कहाँ",
    "क्यों",
    "अब",
    "और",
    "है",
    "हैं",
    "था",
    "थी",
    "थे",
    "को",
    "का",
    "के",
    "की",
    "में",
    "से",
    "पर",
    "एक",
    "यह",
    "वह",
    "तो",
    "भी",
}


def extract_search_keywords(text):

    if not text:
        return []

    words = re.findall(
        r"[A-Za-z0-9\u0900-\u097F]+",
        text.lower()
    )

    keywords = []

    for word in words:

        if word in STOP_WORDS:
            continue

        if len(word) < 3:
            continue

        if word not in keywords:
            keywords.append(word)

    return keywords[:12]


def search_relevant_old_messages(
    user_id,
    current_message,
    limit=25
):

    if not user_id:
        return []

    keywords = extract_search_keywords(
        current_message
    )

    if not keywords:
        return []

    connection = None
    result = []

    try:

        connection = get_db_connection()

        if not connection:
            return []

        conditions = []

        values = [user_id]

        for keyword in keywords:

            conditions.append(
                "content ILIKE %s"
            )

            values.append(
                "%" + keyword + "%"
            )

        query = f"""
            SELECT
                conversation_id,
                role,
                content,
                created_at
            FROM messages
            WHERE user_id = %s
            AND ({' OR '.join(conditions)})
            ORDER BY id DESC
            LIMIT %s
        """

        values.append(limit)

        with connection.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                query,
                tuple(values)
            )

            rows = cursor.fetchall()

            for row in reversed(rows):

                result.append({
                    "conversation_id":
                        row["conversation_id"],
                    "role":
                        row["role"],
                    "content":
                        row["content"]
                })

    except Exception as error:

        print(
            "OLD CHAT SEARCH ERROR:",
            type(error).__name__,
            str(error)
        )

    finally:

        if connection:
            connection.close()

    return result


# =========================================================
# MEMORY SAVE
# =========================================================

def save_memory(
    user_id,
    memory,
    memory_type="general"
):

    if not user_id or not memory:
        return

    memory = memory.strip()

    if len(memory) < 3:
        return

    if len(memory) > 500:
        memory = memory[:500]

    connection = None

    try:

        connection = get_db_connection()

        if not connection:
            return

        with connection.cursor() as cursor:

            cursor.execute("""
                INSERT INTO memories
                (
                    user_id,
                    memory,
                    memory_type
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, memory)
                DO UPDATE SET
                    updated_at = CURRENT_TIMESTAMP
            """, (
                user_id,
                memory,
                memory_type
            ))

        connection.commit()

    except Exception as error:

        print(
            "SAVE MEMORY ERROR:",
            type(error).__name__,
            str(error)
        )

        if connection:
            connection.rollback()

    finally:

        if connection:
            connection.close()


# =========================================================
# SIMPLE LONG-TERM MEMORY DETECTOR
# =========================================================

def detect_memories(text):

    if not text:
        return []

    memories = []

    # -----------------------------------------------------
    # NAME
    # -----------------------------------------------------

    name_patterns = [
        r"(?:मेरा नाम|मुझे|my name is)\s+([A-Za-z\u0900-\u097F ]{2,50})",
        r"(?:mera naam)\s+([A-Za-z\u0900-\u097F ]{2,50})",
    ]

    for pattern in name_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            name = match.group(1).strip()

            name = re.sub(
                r"\b(है|हूं|हूँ|is|hai|hoon|hu)\b.*$",
                "",
                name,
                flags=re.IGNORECASE
            ).strip()

            if name:

                memories.append(
                    (
                        f"User's name is {name}",
                        "name"
                    )
                )

                break

    # -----------------------------------------------------
    # LIKES / INTERESTS
    # -----------------------------------------------------

    like_patterns = [
        r"मुझे\s+(.{2,100}?)\s+पसंद\s+है",
        r"मुझे\s+(.{2,100}?)\s+पसंद\s+हैं",
        r"i\s+like\s+(.{2,100})",
        r"i\s+love\s+(.{2,100})",
        r"मुझे\s+(.{2,100}?)\s+अच्छा\s+लगता\s+है",
    ]

    for pattern in like_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            interest = match.group(1).strip()

            if interest:

                memories.append(
                    (
                        f"User likes {interest}",
                        "interest"
                    )
                )

    # -----------------------------------------------------
    # PROJECT / GOAL
    # -----------------------------------------------------

    project_patterns = [
        r"मैं\s+(.{2,150}?)\s+बना\s+रहा\s+हूँ",
        r"मैं\s+(.{2,150}?)\s+बना\s+रहा\s+ह
