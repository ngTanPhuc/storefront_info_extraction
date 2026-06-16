from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from ollama import chat, ResponseError

from .image_utils import prepare_image_for_vlm, validate_prepared_image
from .models import ShopInfo

logger = logging.getLogger(__name__)

VLM_MODEL = "gemma4:latest"

INFO_FIELDS = ["shop_name", "address", "phone_number", "website_links", "open_hours"]

VLM_EXTRACTION_PROMPT = """
You are an information extraction system.

Identify the PRIMARY business shown in the image.

The PRIMARY business is usually:
- the largest storefront sign
- the most visually prominent sign
- the sign closest to the center of the image
- the sign occupying the largest area

Ignore neighboring businesses, advertisements, vehicles, street signs, banners, posters, and background storefronts.

Extract information ONLY for the PRIMARY business.

Return valid JSON only:

{
  "shop_name": null,
  "address": null,
  "phone_number": [],
  "website_links": [],
  "open_hours": null
}

Rules:

1. Return JSON only.
2. Do not hallucinate.
3. Do not use prior knowledge.
4. Extract information only if it is physically visible in the image.
5. If information is not visible, use null or [].
6. Do not combine information from multiple businesses.

shop_name:
- Use the primary business name.
- Prefer the largest and most prominent text.
- Do not use slogans or product descriptions.

address:
- Use the address belonging to the primary business.
- Prefer complete addresses containing street number and street name.

phone_number:
- Extract only phone numbers belonging to the primary business.
- Common labels include ĐT, Điện thoại, Hotline, Tel, Liên hệ, Zalo.
- Return all phone numbers found for the primary business.

website_links:
- Extract only URLs explicitly visible in the image.
- Extract Facebook pages only if visible.
- Do not infer or generate websites.

open_hours:
- Extract only if visible.
- Otherwise return null.
""".strip()

SEARCH_EXTRACTION_PROMPT_TEMPLATE = """
Use the web search results to fill missing business information.

Only extract these missing fields: {missing_fields}.

Use only the selected search results below. Do not infer fields from unrelated results,
generic directory pages, or information outside the provided results.

Return valid JSON only with keys for the requested fields.
Expected value types:
- phone_number: string or null
- website_links: array of strings
- open_hours: string or null

Rules:
- Do not overwrite known fields.
- Use null or [] when a requested field is still missing.
- Do not add explanations, markdown, comments, or extra keys.
- Prefer official sources when the search results include them.

Known business information:
shop_name: {shop_name}
address: {address}

Web search results:
{search_results_text}
""".strip()


class OllamaExtractor:
    def __init__(self, model: str = VLM_MODEL) -> None:
        self.model = model
        self.last_raw_response = ""

    def extract_from_image(self, image_path: Path) -> ShopInfo:
        image_for_model = prepare_image_for_vlm(image_path)
        validate_prepared_image(image_for_model)
        parsed_response = self._request_json(
            prompt=VLM_EXTRACTION_PROMPT,
            image_path=image_for_model,
        )
        cleaned = _clean_info_payload(parsed_response)
        return ShopInfo(
            source_image=str(image_path),
            raw_response=self.last_raw_response,
            **cleaned,
        )

    def extract_missing_from_search(
        self,
        shop_info: ShopInfo,
        search_results_text: str,
        missing_fields: list[str],
    ) -> dict[str, Any]:
        prompt = SEARCH_EXTRACTION_PROMPT_TEMPLATE.format(
            missing_fields=", ".join(missing_fields),
            shop_name=shop_info.shop_name,
            address=shop_info.address,
            search_results_text=search_results_text,
        )
        data = self._request_json(prompt=prompt)
        cleaned = _clean_info_payload(data)
        return {field: cleaned.get(field) for field in missing_fields}

    def _request_json(
        self,
        prompt: str,
        image_path: Path | None = None,
    ) -> dict[str, Any]:
        content = self._chat(prompt=prompt, image_path=image_path)
        self.last_raw_response = content
        parsed = parse_json_response(content)
        if parsed is not None:
            return parsed

        logger.warning("Ollama returned invalid JSON. Attempting one repair pass.")
        repaired = self._chat(
            prompt=(
                "Return valid JSON only. Preserve business information when present.\n\n"
                f"Text:\n{content}"
            ),
        )
        parsed = parse_json_response(repaired)
        if parsed is not None:
            return parsed

        logger.error("Could not parse valid JSON from Ollama response.")
        return {}

    def _chat(self, prompt: str, image_path: Path | None = None) -> str:
        user_content: dict[str, Any] = {"role": "user", "content": prompt}
        if image_path is not None:
            user_content["images"] = [str(image_path)]

        try:
            response = chat(
                model=self.model,
                messages=[user_content],
                format="json",
                options={
                    "temperature": 0,
                    "num_ctx": 8192,
                },
            )
        except ResponseError as e:
            print("Status:", e.status_code)
            print("Error:", e.error)
            raise
        return _extract_chat_content(response)


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


def _extract_chat_content(response: Any) -> str:
    if isinstance(response, dict):
        message = response.get("message", {})
        return str(message.get("content", ""))

    message = getattr(response, "message", None)
    content = getattr(message, "content", "") if message is not None else ""
    return str(content)


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
