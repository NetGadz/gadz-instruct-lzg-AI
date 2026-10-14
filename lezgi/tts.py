import tempfile
import wave
from pathlib import Path
import soundfile as sf
import torch
from transformers import AutoTokenizer, VitsModel
from piper import PiperVoice

from .config import LEZGI_TTS_DIR, PIPER_MODEL_PATH, ensure_models_downloaded, logger

_TTS_CACHE = {}


def load_tts(language: str):
    """Инициализирует и возвращает модель синтеза речи для выбранного языка."""
    if language in _TTS_CACHE:
        return _TTS_CACHE[language]

    ensure_models_downloaded()

    if language in ("lez_Cyrl", "lez"):
        logger.info("Загрузка лезгинского TTS (VITS)...")
        tokenizer = AutoTokenizer.from_pretrained(str(LEZGI_TTS_DIR), local_files_only=True)
        model = VitsModel.from_pretrained(str(LEZGI_TTS_DIR), local_files_only=True)
        model.eval()
        tts_obj = ("vits", tokenizer, model, 16000)
    else:
        logger.info("Загрузка русского TTS (Piper)...")
        voice = PiperVoice.load(str(PIPER_MODEL_PATH))
        tts_obj = ("piper", voice, None, 22050)

    _TTS_CACHE[language] = tts_obj
    return tts_obj


def generate_speech(text: str, language: str = "rus") -> str | None:
    """Генерирует аудио речи и возвращает путь к временному .wav файлу."""
    if not text or not text.strip():
        return None

    try:
        tts = load_tts(language)
        temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_path = temp_file.name
        temp_file.close()

        engine_type = tts[0]
        if engine_type == "piper":
            voice = tts[1]
            with wave.open(temp_path, "wb") as wav_out:
                voice.synthesize_wav(text, wav_out)
            return temp_path
        elif engine_type == "vits":
            _, tokenizer, model, sample_rate = tts
            inputs = tokenizer(text, return_tensors="pt")
            with torch.inference_mode():
                waveform = model(**inputs).waveform[0].cpu().numpy()
            sf.write(temp_path, waveform, sample_rate)
            return temp_path

    except Exception as err:
        logger.error("Ошибка при синтезе речи (%s): %s", language, err)
        return None
