from functools import lru_cache
from typing import Any

from app.rag.constants import MODEL_NAME


@lru_cache(maxsize=2)
def load_embedding_model(device: str) -> tuple[Any, Any]:
    from transformers.models.xlm_roberta.modeling_xlm_roberta import XLMRobertaModel
    from transformers.models.xlm_roberta.tokenization_xlm_roberta_fast import (
        XLMRobertaTokenizerFast,
    )

    tokenizer = XLMRobertaTokenizerFast.from_pretrained(MODEL_NAME)
    model = XLMRobertaModel.from_pretrained(MODEL_NAME).to(device)
    model.eval()
    return tokenizer, model


def mean_pool(last_hidden_state: Any, attention_mask: Any) -> Any:
    from torch.nn import functional

    token_mask = attention_mask.unsqueeze(-1).to(last_hidden_state.dtype)
    pooled = (last_hidden_state * token_mask).sum(dim=1)
    pooled = pooled / token_mask.sum(dim=1).clamp(min=1)
    return functional.normalize(pooled, p=2, dim=1)


def embed_texts(
    texts: list[str],
    tokenizer: Any,
    model: Any,
    device: str,
    max_length: int = 512,
) -> Any:
    import torch

    tokens = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    tokens = {key: value.to(device) for key, value in tokens.items()}
    with torch.inference_mode():
        output = model(**tokens)
        return mean_pool(output.last_hidden_state, tokens["attention_mask"])
