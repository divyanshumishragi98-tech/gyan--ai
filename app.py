import os
import time
import json
import urllib.request
import urllib.error

import gradio as gr
from google import genai


# =========================================================
# API SETUP
# =========================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

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
# OPENROUTER FUNCTION
# =========================================================

def ask_openrouter(message, history):

    if not OPENROUTER_API_KEY:
        return None

    # Current question + recent conversation
    messages = [
        {
            "role": "system",
            "content": (
                "You are Gyan AI, a helpful and friendly AI assistant. "
                "Answer clearly and accurately. "
                "Use the same language as the user's question. "
                "For students, explain concepts simply."
            )
        }
    ]

    # Keep recent chat context
    for item in (history or [])[-10:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role not in ("user", "assistant"):
            continue

        if isinstance(content, str) and content.strip():
            messages.append({
                "role": role,
                "content": content
            })

    # Add current question
    messages.append({
        "role": "user",
        "content": message
    })

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    for model in OPENROUTER_MODELS:

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 700,
            "temperature": 0.4,
        }

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=45
            ) as response:

                data = json.loads(
                    response.read().decode("utf-8")
                )

            choices = data.get("choices", [])

            if not choices:
                continue

            content = choices[0].get(
                "message", {}
            ).get("content")

            # Normal text response
            if isinstance(content, str) and content.strip():
                return content.strip()

            # Some APIs may return content blocks
            if isinstance(content, list):
                text_parts = []

                for item in content:
                    if (
                        isinstance(item, dict)
                        and item.get("type") == "text"
                    ):
                        text_parts.append(
                            item.get("text", "")
                        )

                answer = "\n".join(text_parts).strip()

                if answer:
                    return answer

        except urllib.error.HTTPError as error:
            # Try the next model on rate limits or provider errors
            print(
                f"OpenRouter model failed: {model} "
                f"(HTTP {error.code})"
            )

        except Exception as error:
            print(
                f"OpenRouter model failed: {model} "
                f"({type(error).__name__})"
            )

        time.sleep(1)

    return None


# =========================================================
# GEMINI FUNCTION
# =========================================================

def ask_gemini(message, history):

    if not message or not message.strip():
        return "", history or []

    history = list(history or [])

    # Save the question
    history.append({
        "role": "user",
        "content": message
    })

    answer = None

    # =====================================================
    # TRY GEMINI FIRST
    # =====================================================

    if gemini_client is not None:

        for attempt in range(3):

            try:
                response = (
                    gemini_client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=message
                    )
                )

                if response.text and response.text.strip():
                    answer = response.text.strip()
                    break

            except Exception as error:

                error_text = str(error).lower()

                temporary_error = any(
                    term in error_text
                    for term in [
                        "429",
                        "503",
                        "unavailable",
                        "resource_exhausted",
                        "overloaded",
                        "timeout",
                    ]
                )

                # Retry temporary errors
                if temporary_error and attempt < 2:
                    time.sleep(2)
                    continue

                print(
                    "Gemini failed:",
                    type(error).__name__
                )
                break

    # =====================================================
    # FALL BACK TO OPENROUTER
    # =====================================================

    if not answer:

        print("Trying OpenRouter fallback...")

        answer = ask_openrouter(
            message,
            history[:-1]
        )

    # =====================================================
    # FINAL MESSAGE
    # =====================================================

    if not answer:

        if not GEMINI_API_KEY and not OPENROUTER_API_KEY:
            answer = (
                "⚠️ कोई AI API configure नहीं है।\n\n"
                "Admin को Render Environment में "
                "GEMINI_API_KEY और OPENROUTER_API_KEY "
                "जाँचना होगा।"
            )
        else:
            answer = (
                "⚠️ अभी AI से जवाब नहीं मिल पाया।\n\n"
                "सभी उपलब्ध मॉडल व्यस्त हो सकते हैं या "
                "उनकी उपयोग सीमा पूरी हो सकती है। "
                "थोड़ी देर बाद फिर कोशिश करें।"
            )

    # Save the AI answer
    history.append({
        "role": "assistant",
        "content": answer
    })

    return "", history


# =========================================================
# NEW CHAT
# =========================================================

def clear_chat():
    return []


# =========================================================
# MODERN UI CSS
# =========================================================

css = """
body {
    background: #f7f8fc;
}

#app {
    max-width: 900px;
    margin: auto;
}

#title {
    text-align: center;
    padding: 18px;
}

#chat {
    border-radius: 18px;
}

#message textarea {
    border-radius: 24px !important;
}

#send {
    border-radius: 50% !important;
    min-width: 48px !important;
    height: 48px !important;
}

#newchat {
    border-radius: 12px !important;
}
"""


# =========================================================
# GYAN AI APP
# =========================================================

with gr.Blocks(
    title="Gyan AI",
    css=css
) as app:

    gr.Markdown(
        """
        <div id="title">
            <h1>🧠 Gyan AI</h1>
            <p>Ask. Learn. Grow.</p>
        </div>
        """
    )

    chatbot = gr.Chatbot(
        elem_id="chat",
        height=520,
        placeholder="👋 Ask Gyan AI anything..."
    )

    with gr.Row():

        message = gr.Textbox(
            placeholder="Ask your question...",
            show_label=False,
            elem_id="message",
            scale=8
        )

        send = gr.Button(
            "➤",
            elem_id="send",
            scale=1
        )

    new_chat_btn = gr.Button(
        "＋ New Chat",
        elem_id="newchat"
    )

    send.click(
        ask_gemini,
        inputs=[message, chatbot],
        outputs=[message, chatbot]
    )

    message.submit(
        ask_gemini,
        inputs=[message, chatbot],
        outputs=[message, chatbot]
    )

    new_chat_btn.click(
        clear_chat,
        outputs=[chatbot]
    )


# =========================================================
# START SERVER
# =========================================================

app.launch(
    server_name="0.0.0.0",
    server_port=int(os.environ.get("PORT", 7860))
)
