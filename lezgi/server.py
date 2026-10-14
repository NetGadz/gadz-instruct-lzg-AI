import os
from pathlib import Path
import gradio as gr
import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .config import MODEL_DIR, QWEN_MODEL_DIR, QWEN_MODELS, ROOT, logger
from .llm import answer_in_lezgi
from .search import search_web
from .translator import detect_source_language, translate
from .tts import generate_speech

# FastAPI сервис
api_app = FastAPI(title="LEZGi AI API", version="2.1.0")

api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    text: str
    model: str = "gadz-instruct-lzg · 3B"
    answer_lang: str = "lez_Cyrl"
    online: bool = False
    history: list[dict] = []


class TranslateRequest(BaseModel):
    text: str
    src: str = "auto"
    tgt: str = "lez_Cyrl"


class SpeakRequest(BaseModel):
    text: str
    language: str = "rus"


@api_app.get("/health")
def health_check():
    """Проверка состояния сервиса и доступности GPU."""
    return {
        "status": "ok",
        "cuda": torch.cuda.is_available(),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
    }


@api_app.get("/translator")
def serve_translator_page():
    """Раздача standalone страницы переводчика."""
    html_path = ROOT / "translator.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="Страница translator.html не найдена")


@api_app.post("/api/translate")
def api_translate(req: TranslateRequest):
    """Эндпоинт прямого перевода."""
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Текст для перевода не может быть пустым")

    src = req.src
    tgt = req.tgt
    if src == "auto":
        src = detect_source_language(text)
        tgt = "rus_Cyrl" if src == "lez_Cyrl" else "lez_Cyrl"

    result = translate(text, MODEL_DIR, src_lang=src, tgt_lang=tgt)
    return {"translation": result, "src": src, "tgt": tgt}


@api_app.post("/api/chat")
def api_chat(req: ChatRequest):
    """Эндпоинт чата с ассистентом."""
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Сообщение не может быть пустым")

    model_dir = QWEN_MODELS.get(req.model, QWEN_MODEL_DIR)
    web_context, sources = search_web(text) if req.online else ("", [])
    sources_str = "\n".join(f"[{i}] {s['url']}" for i, s in enumerate(sources, 1))

    _, _, answer = answer_in_lezgi(
        text,
        translator_model_dir=MODEL_DIR,
        qwen_model_dir=model_dir,
        history=req.history,
        answer_lang=req.answer_lang,
        web_context=web_context,
    )
    return {"answer": answer, "sources": sources_str}


@api_app.post("/api/speak")
def api_speak(req: SpeakRequest):
    """Эндпоинт озвучки текста."""
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Текст пустой")

    audio_path = generate_speech(text, req.language)
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=500, detail="Ошибка при генерации аудио")

    return FileResponse(audio_path, media_type="audio/wav")


# Веб-интерфейс Gradio
def _gradio_chat(message, history, model_choice, lang_choice, use_web):
    if not message or not message.strip():
        return history, "", None

    model_dir = QWEN_MODELS.get(model_choice, QWEN_MODEL_DIR)
    target_lang = "rus_Cyrl" if lang_choice == "Русский" else "lez_Cyrl"

    web_context = ""
    sources_md = ""
    if use_web:
        web_context, sources = search_web(message)
        if sources:
            sources_md = "\n\n**Источники:**\n" + "\n".join(
                f"- [{s['title']}]({s['url']})" for s in sources
            )

    normalized = []
    for turn in history:
        if isinstance(turn, dict):
            normalized.append(turn)
        elif isinstance(turn, (list, tuple)) and len(turn) == 2:
            normalized.append({"role": "user", "content": turn[0]})
            normalized.append({"role": "assistant", "content": turn[1]})

    try:
        _, _, answer = answer_in_lezgi(
            message,
            translator_model_dir=MODEL_DIR,
            qwen_model_dir=model_dir,
            history=normalized,
            answer_lang=target_lang,
            web_context=web_context,
        )
    except Exception as err:
        answer = f"Ошибка генерации: {err}"

    full_answer = answer + sources_md
    new_history = list(history)
    new_history.append({"role": "user", "content": message})
    new_history.append({"role": "assistant", "content": full_answer})

    audio_path = generate_speech(answer, target_lang)
    return new_history, "", audio_path


def _gradio_translate(text, direction):
    if not text or not text.strip():
        return "", None

    if direction == "Русский → Лезгинский":
        src, tgt = "rus_Cyrl", "lez_Cyrl"
    elif direction == "Лезгинский → Русский":
        src, tgt = "lez_Cyrl", "rus_Cyrl"
    else:
        src = detect_source_language(text)
        tgt = "rus_Cyrl" if src == "lez_Cyrl" else "lez_Cyrl"

    try:
        res = translate(text, MODEL_DIR, src_lang=src, tgt_lang=tgt)
        audio = generate_speech(res, tgt)
        return res, audio
    except Exception as err:
        return f"Ошибка перевода: {err}", None


