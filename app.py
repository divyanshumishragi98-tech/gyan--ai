import os
import time
import json
import re
import uuid
import urllib.request
import urllib.error

import gradio as gr

from google import genai

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None


# ============================================================
#                  GYAN AI V13
#        LONG-TERM MEMORY + CHAT HISTORY
# ============================================================

print("=" * 70)
print("                 GYAN AI V13")
print("       LONG-TERM MEMORY + CHAT HISTORY")
print("=" * 70)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)


# ============================================================
# GEMINI CLIENT
# ============================================================

gemini_client = None

if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )
        print("Gemini client: READY")
    except Exception as error:
        print("Gemini client error:", type(error).__name__)
else:
    print("Gemini API key: NOT FOUND")


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
# DATABASE CONNECTION
# ============================================================

def get_db():
    if psycopg2 is None:
        raise RuntimeError(
            "psycopg2-binary installed नहीं है। "
            "requirements.txt में psycopg2-binary जोड़ें।"
        )

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL Render Environment में नहीं मिला।"
        )

    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        connect_timeout=10
    )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_database():
    if not DATABASE_URL:
        print("WARNING: DATABASE_URL नहीं मिला।")
        return

    if psycopg2 is None:
        print("WARNING: psycopg2-binary नहीं मिला।")
        return

    try:
        connection = get_db()
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gyan_users (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT DEFAULT 'नई बातचीत',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                memory_key TEXT NOT NULL,
                memory_value TEXT NOT NULL,
                source_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, memory_key)
            );
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_user
            ON messages(user_id);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user
            ON memories(user_id);
        """)

        connection.commit()

        cursor.close()
        connection.close()

        print("PostgreSQL database: READY")

    except Exception as error:
        print(
            "Database initialization error:",
            type(error).__name__,
            str(error)
        )


init_database()


# ============================================================
# USER MANAGEMENT
# ============================================================

def ensure_user(user_id):
    if not user_id:
        user_id = str(uuid.uuid4())

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO gyan_users (id)
        VALUES (%s)
        ON CONFLICT (id)
        DO UPDATE SET last_seen = CURRENT_TIMESTAMP
        """,
        (user_id,)
    )

    connection.commit()

    cursor.close()
    connection.close()

    return user_id


# ============================================================
# CONVERSATION MANAGEMENT
# ============================================================

def create_conversation(user_id, title="नई बातचीत"):
    conversation_id = str(uuid.uuid4())

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO conversations
        (id, user_id, title)
        VALUES (%s, %s, %s)
        """,
        (
            conversation_id,
            user_id,
            title[:100]
        )
    )

    connection.commit()

    cursor.close()
    connection.close()

    return conversation_id


def update_conversation_title(
    conversation_id,
    title
):
    if not title:
        return

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE conversations
        SET title = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (
            title[:100],
            conversation_id
        )
    )

    connection.commit()

    cursor.close()
    connection.close()


def touch_conversation(conversation_id):
    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE conversations
        SET updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (conversation_id,)
    )

    connection.commit()

    cursor.close()
    connection.close()


# ============================================================
# SAVE MESSAGE
# ============================================================

def save_message(
    conversation_id,
    user_id,
    role,
    content
):
    if not content:
        return

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO messages
        (conversation_id, user_id, role, content)
        VALUES (%s, %s, %s, %s)
        """,
        (
            conversation_id,
            user_id,
            role,
            content
        )
    )

    connection.commit()

    cursor.close()
    connection.close()

    touch_conversation(conversation_id)


# ============================================================
# GET CURRENT CONVERSATION
# ============================================================

