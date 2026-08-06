from __future__ import annotations

from typing import Any


def normalize_base_url(base_url: str) -> str:
    """
    将用户填写的 Base URL 规范化为 Chat Completions 完整地址。
    """
    url = base_url.strip()
    if not url:
        return ""

    url = url.rstrip("/")

    if url.endswith("/chat/completions"):
        return url

    if url.endswith("/v1"):
        return f"{url}/chat/completions"

    return f"{url}/v1/chat/completions"


def normalize_models_url(base_url: str) -> str:
    """
    将用户填写的 Base URL 规范化为模型列表地址。
    """
    url = base_url.strip()
    if not url:
        return ""

    url = url.rstrip("/")

    if url.endswith("/models"):
        return url

    if url.endswith("/chat/completions"):
        return f"{url[: -len('/chat/completions')]}/models"

    if url.endswith("/v1"):
        return f"{url}/models"

    return f"{url}/v1/models"


def extract_model_names(data: Any) -> list[str]:
    """
    从 /v1/models 风格（含常见变体）的响应中提取模型名称列表。
    """
    model_names: list[str] = []

    if isinstance(data, dict):
        items = data.get("data")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    model_id = item.get("id") or item.get("name")
                    if isinstance(model_id, str) and model_id.strip():
                        model_names.append(model_id.strip())
                elif isinstance(item, str) and item.strip():
                    model_names.append(item.strip())

        items = data.get("models")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    model_id = item.get("id") or item.get("name")
                    if isinstance(model_id, str) and model_id.strip():
                        model_names.append(model_id.strip())
                elif isinstance(item, str) and item.strip():
                    model_names.append(item.strip())

    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                model_id = item.get("id") or item.get("name")
                if isinstance(model_id, str) and model_id.strip():
                    model_names.append(model_id.strip())
            elif isinstance(item, str) and item.strip():
                model_names.append(item.strip())

    return sorted(set(model_names), key=str.lower)
