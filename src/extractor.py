from __future__ import annotations

import json
import logging
import re
from typing import Any

import ollama

from .models import ShopInfo

logger = logging.getLogger(__name__)

INFO_FIELDS = ["shop_name", "address", "phone_number", "website_links", "open_hours"]


class OllamaExtractor:
    def __init__(self, model: str = "qwen3") -> None:
        self.model = model

    def extract_from_ocr(self, ocr_text: str, source_image: str) -> ShopInfo:
        prompt = (
            "Extract business information from storefront OCR text.\n"
            "Return valid JSON only with these exact keys:\n"
            "- shop_name: string or null\n"
            "- address: string or null\n"
            "- phone_number: string or null\n"
            "- website_links: array of strings\n"
            "- open_hours: string or null\n\n"
            "Rules:\n"
            "- Use null for missing scalar fields.\n"
            "- Use [] for missing website_links.\n"
            "- Do not add explanations, markdown, comments, or extra keys.\n\n"
            f"OCR text:\n{ocr_text}"
        )
        data = self._request_json(prompt)
        cleaned = _clean_info_payload(data)
        return ShopInfo(source_image=source_image, ocr_text=ocr_text, **cleaned)

    def extract_missing_from_search(
        self,
        shop_info: ShopInfo,
        search_results_text: str,
        missing_fields: list[str],
    ) -> dict[str, Any]:
        fields = ", ".join(missing_fields)
        prompt = (
            "Use the search results to fill missing business information.\n"
            f"Only extract these missing fields: {fields}.\n"
            "Return valid JSON only with keys for the requested fields.\n"
            "Expected value types:\n"
            "- phone_number: string or null\n"
            "- website_links: array of strings\n"
            "- open_hours: string or null\n\n"
            "Rules:\n"
            "- Do not overwrite known fields.\n"
            "- Use null or [] when a requested field is still missing.\n"
            "- Do not add explanations, markdown, comments, or extra keys.\n\n"
            "Known business information:\n"
            f"shop_name: {shop_info.shop_name}\n"
            f"address: {shop_info.address}\n\n"
            f"Search results:\n{search_results_text}"
        )
        data = self._request_json(prompt)
        cleaned = _clean_info_payload(data)
        return {field: cleaned.get(field) for field in missing_fields}

    def _request_json(self, prompt: str) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You extract business information. Respond with valid JSON only. "
                    "No prose, no markdown, no reasoning."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        content = self._chat(messages)
        parsed = parse_json_response(content)
        if parsed is not None:
            return parsed

        logger.warning("Ollama returned invalid JSON. Attempting one repair pass.")
        repair_messages = [
            {
                "role": "system",
                "content": "Convert the provided text to valid JSON only.",
            },
            {
                "role": "user",
                "content": (
                    "Return valid JSON only. Preserve business information when present.\n\n"
                    f"Text:\n{content}"
                ),
            },
        ]
        repaired = self._chat(repair_messages)
        parsed = parse_json_response(repaired)
        if parsed is not None:
            return parsed

        logger.error("Could not parse valid JSON from Ollama response.")
        return {}

    def _chat(self, messages: list[dict[str, str]]) -> str:
        response = ollama.chat(
            model=self.model,
            messages=messages,
            format="json",
            options={"temperature": 0},
        )
        if isinstance(response, dict):
            message = response.get("message", {})
            return str(message.get("content", ""))
        message = getattr(response, "message", None)
        content = getattr(message, "content", "") if message is not None else ""
        return str(content)


def parse_json_response(content: str) -> dict[str, Any] | None:
    cleaned = _strip_thinking(content).strip()
    candidates = [
        cleaned,
        _strip_markdown_fence(cleaned),
        _extract_first_json_object(cleaned),
    ]

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return parsed[0]

    return None


def _clean_info_payload(data: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for field in INFO_FIELDS:
        cleaned[field] = data.get(field)
    return cleaned


def _strip_thinking(content: str) -> str:
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)


def _strip_markdown_fence(content: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)```", content, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else content


def _extract_first_json_object(content: str) -> str | None:
    start = content.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(content[start:], start=start):
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return content[start : index + 1]

    return None