def get_conversation_messages(
    conversation_id,
    user_id,
    limit=100
):
    connection = get_db()

    cursor = connection.cursor(
        cursor_factory=RealDictCursor
    )

    cursor.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
          AND user_id = %s
        ORDER BY id ASC
        LIMIT %s
        """,
        (
            conversation_id,
            user_id,
            limit
        )
    )

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    return [
        {
            "role": row["role"],
            "content": row["content"]
        }
        for row in rows
    ]


# ============================================================
# GET ALL CONVERSATIONS
# ============================================================

def get_user_conversations(user_id):
    connection = get_db()

    cursor = connection.cursor(
        cursor_factory=RealDictCursor
    )

    cursor.execute(
        """
        SELECT id, title, updated_at
        FROM conversations
        WHERE user_id = %s
        ORDER BY updated_at DESC
        LIMIT 100
        """,
        (user_id,)
    )

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    return rows


# ============================================================
# MEMORY SAVE
# ============================================================

def save_memory(
    user_id,
    memory_key,
    memory_value,
    source_text=""
):
    if not user_id:
        return

    if not memory_key or not memory_value:
        return

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO memories
        (
            user_id,
            memory_key,
            memory_value,
            source_text
        )
        VALUES (%s, %s, %s, %s)

        ON CONFLICT (user_id, memory_key)
        DO UPDATE SET
            memory_value = EXCLUDED.memory_value,
            source_text = EXCLUDED.source_text,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            memory_key,
            memory_value[:1000],
            source_text[:2000]
        )
    )

    connection.commit()

    cursor.close()
    connection.close()


# ============================================================
# GET MEMORIES
# ============================================================

def get_user_memories(user_id):
    connection = get_db()

    cursor = connection.cursor(
        cursor_factory=RealDictCursor
    )

    cursor.execute(
        """
        SELECT
            memory_key,
            memory_value,
            source_text,
            updated_at
        FROM memories
        WHERE user_id = %s
        ORDER BY updated_at DESC
        """,
        (user_id,)
    )

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    return rows


# ============================================================
# DELETE ALL MEMORY
# ============================================================

def delete_all_memories(user_id):
    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        DELETE FROM memories
        WHERE user_id = %s
        """,
        (user_id,)
    )

    connection.commit()

    cursor.close()
    connection.close()


# ============================================================
# EXTRACT LONG-TERM MEMORY
# ============================================================

def extract_memories(
    user_id,
    message
):
    if not message:
        return

    text = message.strip()

    # --------------------------------------------------------
    # NAME
    # --------------------------------------------------------

    name_patterns = [
        r"मेरा नाम\s+([A-Za-z\u0900-\u097F ]{2,60})\s+है",
        r"मेरा नाम\s+([A-Za-z\u0900-\u097F ]{2,60})",
        r"my name is\s+([A-Za-z ]{2,60})",
        r"i am\s+([A-Za-z ]{2,60})",
        r"i'm\s+([A-Za-z ]{2,60})",
    ]

    for pattern in name_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            value = match.group(1).strip()

            value = re.sub(
                r"[।.!?,]+$",
                "",
                value
            ).strip()

            if 1 < len(value) <= 60:
                save_memory(
                    user_id,
                    "name",
                    value,
                    text
                )
                print("Memory saved: name =", value)
                break

    # --------------------------------------------------------
    # LIKES / INTERESTS
    # --------------------------------------------------------

    like_patterns = [
        r"मुझे\s+(.{2,100}?)\s+पसंद\s+है",
        r"मुझे\s+(.{2,100}?)\s+पसंद\s+हैं",
        r"मुझे\s+(.{2,100}?)\s+अच्छा\s+लगता\s+है",
        r"मुझे\s+(.{2,100}?)\s+अच्छे\s+लगते\s+हैं",
        r"i\s+like\s+(.{2,100})",
        r"i\s+love\s+(.{2,100})",
        r"i\s+am\s+interested\s+in\s+(.{2,100})",
    ]

    for pattern in like_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            value = match.group(1).strip()

            value = re.sub(
                r"[।.!?,]+$",
                "",
                value
            ).strip()

            if value:
                save_memory(
                    user_id,
                    "interest_" + str(abs(hash(value)))[:12],
                    value,
                    text
                )

    # --------------------------------------------------------
    # PROJECT / GOAL
    # --------------------------------------------------------

    project_patterns = [
        r"मैं\s+(.{2,150}?)\s+बना\s+रहा\s+हूँ",
        r"मैं\s+(.{2,150}?)\s+बना\s+रहा\s+हूं",
        r"मैं\s+(.{2,150}?)\s+बना\s+रही\s+हूँ",
        r"मैं\s+(.{2,150}?)\s+बना\s+रही\s+हूं",
        r"i\s+am\s+building\s+(.{2,150})",
        r"i\s+am\s+making\s+(.{2,150})",
        r"i\s+want\s+to\s+build\s+(.{2,150})",
    ]

    for pattern in project_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            value = match.group(1).strip()

            value = re.sub(
                r"[।.!?,]+$",
                "",
                value
            ).strip()

            if value:
                save_memory(
                    user_id,
                    "project",
                    value,
                    text
                )

    # --------------------------------------------------------
    # STUDY / GOAL
    # --------------------------------------------------------

    goal_patterns = [
        r"मेरा लक्ष्य\s+(.{2,150})",
        r"मेरा गोल\s+(.{2,150})",
        r"मुझे\s+(.{2,150}?)\s+करना\s+है",
        r"my goal is\s+(.{2,150})",
        r"i want to\s+(.{2,150})",
    ]

    for pattern in goal_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            value = match.group(1).strip()

            value = re.sub(
                r"[।.!?,]+$",
                "",
                value
            ).strip()

            if value:
                save_memory(
                    user_id,
                    "goal_" + str(abs(hash(value)))[:12],
                    value,
                    text
                )


