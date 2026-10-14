import re
from pathlib import Path
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from .config import MODEL_DIR, ensure_models_downloaded, logger

# Кэш загруженных моделей перевода в памяти
_NLLB_CACHE = {}

# Характерные лезгинские диграфы и буквы
LEZGI_MARKERS = (
    "гь", "къ", "кӀ", "пӀ", "тӀ", "чӀ", "хъ", "хь", "уь", "юь", "цӀ", "гъ", "дз", "дж", "ə", "ä"
)

# Базовый словарь частотных лезгинских слов
LEZGI_CORE_WORDS = {
    "вуч", "вуна", "заз", "ваз", "ава", "авач", "аватlа", "аватӀа", "фи", "йис", "исятна", "вун",
    "чун", "куьн", "абур", "лагьай", "лугьуз", "жеда", "жедани", "буюр", "къвезва", "фена", "хъфена",
    "кlанда", "кӀанда", "кlанзава", "кӀанзава", "чан", "стха", "вах", "диде", "буба", "бажи", "хва",
    "руш", "хабар", "хабарар", "кlвал", "кӀвал", "рекь", "гъил", "виш", "агъзур", "гьикl", "гьикӀ",
    "гьикьван", "гьиниз", "гьина", "вучиз", "вужар", "сад", "кьвед", "пуд", "кьуд", "вад", "ругуд",
    "ирид", "муьжуьд", "кlуьд", "кӀуьд", "цlуд", "цӀуд", "гьагь", "гьава", "эхь", "ваъ", "пара",
    "тlимил", "тӀимил", "мани", "чир", "ша", "югъ", "йиф", "гаф", "гафар", "чи", "зи", "ви", "куь",
    "квез", "чаз", "за", "ада", "адаз", "иниз", "аниз", "инра", "анра", "акl", "акӀ", "гьакl", "гьакӀ",
    "зани", "вани", "зун", "аш", "фу", "яд", "цlай", "цӀай", "къван", "накь", "пака", "къе"
}

# Частотные русские маркеры для разделения языков
RUSSIAN_CORE_WORDS = {
    "привет", "здравствуйте", "пожалуйста", "спасибо", "почему", "зачем", "когда", "сколько",
    "сейчас", "сегодня", "завтра", "вчера", "помоги", "расскажи", "объясни", "переведи",
    "напиши", "сделай", "какой", "какая", "какое", "какие", "который", "только", "может",
    "можно", "нужно", "надо", "очень", "хорошо", "плохо", "человек", "время", "правда",
    "вопрос", "ответ", "что", "это", "как", "где", "куда", "откуда", "кто", "меня",
    "тебя", "его", "ее", "нас", "вас", "их", "мне", "тебе", "ему", "ей", "нам", "вам",
    "им", "быть", "будет", "было", "если", "хотя", "чтобы", "тоже", "также", "все", "всё"
}

RUSSIAN_SUFFIXES = ("ться", "тся", "ому", "ему", "ыми", "ими", "ость", "ение", "ание", "ющий", "вшего")


def normalize_lezgi_text(text: str) -> str:
    """Приводит различные варианты написания палочки (1, I, l, !) к стандартной кириллической 'Ӏ'."""
    if not text:
        return ""
    return re.sub(r"([кптчцгхКПТЧЦГХ](?:ъ|ь)?)[1!Ilӏ]", r"\1Ӏ", text)


