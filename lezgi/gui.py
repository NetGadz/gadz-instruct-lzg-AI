import threading
import tkinter as tk
from tkinter import ttk

from .config import MODEL_DIR, QWEN_MODELS, QWEN_MODEL_DIR, logger
from .llm import ask_qwen, stream_qwen
from .search import search_web
from .translator import detect_source_language, translate, translate_mixed_to_russian
from .tts import generate_speech


class LezgiGuiApp:
    """Десктопный интерфейс на Tkinter для прямого общения с моделью."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("LEZGi AI — Лезгинский ассистент")
        self.root.geometry("1100x720")
        self.root.minsize(720, 500)
        self.root.configure(bg="#1f2321")

        self.history = []
        self.last_bot_answer = ""
        self.is_busy = False

        self._init_styles()
        self._build_layout()

    def _init_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("App.TFrame", background="#1f2321")
        style.configure("Sidebar.TFrame", background="#171918")
        style.configure("Title.TLabel", background="#171918", foreground="#f4f4f4", font=("Segoe UI", 14, "bold"))
        style.configure("Subtitle.TLabel", background="#171918", foreground="#8a928c", font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#1f2321", foreground="#8a928c", font=("Segoe UI", 9))
        style.configure("SideBtn.TButton", background="#171918", foreground="#d0d6d2", borderwidth=0, padding=(10, 8))
        style.map("SideBtn.TButton", background=[("active", "#252b27")])
        style.configure("Primary.TButton", background="#2d6a4f", foreground="#ffffff", borderwidth=0, padding=(10, 6))
        style.map("Primary.TButton", background=[("active", "#367d5e")])

    def _build_layout(self):
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        # Боковая панель
        sidebar = ttk.Frame(self.root, width=220, style="Sidebar.TFrame", padding=(16, 16))
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        ttk.Label(sidebar, text="LEZGi AI", style="Title.TLabel").pack(anchor="w")
        ttk.Label(sidebar, text="Локальный ассистент", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 20))

        ttk.Button(sidebar, text="＋  Новый чат", style="SideBtn.TButton", command=self.clear_chat).pack(fill="x", pady=(0, 10))

        ttk.Label(sidebar, text="Модель:", style="Subtitle.TLabel").pack(anchor="w", pady=(10, 2))
        self.model_var = tk.StringVar(value=list(QWEN_MODELS.keys())[0])
        self.model_combo = ttk.Combobox(sidebar, textvariable=self.model_var, values=list(QWEN_MODELS.keys()), state="readonly")
        self.model_combo.pack(fill="x", pady=(0, 10))

        ttk.Label(sidebar, text="Язык ответа:", style="Subtitle.TLabel").pack(anchor="w", pady=(5, 2))
        self.lang_var = tk.StringVar(value="Лезгинский")
        self.lang_combo = ttk.Combobox(sidebar, textvariable=self.lang_var, values=["Лезгинский", "Русский"], state="readonly")
        self.lang_combo.pack(fill="x", pady=(0, 10))

        self.web_var = tk.BooleanVar(value=False)
        self.web_check = ttk.Checkbutton(sidebar, text="Поиск в интернете", variable=self.web_var)
        self.web_check.pack(anchor="w", pady=(5, 10))

        self.speak_btn = ttk.Button(sidebar, text="🔊 Озвучить ответ", style="SideBtn.TButton", command=self.speak_last, state="disabled")
        self.speak_btn.pack(fill="x", pady=(10, 0))

        # Основная зона диалога
        main_frame = ttk.Frame(self.root, style="App.TFrame", padding=(16, 16))
        main_frame.grid(row=0, column=1, sticky="nsew")
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        # Поле вывода сообщений
        self.chat_display = tk.Text(
            main_frame,
            wrap="word",
            bg="#262b28",
            fg="#e6eae7",
            insertbackground="#ffffff",
            font=("Segoe UI", 10),
            padx=12,
            pady=12,
            relief="flat",
        )
        self.chat_display.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.chat_display.configure(state="disabled")

        self.chat_display.tag_configure("user", foreground="#78c2ad", font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_configure("bot", foreground="#e6eae7")
        self.chat_display.tag_configure("info", foreground="#8a928c", font=("Segoe UI", 9, "italic"))

        # Нижняя панель ввода
        bottom_box = ttk.Frame(main_frame, style="App.TFrame")
        bottom_box.grid(row=1, column=0, sticky="ew")
        bottom_box.grid_columnconfigure(0, weight=1)

        self.input_entry = ttk.Entry(bottom_box, font=("Segoe UI", 10))
        self.input_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10), ipady=6)
        self.input_entry.bind("<Return>", lambda e: self.send_message())

        self.send_btn = ttk.Button(bottom_box, text="Отправить", style="Primary.TButton", command=self.send_message)
        self.send_btn.grid(row=0, column=1)

        self.status_var = tk.StringVar(value="Готов к работе")
        ttk.Label(main_frame, textvariable=self.status_var, style="Status.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 0))

    def append_text(self, sender: str, text: str, tag: str = "bot"):
        self.chat_display.configure(state="normal")
        if sender:
            self.chat_display.insert("end", f"{sender}:\n", tag)
        self.chat_display.insert("end", f"{text}\n\n", tag)
        self.chat_display.see("end")
        self.chat_display.configure(state="disabled")

    def clear_chat(self):
        if self.is_busy:
            return
        self.history.clear()
        self.last_bot_answer = ""
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        self.chat_display.configure(state="disabled")
        self.speak_btn.configure(state="disabled")
        self.status_var.set("Диалог очищен")

    def send_message(self):
        text = self.input_entry.get().strip()
        if not text or self.is_busy:
            return

        self.input_entry.delete(0, "end")
        self.append_text("Вы", text, "user")
        self.history.append({"role": "user", "content": text})

        self.is_busy = True
        self.send_btn.configure(state="disabled")
        self.speak_btn.configure(state="disabled")
        self.status_var.set("Думаю...")

        selected_model = QWEN_MODELS.get(self.model_var.get(), QWEN_MODEL_DIR)
        want_lezgi = self.lang_var.get() == "Лезгинский"
        use_online = self.web_var.get()

        threading.Thread(
            target=self._worker_process,
            args=(text, selected_model, want_lezgi, use_online),
            daemon=True,
        ).start()

    def _worker_process(self, user_text: str, model_dir, want_lezgi: bool, use_online: bool):
        try:
            # Веб-поиск при необходимости
            web_context = ""
            if use_online:
                self.root.after(0, lambda: self.status_var.set("Поиск в интернете..."))
                web_context, _ = search_web(user_text)

            # Перевод входящего сообщения на русский для LLM
            self.root.after(0, lambda: self.status_var.set("Обработка запроса..."))
            src_lang = detect_source_language(user_text)
            ru_question = user_text if src_lang == "rus_Cyrl" else translate_mixed_to_russian(user_text, MODEL_DIR)

            model_input = ru_question
            if web_context:
                model_input += "\n\nКонтекст из интернета:\n" + web_context

            self.root.after(0, lambda: self.status_var.set("Генерация ответа..."))
            ru_answer = ask_qwen(model_input, model_dir, self.history[:-1])

            # Перевод на лезгинский, если требуется
            if want_lezgi:
                self.root.after(0, lambda: self.status_var.set("Перевод на лезгинский..."))
                final_answer = translate(ru_answer, MODEL_DIR, src_lang="rus_Cyrl", tgt_lang="lez_Cyrl")
            else:
                final_answer = ru_answer

            self.last_bot_answer = final_answer
            self.history.append({"role": "assistant", "content": final_answer})

            # Отображение готового ответа без искусственной задержки
            self.root.after(0, lambda: self._on_answer_ready(final_answer))

        except Exception as err:
            logger.error("Ошибка в диалоге: %s", err)
            self.root.after(0, lambda: self._on_error(str(err)))

    def _on_answer_ready(self, answer: str):
        self.append_text("Ассистент", answer, "bot")
        self.is_busy = False
        self.send_btn.configure(state="normal")
        self.speak_btn.configure(state="normal")
        self.status_var.set("Готов к работе")

    def _on_error(self, err_msg: str):
        self.append_text("Система", f"Ошибка: {err_msg}", "info")
        self.is_busy = False
        self.send_btn.configure(state="normal")
        self.status_var.set("Произошла ошибка")

    def speak_last(self):
        if not self.last_bot_answer:
            return
        lang = "lez_Cyrl" if self.lang_var.get() == "Лезгинский" else "rus"
        self.status_var.set("Озвучивание...")

        def _tts():
            path = generate_speech(self.last_bot_answer, lang)
            if path:
                try:
                    import winsound
                    winsound.PlaySound(path, winsound.SND_FILENAME)
                except Exception as err:
                    logger.debug("Воспроизведение звука: %s", err)
            self.root.after(0, lambda: self.status_var.set("Готов к работе"))

        threading.Thread(target=_tts, daemon=True).start()


def launch_gui():
    """Запускает графический интерфейс Tkinter."""
    root = tk.Tk()
    app = LezgiGuiApp(root)
    root.mainloop()
