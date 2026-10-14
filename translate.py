#!/usr/bin/env python3
"""LEZGi AI — командный интерфейс и запуск локального сервиса перевода."""

import argparse
import sys
import webbrowser

# Настройка корректного вывода UTF-8 в консоли Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from lezgi.config import logger


def run_cli_translation(text: str, src: str | None = None, tgt: str | None = None):
    """Выполняет быстрый перевод переданного текста в терминале."""
    if not text.strip():
        print("Внимание: передан пустой текст.")
        return

    from lezgi.translator import detect_source_language, translate

    # Автоопределение языков, если не заданы явно
    if not src:
        src = detect_source_language(text)
    if not tgt:
        tgt = "rus_Cyrl" if src == "lez_Cyrl" else "lez_Cyrl"

    print(f"[{src} → {tgt}]")
    result = translate(text, src_lang=src, tgt_lang=tgt)
    print(result)


def start_server(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False):
    """Запускает локальный веб-сервер и API."""
    import uvicorn

    logger.info("Запуск LEZGi AI на http://%s:%d", host, port)
    if open_browser and host in ("127.0.0.1", "localhost"):
        webbrowser.open(f"http://{host}:{port}")

    uvicorn.run("lezgi.server:app", host=host, port=port, log_level="info")


def main():
    parser = argparse.ArgumentParser(
        description="LEZGi AI — локальный русско-лезгинский переводчик и диалоговый ассистент",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python translate.py "Привет, как дела?"
  python translate.py --server
  python translate.py --gui
  python translate.py --text "Фи хабарар ава?" --src lez_Cyrl --tgt rus_Cyrl
        """,
    )
    parser.add_argument("query", nargs="?", default=None, help="Текст для быстрого перевода из командной строки")
    parser.add_argument("--text", type=str, default=None, help="Альтернативный флаг для передачи текста")
    parser.add_argument("--src", type=str, default=None, help="Исходный язык (rus_Cyrl или lez_Cyrl)")
    parser.add_argument("--tgt", type=str, default=None, help="Целевой язык (rus_Cyrl или lez_Cyrl)")
    parser.add_argument("--server", action="store_true", help="Запустить локальный REST API и веб-интерфейс")
    parser.add_argument("--gui", action="store_true", help="Запустить настольный графический интерфейс (Tkinter)")
    parser.add_argument("--host", default="127.0.0.1", help="Хост сервера (по умолчанию: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Порт сервера (по умолчанию: 8765)")

    args = parser.parse_args()
    input_text = args.text or args.query

    if input_text:
        run_cli_translation(input_text, src=args.src, tgt=args.tgt)
    elif args.gui:
        from lezgi.gui import launch_gui
        launch_gui()
    elif args.server:
        start_server(host=args.host, port=args.port, open_browser=False)
    else:
        # По умолчанию без аргументов запускаем веб-сервер и открываем браузер
        start_server(host=args.host, port=args.port, open_browser=True)


if __name__ == "__main__":
    main()