def build_gradio_ui():
    """Создаёт Gradio Blocks интерфейс для чата и переводчика."""
    custom_css = """
    .gradio-container { max-width: 1100px !important; margin: auto; }
    .header-box { text-align: center; padding: 20px 0 10px; }
    .header-box h1 { font-size: 2.2rem; font-weight: 700; color: #1e4620; margin-bottom: 4px; }
    .header-box p { color: #5a6b5c; font-size: 1rem; }
    .tab-header { font-size: 1.1rem; font-weight: 600; }
    .action-btn { background-color: #2d6a4f !important; color: white !important; font-weight: 600 !important; }
    .tr-box textarea { font-size: 1.05rem !important; line-height: 1.6 !important; }
    """

    with gr.Blocks(title="LEZGi AI — Лезгинский ИИ и Переводчик") as demo:
        with gr.Column(elem_classes=["header-box"]):
            gr.Markdown("# 🦅 LEZGi AI")
            gr.Markdown("Интеллектуальный русско-лезгинский ассистент и переводчик")

        with gr.Tabs():
            with gr.Tab("💬 Чат-ассистент", elem_classes=["tab-header"]):
                with gr.Row():
                    with gr.Column(scale=4):
                        chatbot = gr.Chatbot(height=480, label="Диалог")
                        with gr.Row():
                            msg_input = gr.Textbox(
                                placeholder="Напишите сообщение на русском или лезгинском (например: 'Фи хабарар ава?')...",
                                label="Ваше сообщение",
                                lines=2,
                                scale=8,
                            )
                            send_btn = gr.Button("Отправить ➤", elem_classes=["action-btn"], scale=2)
                        with gr.Row():
                            clear_btn = gr.Button("🗑️ Очистить диалог", size="sm")
                    with gr.Column(scale=2):
                        gr.Markdown("### ⚙️ Параметры")
                        model_drop = gr.Dropdown(
                            choices=list(QWEN_MODELS.keys()),
                            value="gadz-instruct-lzg · 3B",
                            label="Модель ИИ",
                        )
                        lang_drop = gr.Dropdown(
                            choices=["Лезгинский", "Русский"],
                            value="Лезгинский",
                            label="Язык ответа",
                        )
                        web_box = gr.Checkbox(
                            value=False,
                            label="🌐 Поиск в интернете",
                            info="Находить свежую информацию из сети",
                        )
                        chat_audio = gr.Audio(
                            label="🔊 Озвучка ответа",
                            type="filepath",
                            interactive=False,
                        )
                        examples = gr.Dataset(
                            components=[msg_input],
                            samples=[
                                ["Вуч хабарар ава ваз?"],
                                ["Фи йис я исятна?"],
                                ["Расскажи о лезгинском эпосе Шарвили"],
                                ["Переведи на лезгинский: Желаю крепкого здоровья"],
                            ],
                            label="Примеры вопросов",
                        )

            with gr.Tab("🔄 Переводчик", elem_classes=["tab-header"]):
                with gr.Row():
                    dir_radio = gr.Radio(
                        choices=["Русский → Лезгинский", "Лезгинский → Русский", "Автоопределение"],
                        value="Русский → Лезгинский",
                        label="Направление перевода",
                    )
                with gr.Row():
                    with gr.Column():
                        tr_src = gr.Textbox(
                            label="Исходный текст",
                            placeholder="Введите текст для перевода...",
                            lines=8,
                            elem_classes=["tr-box"],
                        )
                    with gr.Column():
                        tr_tgt = gr.Textbox(
                            label="Перевод",
                            placeholder="Здесь появится готовый перевод...",
                            lines=8,
                            interactive=False,
                            elem_classes=["tr-box"],
                        )
                with gr.Row():
                    tr_btn = gr.Button("⚡ Перевести", elem_classes=["action-btn"], scale=2)
                    tr_clear = gr.Button("Очистить", scale=1)
                with gr.Row():
                    tr_audio = gr.Audio(label="🔊 Озвучить перевод", type="filepath", interactive=False)

                gr.Markdown("#### 💡 Частые фразы:")
                with gr.Row():
                    b1 = gr.Button("Привет, как дела?", size="sm")
                    b2 = gr.Button("Фи хабарар ава?", size="sm")
                    b3 = gr.Button("Спасибо большое", size="sm")
                    b4 = gr.Button("Сагърай", size="sm")
                    b5 = gr.Button("Пакаман хийирар", size="sm")

        send_btn.click(_gradio_chat, inputs=[msg_input, chatbot, model_drop, lang_drop, web_box], outputs=[chatbot, msg_input, chat_audio])
        msg_input.submit(_gradio_chat, inputs=[msg_input, chatbot, model_drop, lang_drop, web_box], outputs=[chatbot, msg_input, chat_audio])
        clear_btn.click(lambda: ([], "", None), outputs=[chatbot, msg_input, chat_audio])
        examples.click(lambda x: x[0], inputs=[examples], outputs=[msg_input])

        tr_btn.click(_gradio_translate, inputs=[tr_src, dir_radio], outputs=[tr_tgt, tr_audio])
        tr_clear.click(lambda: ("", "", None), outputs=[tr_src, tr_tgt, tr_audio])
        b1.click(lambda: "Привет, как дела?", outputs=[tr_src])
        b2.click(lambda: "Фи хабарар ава?", outputs=[tr_src])
        b3.click(lambda: "Спасибо большое", outputs=[tr_src])
        b4.click(lambda: "Сагърай", outputs=[tr_src])
        b5.click(lambda: "Пакаман хийирар", outputs=[tr_src])

    return demo


# Интеграция Gradio в FastAPI
demo = build_gradio_ui()
app = gr.mount_gradio_app(api_app, demo, path="/")
