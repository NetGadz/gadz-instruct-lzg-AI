import logging
import os
from pathlib import Path

# Базовые пути проекта
ROOT = Path(__file__).resolve().parent.parent

# Пути к локальным моделям
MODEL_DIR = ROOT / "lezgi-nllb-600m-200k-syntetics"
QWEN_MODEL_DIR = ROOT / "models" / "gadz-instruct-lzg-4bit"
QWEN_8B_DIR = ROOT / "models" / "gadz1-8b"
QWEN_MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"

# Модели озвучки
LEZGI_TTS_DIR = ROOT / "models" / "vits-lez-tts"
PIPER_MODEL_PATH = ROOT / "models" / "piper-ru" / "ru_RU-denis-medium.onnx"

# Доступные варианты LLM
QWEN_MODELS = {
    "gadz-instruct-lzg · 3B": QWEN_MODEL_DIR,
    "gadz1-8b · 8B": QWEN_8B_DIR,
}

# Системный промпт для ассистента
DEFAULT_SYSTEM_PROMPT = (
    "Ты — LEZGi AI, доброжелательный и эрудированный русско-лезгинский ассистент. "
    "Твоя задача — помогать пользователю, отвечать на вопросы, переводить фразы и "
    "поддерживать живой разговор на русском и лезгинском языках. "
    "Ты уважительно относишься к культуре, истории и традициям лезгинского народа. "
    "Отвечай грамотно, вежливо и по существу на русском языке (при необходимости ответ будет переведён)."
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("lezgi")


def ensure_models_downloaded():
    """Проверяет наличие локальных весов и при необходимости скачивает их с Hugging Face."""
    if not MODEL_DIR.exists() or not (MODEL_DIR / "config.json").exists():
        logger.info("Модели не найдены локально. Начинаем загрузку с Hugging Face Hub...")
        try:
            from huggingface_hub import snapshot_download

            snapshot_download(
                repo_id="gadz777/gadz-instruct-lzg-models",
                repo_type="model",
                local_dir=str(ROOT),
                allow_patterns=["models/**", "lezgi-nllb-600m-200k-syntetics/**"],
                ignore_patterns=["**/.cache/**", "**/checkpoint/**"],
            )
            logger.info("Загрузка моделей завершена успешно.")
        except Exception as err:
            logger.warning("Не удалось автоматически загрузить модели: %s", err)