def detect_source_language(text: str) -> str:
    """Определяет язык входного текста (lez_Cyrl или rus_Cyrl)."""
    if not text or not text.strip():
        return "rus_Cyrl"

    normalized = normalize_lezgi_text(text).lower()

    # Специфичные буквы русского языка, отсутствующие в лезгинской графике
    if "ы" in normalized or "ё" in normalized:
        return "rus_Cyrl"

    words = set(re.findall(r"[а-яёӀə]+", normalized))

    lezgi_score = 0
    russian_score = 0

    # Оценка по диграфам
    for marker in LEZGI_MARKERS:
        lezgi_score += normalized.count(marker) * 2

    # Оценка по лексике и грамматическим окончаниям
    for word in words:
        if word in LEZGI_CORE_WORDS:
            lezgi_score += 3
        if word in RUSSIAN_CORE_WORDS:
            russian_score += 3
        if any(word.endswith(sfx) for sfx in RUSSIAN_SUFFIXES):
            russian_score += 2

    if lezgi_score > russian_score:
        return "lez_Cyrl"
    elif russian_score > lezgi_score:
        return "rus_Cyrl"

    if any(marker in normalized for marker in LEZGI_MARKERS):
        return "lez_Cyrl"

    return "rus_Cyrl"


def _clean_translation(text: str, src_lang: str, tgt_lang: str) -> str:
    """Удаляет латинские артефакты и случайные пробелы из вывода NLLB."""
    if not text:
        return ""
    if tgt_lang in ("lez_Cyrl", "rus_Cyrl"):
        cleaned_tokens = []
        for token in text.split():
            stripped = re.sub(r"[^\w]", "", token)
            if not stripped:
                cleaned_tokens.append(token)
                continue
            latin_chars = sum(1 for ch in stripped if "a" <= ch.lower() <= "z")
            if latin_chars > len(stripped) * 0.5 and len(stripped) > 1:
                continue
            cleaned_tokens.append(token)
        text = " ".join(cleaned_tokens)
        text = re.sub(r"  +", " ", text).strip()
    return text


def load_nllb(model_dir: Path | str = MODEL_DIR):
    """Загружает или достаёт из кэша модель NLLB для перевода."""
    model_key = str(Path(model_dir).resolve())
    if model_key in _NLLB_CACHE:
        return _NLLB_CACHE[model_key]

    ensure_models_downloaded()
    logger.info("Загрузка модели перевода из %s...", model_dir)
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    model = AutoModelForSeq2SeqLM.from_pretrained(str(model_dir))

    if torch.cuda.is_available():
        model.to("cuda")
    model.eval()

    _NLLB_CACHE[model_key] = (tokenizer, model)
    return _NLLB_CACHE[model_key]


def translate(
    text: str,
    model_dir: Path | str = MODEL_DIR,
    src_lang: str = "rus_Cyrl",
    tgt_lang: str = "lez_Cyrl",
    max_length: int = 256,
) -> str:
    """Переводит текст между русским и лезгинским языками с помощью NLLB."""
    if not text or not text.strip():
        return ""

    text = normalize_lezgi_text(text.strip())
    tokenizer, model = load_nllb(model_dir)

    tokenizer.src_lang = src_lang
    tokenizer.tgt_lang = tgt_lang
    tokenizer.set_src_lang_special_tokens(src_lang)

    # Разбиваем длинный текст на предложения для предотвращения обрезания
    chunks = [text] if len(text) < 300 else re.split(r"(?<=[.!?\n])\s+", text)
    translated_chunks = []
    device = next(model.parameters()).device

    for chunk in chunks:
        if not chunk.strip():
            continue
        inputs = tokenizer(chunk, return_tensors="pt", truncation=True, max_length=512)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.inference_mode():
            generated = model.generate(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                forced_bos_token_id=tokenizer.convert_tokens_to_ids(tgt_lang),
                max_length=max_length,
                num_beams=4,
                no_repeat_ngram_size=4,
                length_penalty=1.0,
            )
        res = tokenizer.decode(generated[0], skip_special_tokens=True).strip()
        cleaned = _clean_translation(res, src_lang, tgt_lang)
        if cleaned:
            translated_chunks.append(cleaned)

    return " ".join(translated_chunks)


def translate_mixed_to_russian(text: str, model_dir: Path | str = MODEL_DIR) -> str:
    """Переводит лезгинский или смешанный текст на русский."""
    if detect_source_language(text) == "rus_Cyrl":
        return text
    return translate(text, model_dir, src_lang="lez_Cyrl", tgt_lang="rus_Cyrl")
