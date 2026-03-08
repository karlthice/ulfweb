"""Build LLM request payloads adapted for llamacpp or vllm backends."""

from backend.config import settings


def build_llm_payload(
    messages: list[dict],
    *,
    temperature: float = 0.7,
    top_k: int = 40,
    top_p: float = 0.9,
    repeat_penalty: float = 1.1,
    max_tokens: int = 2048,
    stream: bool = True,
) -> dict:
    """Build a /v1/chat/completions payload appropriate for the configured backend.

    llamacpp: sends repeat_penalty, top_k, reasoning_budget
    vllm:     sends repetition_penalty, top_k, omits reasoning_budget
    """
    llm_type = settings.llama.type

    payload = {
        "messages": messages,
        "stream": stream,
        "temperature": temperature,
        "top_k": top_k,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }

    if llm_type == "vllm":
        payload["repetition_penalty"] = repeat_penalty
    else:
        # llamacpp (default)
        payload["repeat_penalty"] = repeat_penalty
        payload["reasoning_budget"] = 0

    return payload
