"""NLLB-200 segment translation (CPU, lazy-loaded)."""

from __future__ import annotations

from functools import lru_cache

from declarations.models import SourceLanguage

_NLLB_TAG: dict[SourceLanguage, tuple[str, str]] = {
    SourceLanguage.es: ("spa_Latn", "eng_Latn"),
    SourceLanguage.zh: ("zho_Hans", "eng_Latn"),
    SourceLanguage.fr: ("fra_Latn", "eng_Latn"),
    SourceLanguage.ht: ("hat_Latn", "eng_Latn"),
    SourceLanguage.ti: ("tir_Ethi", "eng_Latn"),
    SourceLanguage.prs: ("pes_Arab", "eng_Latn"),
}

_MODEL_ID = "facebook/nllb-200-distilled-600M"


@lru_cache(maxsize=1)
def _load_pipeline() -> tuple[object, object, str]:
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(_MODEL_ID)  # type: ignore[no-untyped-call]
    model = AutoModelForSeq2SeqLM.from_pretrained(_MODEL_ID)
    try:
        import transformers

        version = getattr(transformers, "__version__", "unknown")
    except ImportError:
        version = "unknown"
    return (
        tokenizer,
        model,
        f"nllb-200-distilled-600M@transformers-{version}",
    )


def _translate_one(
    text: str,
    src_tag: str,
    tgt_tag: str,
    tokenizer: object,
    model: object,
) -> str:
    tok = tokenizer
    mdl = model
    setattr(tok, "src_lang", src_tag)
    inputs = tok(text, return_tensors="pt", truncation=True)  # type: ignore[operator]
    tgt_id = tok.convert_tokens_to_ids(tgt_tag)  # type: ignore[attr-defined]
    generated = mdl.generate(  # type: ignore[attr-defined]
        **inputs,
        forced_bos_token_id=tgt_id,
        max_length=512,
    )
    out = tok.batch_decode(generated, skip_special_tokens=True)  # type: ignore[attr-defined]
    return str(out[0]).strip()


def translate_texts(
    texts: list[str],
    source_language: SourceLanguage,
) -> tuple[list[str], str]:
    if not texts:
        tokenizer, _model, model_version = _load_pipeline()
        del tokenizer
        return [], model_version
    src_tag, tgt_tag = _NLLB_TAG[source_language]
    tokenizer, model, model_version = _load_pipeline()
    translations = [
        _translate_one(text, src_tag, tgt_tag, tokenizer, model) for text in texts
    ]
    return translations, model_version
