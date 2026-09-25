import os
import time
import json
import urllib.request
import urllib.error

import gradio as gr
from google import genai


# =========================================================
# GYAN AI - API SETUP
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
# CHAT HISTORY HELPER
# =========================================================

def get_previous_messages(history):
    """
    Gradio chat history से पिछली बातचीत निकालता है।
    केवल user और assistant के text messages रखता है।
    """

    messages = []

    for item in (history or [])[-20:]:

        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role not in ("user", "assistant"):
            continue

        if isinstance(content, str) and content.strip():
            messages.append({
                "role": role,
                "content": content.strip()
            })

    return messages


# =========================================================
# GEMINI FUNCTION WITH CHAT MEMORY
# =========================================================

def ask_gemini_model(message, previous_messages):

    if gemini_client is None:
        return None

    # पिछली बातचीत को Gemini के prompt में जोड़ना
    conversation = []

    for item in previous_messages:
        if item["role"] == "user":
            conversation.append(
                "User: " + item["content"]
            )
        else:
            conversation.append(
                "Gyan AI: " + item["content"]
            )

    previous_chat = (
        "\n".join(conversation)
        if conversation
        else "यह नई बातचीत है।"
    )

    prompt = f"""
तुम Gyan AI हो, एक helpful AI assistant।

महत्वपूर्ण निर्देश:
1. पिछली बातचीत को ध्यान से पढ़ो।
2. उपयोगकर्ता ने अपना नाम या कोई जानकारी पहले बताई हो,
   तो उसी बातचीत के संदर्भ में उसका उपयोग करो।
3. अगर उपयोगकर्ता पूछे कि उसने पहले क्या बताया था,
   तो पिछली बातचीत के आधार पर जवाब दो।
4. उपयोगकर्ता की भाषा में जवाब दो।
5. अगर जानकारी पिछली बातचीत में नहीं है,
   तो साफ बताओ कि तुम्हें वह जानकारी नहीं मिली।
6. बिना आधार के कोई व्यक्तिगत जानकारी मत बनाओ।

पिछली बातचीत:
{previous_chat}

अभी उपयोगकर्ता का सवाल:
{message}

Gyan AI का जवाब:
"""

    for attempt in range(3):

        try:
            response = gemini_client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )

            answer = getattr(response, "text", None)

            if isinstance(answer, str) and answer.strip():
                return answer.strip()

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

            print(
                "Gemini error:",
                type(error).__name__
            )

            if temporary_error and attempt < 2:
                time.sleep(2)
                continue

            break

    return None


# =========================================================
# OPENROUTER FUNCTION WITH CHAT MEMORY
# =========================================================

def ask_openrouter_model(message, previous_messages):

    if not OPENROUTER_API_KEY:
        return None

    messages = [
        {
            "role": "system",
            "content": (
                "You are Gyan AI, a helpful and friendly AI assistant. "
                "Use the same language as the user's question. "
                "Remember and use the conversation history provided "
                "in this request. If the user previously shared "
                "their name or other information in this conversation, "
                "use it when relevant. Do not invent personal details. "
                "Explain things simply for students."
            )
        }
    ]

    # पिछली बातचीत
    messages.extend(previous_messages)

    # वर्तमान सवाल
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

            if isinstance(content, str) and content.strip():
                return content.strip()

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
# MAIN QUESTION FUNCTION
# =========================================================

def ask_gemini(message, history):

    if not message or not message.strip():
        return "", history or []

    # पुरानी बातचीत को पहले सुरक्षित निकालें
    previous_messages = get_previous_messages(history)

    # Gemini पहले कोशिश करेगा
    answer = ask_gemini_model(
        message,
        previous_messages
    )

    # Gemini विफल होने पर OpenRouter
    if not answer:
        print("Trying OpenRouter fallback...")

        answer = ask_openrouter_model(
            message,
            previous_messages
        )

    # दोनों से जवाब न मिले
    if not answer:

        if not GEMINI_API_KEY and not OPENROUTER_API_KEY:
            answer = (
                "⚠️ कोई AI API configure नहीं है।\n\n"
                "Admin को Render Environment में "
                "GEMINI_API_KEY और OPENROUTER_API_KEY "
                "जाँचनी होंगी।"
            )

        else:
            answer = (
                "⚠️ अभी AI से जवाब नहीं मिल पाया।\n\n"
                "मॉडल व्यस्त हो सकते हैं या उनकी उपयोग सीमा "
                "पूरी हो सकती है। कृपया थोड़ी देर बाद कोशिश करें।"
            )

    # पुरानी बातचीत को बनाए रखें
    updated_history = list(history or [])

    # वर्तमान सवाल और जवाब जोड़ें
    updated_history.append({
        "role": "user",
        "content": message
    })

    updated_history.append({
        "role": "assistant",
        "content": answer
    })

    return "", updated_history


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

    # Send button
    send.click(
        ask_gemini,
        inputs=[message, chatbot],
        outputs=[message, chatbot]
    )

    # Enter key
    message.submit(
        ask_gemini,
        inputs=[message, chatbot],
        outputs=[message, chatbot]
    )

    # New chat
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
