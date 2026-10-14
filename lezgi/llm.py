import threading
from pathlib import Path
import torch
from transformers import (
    AutoConfig,
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TextIteratorStreamer,
)

from .config import (
    DEFAULT_SYSTEM_PROMPT,
    MODEL_DIR,
    QWEN_MODEL_DIR,
    QWEN_MODEL_ID,
    ensure_models_downloaded,
    logger,
)
from .translator import detect_source_language, translate, translate_mixed_to_russian

_QWEN_CACHE = {}


def load_qwen(model_dir: Path | str = QWEN_MODEL_DIR):
    """Загружает или достаёт из кэша модель Qwen."""
    model_key = str(Path(model_dir).resolve())
    if model_key in _QWEN_CACHE:
        return _QWEN_CACHE[model_key]

    ensure_models_downloaded()
    local_model = Path(model_dir)
    has_local_weights = (
        (local_model / "model.safetensors").exists()
        or (local_model / "model.safetensors.index.json").exists()
    )
    model_path = str(local_model) if has_local_weights else QWEN_MODEL_ID

    logger.info("Загрузка языковой модели из %s...", model_path)
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    if torch.cuda.is_available():
        try:
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
            )
            model = AutoModelForCausalLM.from_pretrained(
                model_path,
                quantization_config=bnb_config,
                device_map={"": 0},
                low_cpu_mem_usage=True,
            )
        except Exception as err:
            logger.warning("Не удалось загрузить в 4-bit (%s), переключаемся на float16...", err)
            model = AutoModelForCausalLM.from_pretrained(
                model_path,
                torch_dtype=torch.float16,
                device_map="auto",
                low_cpu_mem_usage=True,
            )
    else:
        logger.info("CUDA недоступна, запуск на CPU (может работать медленнее)...")
        config = AutoConfig.from_pretrained(model_path)
        config.quantization_config = None
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            config=config,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True,
            attn_implementation="sdpa",
        )
        model.to("cpu")

    model.eval()
    _QWEN_CACHE[model_key] = (tokenizer, model)
    return _QWEN_CACHE[model_key]


def _build_messages(text: str, history: list[dict] | None = None) -> list[dict]:
    """Формирует список сообщений для chat_template с сохранением контекста."""
    messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-6:])
    messages.append({"role": "user", "content": text})
    return messages


def ask_qwen(
    text: str,
    model_dir: Path | str = QWEN_MODEL_DIR,
    history: list[dict] | None = None,
    max_new_tokens: int = 512,
) -> str:
    """Генерирует ответ LLM на основе вопроса и контекста диалога."""
    tokenizer, model = load_qwen(model_dir)
    messages = _build_messages(text, history)

    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.inference_mode():
        generated = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.6,
            top_p=0.85,
            top_k=30,
            repetition_penalty=1.15,
            use_cache=True,
        )

    # Декодируем только новые сгенерированные токены
    new_tokens = generated[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def stream_qwen(
    text: str,
    model_dir: Path | str = QWEN_MODEL_DIR,
    history: list[dict] | None = None,
    on_token=None,
    max_new_tokens: int = 512,
) -> str:
    """Потоковая генерация ответа через TextIteratorStreamer."""
    tokenizer, model = load_qwen(model_dir)
    messages = _build_messages(text, history)

    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}

    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
    generation_kwargs = dict(
        **inputs,
        streamer=streamer,
        max_new_tokens=max_new_tokens,
        do_sample=True,
        temperature=0.6,
        top_p=0.85,
        top_k=30,
        repetition_penalty=1.15,
        use_cache=True,
    )

    worker_thread = threading.Thread(target=model.generate, kwargs=generation_kwargs, daemon=True)
    worker_thread.start()

    collected = []
    for token in streamer:
        collected.append(token)
        if on_token:
            on_token(token)

    worker_thread.join()
    return "".join(collected).strip()


def answer_in_lezgi(
    text: str,
    translator_model_dir: Path | str = MODEL_DIR,
    qwen_model_dir: Path | str = QWEN_MODEL_DIR,
    history: list[dict] | None = None,
    answer_lang: str = "lez_Cyrl",
    web_context: str = "",
) -> tuple[str, str, str]:
    """Основной пайплайн: входной текст -> перевод в RU -> ответ LLM -> перевод в целевой язык."""
    src_lang = detect_source_language(text)
    russian_question = text if src_lang == "rus_Cyrl" else translate_mixed_to_russian(text, translator_model_dir)

    model_input = russian_question
    if web_context:
        model_input += (
            "\n\nСвежие сведения из интернета для справки. Используй их для точного ответа:\n"
            + web_context
        )

    russian_answer = ask_qwen(model_input, qwen_model_dir, history)

    final_answer = (
        russian_answer
        if answer_lang == "rus_Cyrl"
        else translate(russian_answer, translator_model_dir, src_lang="rus_Cyrl", tgt_lang=answer_lang)
    )

    return russian_question, russian_answer, final_answer
