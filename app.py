import os
import gradio as gr
from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY")

client = genai.Client(api_key=API_KEY) if API_KEY else None


def ask_gemini(message, history):
    if not message.strip():
        return "", history

    history = history or []

    history.append({
        "role": "user",
        "content": message
    })

    if client is None:
        answer = "⚠️ Gemini API अभी configure नहीं हुई है."
    else:
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=message
            )
            answer = response.text
        except Exception as e:
            answer = f"⚠️ Error: {str(e)}"

    history.append({
        "role": "assistant",
        "content": answer
    })

    return "", history


def clear_chat():
    return []


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
"""


with gr.Blocks(title="Gyan AI") as app:

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

    new_chat = gr.Button("＋ New Chat")

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

    new_chat.click(
        clear_chat,
        outputs=chatbot
    )


app.launch(
    server_name="0.0.0.0",
    server_port=int(os.environ.get("PORT", 7860)),
    css=css
      )