# ============================================================
# KEYWORD EXTRACTION
# ============================================================

def extract_keywords(text):
    if not text:
        return []

    words = re.findall(
        r"[\w\u0900-\u097F]{3,}",
        text.lower()
    )

    stop_words = {
        "क्या",
        "कैसे",
        "क्यों",
        "मुझे",
        "मेरा",
        "मेरी",
        "मेरे",
        "तुम",
        "आप",
        "और",
        "यह",
        "वह",
        "है",
        "हैं",
        "था",
        "थे",
        "कर",
        "करना",
        "करके",
        "एक",
        "अब",
        "से",
        "में",
        "पर",
        "को",
        "का",
        "की",
        "के",
        "लिए",
        "और",
        "the",
        "what",
        "how",
        "why",
        "this",
        "that",
        "with",
        "from",
        "have",
        "your",
        "you",
        "are",
        "is",
        "was",
        "for",
        "and",
        "can",
        "please",
    }

    result = []

    for word in words:
        if word in stop_words:
            continue

        if word not in result:
            result.append(word)

    return result[:12]


# ============================================================
# RELEVANT OLD MESSAGES
# ============================================================

def search_relevant_old_messages(
    user_id,
    query,
    limit=12
):
    keywords = extract_keywords(query)

    if not keywords:
        return []

    connection = get_db()

    cursor = connection.cursor(
        cursor_factory=RealDictCursor
    )

    conditions = []
    params = [user_id]

    for keyword in keywords:
        conditions.append(
            "LOWER(content) LIKE %s"
        )
        params.append(
            "%" + keyword + "%"
        )

    where_part = " OR ".join(conditions)

    sql = f"""
        SELECT
            conversation_id,
            role,
            content,
            created_at
        FROM messages
        WHERE user_id = %s
          AND ({where_part})
        ORDER BY created_at DESC
        LIMIT %s
    """

    params.append(limit)

    cursor.execute(
        sql,
        tuple(params)
    )

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    return rows


# ============================================================
# BUILD MEMORY CONTEXT
# ============================================================

def build_memory_context(user_id):
    memories = get_user_memories(user_id)

    if not memories:
        return "अभी कोई स्थायी memory उपलब्ध नहीं है।"

    lines = []

    for item in memories[:30]:
        key = item["memory_key"]
        value = item["memory_value"]

        lines.append(
            f"- {key}: {value}"
        )

    return "\n".join(lines)


# ============================================================
# BUILD OLD CHAT CONTEXT
# ============================================================

def build_old_chat_context(
    user_id,
    current_message
):
    rows = search_relevant_old_messages(
        user_id,
        current_message,
        limit=12
    )

    if not rows:
        return "कोई relevant पुरानी chat नहीं मिली।"

    lines = []

    # Reverse so older relevant messages appear first
    for row in reversed(rows):
        role = row["role"]

        if role == "user":
            speaker = "User"
        else:
            speaker = "Gyan AI"

        content = row["content"]

        lines.append(
            f"{speaker}: {content}"
        )

    return "\n".join(lines)


# ============================================================
# BUILD CURRENT CHAT CONTEXT
# ============================================================

def build_current_chat_context(
    conversation_id,
    user_id,
    limit=30
):
    messages = get_conversation_messages(
        conversation_id,
        user_id,
        limit=limit
    )

    if not messages:
        return "यह नई बातचीत है।"

    lines = []

    for item in messages:
        if item["role"] == "user":
            speaker = "User"
        else:
            speaker = "Gyan AI"

        lines.append(
            f"{speaker}: {item['content']}"
        )

    return "\n".join(lines)


# ============================================================
# GEMINI MODEL
# ============================================================

def ask_gemini_model(
    me
