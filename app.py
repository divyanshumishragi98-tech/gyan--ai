import os
import time
import gradio as gr
from google import genai


# =========================================================
# GEMINI API SETUP
# =========================================================

API_KEY = os.environ.get("GEMINI_API_KEY")

client = genai.Client(api_key=API_KEY) if API_KEY else None


# =========================================================
# GEMINI QUESTION FUNCTION
# =========================================================

def ask_gemini(message, history):

    # Empty message
    if not message or not message.strip():
        return "", history

    # Make sure history exists
    history = history or []

    # Add user's question
    history.append({
        "role": "user",
        "content": message
    })

    # =====================================================
    # API KEY CHECK
    # =====================================================

    if client is None:

        answer = (
            "⚠️ Gemini API अभी configure नहीं हुई है.\n\n"
            "Admin को GEMINI_API_KEY check करनी होगी."
        )

    else:

        answer = None

        # =================================================
        # GEMINI RETRY SYSTEM
        # =================================================

        for attempt in range(3):

            try:

                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=message
                )

                # Successful response
                answer = response.text

                break

            except Exception as e:

                error_text = str(e)

                # =========================================
                # TEMPORARY GEMINI ERRORS
                # =========================================

                temporary_error = (
                    "429" in error_text
                    or "503" in error_text
                    or "UNAVAILABLE" in error_text
                    or "RESOURCE_EXHAUSTED" in error_text
                    or "overloaded" in error_text.lower()
                )

                if temporary_error:

                    # Retry if attempts are remaining
                    if attempt < 2:

                        time.sleep(3)

                        continue

                # =========================================
                # FINAL ERROR
                # =========================================

                answer = (
                    "⚠️ अभी Gemini से जवाब नहीं मिल पाया।\n\n"
                    "थोड़ी देर बाद फिर से कोशिश करें।"
                )

                break

    # =====================================================
    # ADD AI ANSWER
    # =====================================================

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


/* Main application */
#app {
    max-width: 900px;
    margin: auto;
}


/* Header */
#title {
    text-align: center;
    padding: 18px;
}


/* Chat */
#chat {
    border-radius: 18px;
}


/* Message box */
#message textarea {
    border-radius: 24px !important;
}


/* Send button */
#send {
    border-radius: 50% !important;
    min-width: 48px !important;
    height: 48px !important;
}


/* New chat button */
#newchat {
    border-radius: 12px !important;
}

"""


# =========================================================
# GYAN AI APP
# =========================================================

with gr.Blocks(
    title="Gyan AI"
) as app:

    # =====================================================
    # HEADER
    # =====================================================

    gr.Markdown(
        """
        <div id="title">
            <h1>🧠 Gyan AI</h1>
            <p>Ask. Learn. Grow.</p>
        </div>
        """
    )


    # =====================================================
    # CHAT WINDOW
    # =====================================================

    chatbot = gr.Chatbot(
        elem_id="chat",
        height=520,
        placeholder="👋 Ask Gyan AI anything..."
    )


    # =====================================================
    # QUESTION INPUT
    # =====================================================

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


    # =====================================================
    # NEW CHAT
    # =====================================================

    new_chat_btn = gr.Button(
        "＋ New Chat",
        elem_id="newchat"
    )


    # =====================================================
    # SEND BUTTON
    # =====================================================

    send.click(
        ask_gemini,
        inputs=[
            message,
            chatbot
        ],
        outputs=[
            message,
            chatbot
        ]
    )


    # =====================================================
    # ENTER KEY
    # =====================================================

    message.submit(
        ask_gemini,
        inputs=[
            message,
            chatbot
        ],
        outputs=[
            message,
            chatbot
        ]
    )


    # =====================================================
    # NEW CHAT BUTTON
    # =====================================================

    new_chat_btn.click(
        clear_chat,
        outputs=[
            chatbot
        ]
    )


# =========================================================
# START SERVER
# =========================================================

app.launch(
    server_name="0.0.0.0",
    server_port=int(
        os.environ.get("PORT", 7860)
    ),
    css=css
)
