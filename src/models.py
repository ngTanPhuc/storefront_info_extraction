from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SearchResult(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""


class ShopInfo(BaseModel):
    source_image: str
    shop_name: str | None = None
    address: str | None = None
    phone_number: str | None = None
    website_links: list[str] = Field(default_factory=list)
    open_hours: str | None = None
    ocr_text: str = ""
    search_results: list[SearchResult] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    enrichment_results: dict[str, Any] = Field(default_factory=dict)

    @field_validator("shop_name", "address", "phone_number", "open_hours", mode="before")
    @classmethod
    def normalize_empty_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return str(value).strip() or None

    @field_validator("website_links", mode="before")
    @classmethod
    def normalize_website_links(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            links: list[str] = []
            for item in value:
                if item is None:
                    continue
                text = str(item).strip()
                if text and text not in links:
                    links.append(text)
            return links
        return []

    @property
    def missing_enrichment_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.phone_number:
            missing.append("phone_number")
        if not self.website_links:
            missing.append("website_links")
        if not self.open_hours:
            missing.append("open_hours")
        return missing

    def business_fields(self) -> dict[str, Any]:
        return {
            "shop_name": self.shop_name,
            "address": self.address,
            "phone_number": self.phone_number,
            "website_links": self.website_links,
            "open_hours": self.open_hours,
        }

    def to_export_row(self) -> dict[str, Any]:
        return {
            "image_name": Path(self.source_image).name,
            "shop_name": self.shop_name,
            "address": self.address,
            "phone_number": self.phone_number,
            "website_links": ", ".join(self.website_links),
            "open_hours": self.open_hours,
        }
