import os
import re
import uuid
import hashlib
import json
import urllib.request
import urllib.error
from typing import Optional

import gradio as gr
import psycopg2
from psycopg2.extras import RealDictCursor
from google import genai


# ============================================================
#                 GYAN AI V13.5
#       POSTGRESQL + LONG-TERM MEMORY + CHAT HISTORY
#                 GEMINI + OPENROUTER
# ============================================================

APP_TITLE = "Gyan AI"

DATABASE_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)

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

def get_db():

    if not DATABASE_URL:

        raise RuntimeError(
            "DATABASE_URL is not configured."
        )

    return psycopg2.connect(
        DATABASE_URL,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, memory_key)
            )
        """)

        # ----------------------------------------------------
        # INDEXES
        # ----------------------------------------------------

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

        print("=" * 60)
        print("GYAN AI DATABASE READY")
        print("PostgreSQL connected successfully.")
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
# USER MANAGEMENT
# ============================================================

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

