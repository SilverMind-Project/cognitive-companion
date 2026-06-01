"""Service-layer enrichment for Person Hypothesis BFF responses."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from backend.services.cts._types import IdentityLookupClient

ImageUrlFactory = Callable[[str], str | None]


class PHEnrichmentService:
    """Apply UI-facing names and presigned URLs to PH payload dictionaries."""

    def __init__(self, identity_client: IdentityLookupClient) -> None:
        self._identity_client = identity_client

    async def identity_display_names(self) -> dict[str, str]:
        identities = await self._identity_client.get_identities(active_only=True)
        names: dict[str, str] = {}
        for identity in identities:
            identity_id = identity.get("identity_id")
            if not isinstance(identity_id, str) or not identity_id:
                continue
            display_name = identity.get("display_name") or identity.get("name") or identity_id
            names[identity_id] = str(display_name)
        return names

    async def enrich_phs(
        self,
        items: Iterable[dict[str, Any]],
        *,
        image_url: ImageUrlFactory | None = None,
    ) -> list[dict[str, Any]]:
        display_names = await self.identity_display_names()
        return [
            self._apply_ph_enrichment(dict(item), display_names, image_url=image_url)
            for item in items
        ]

    async def enrich_ph(
        self,
        item: dict[str, Any],
        *,
        display_names: dict[str, str] | None = None,
        image_url: ImageUrlFactory | None = None,
    ) -> dict[str, Any]:
        names = display_names if display_names is not None else await self.identity_display_names()
        return self._apply_ph_enrichment(dict(item), names, image_url=image_url)

    def enrich_co_present(
        self,
        items: Iterable[dict[str, Any]],
        *,
        display_names: dict[str, str],
    ) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for item in items:
            payload = self._apply_identity_name(dict(item), display_names)
            self._apply_room_fields(payload)
            enriched.append(payload)
        return enriched

    def enrich_keyframes(
        self,
        items: Iterable[dict[str, Any]],
        *,
        image_url: ImageUrlFactory,
    ) -> list[dict[str, Any]]:
        return [self._apply_keyframe_urls(dict(item), image_url=image_url) for item in items]

    def _apply_ph_enrichment(
        self,
        item: dict[str, Any],
        display_names: dict[str, str],
        *,
        image_url: ImageUrlFactory | None,
    ) -> dict[str, Any]:
        self._apply_identity_name(item, display_names)
        self._apply_room_fields(item)
        if image_url is not None:
            self._apply_latest_keyframe_urls(item, image_url=image_url)
        posterior_prob = item.get("posterior_top_prob")
        if posterior_prob is not None:
            item["posterior_top_prob"] = float(posterior_prob)
        return item

    def _apply_identity_name(
        self,
        item: dict[str, Any],
        display_names: dict[str, str],
    ) -> dict[str, Any]:
        identity_id = item.get("current_identity_id") or item.get("identity_id")
        if isinstance(identity_id, str) and identity_id:
            item["identity_display_name"] = display_names.get(identity_id, identity_id)
        return item

    def _apply_room_fields(self, item: dict[str, Any]) -> None:
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        room_id = item.get("room_id") or metadata.get("last_room_id") or metadata.get("room_id")
        room_name = (
            item.get("room_name")
            or metadata.get("last_room_name")
            or metadata.get("room_name")
            or room_id
        )
        if room_id:
            item["room_id"] = str(room_id)
        if room_name:
            item["room_name"] = str(room_name)

    def _apply_latest_keyframe_urls(
        self,
        item: dict[str, Any],
        *,
        image_url: ImageUrlFactory,
    ) -> None:
        minio_key = item.get("latest_keyframe_minio_key")
        if isinstance(minio_key, str) and minio_key:
            item["latest_keyframe_image_url"] = image_url(minio_key)
        blurred_key = item.get("latest_keyframe_blurred_minio_key")
        if isinstance(blurred_key, str) and blurred_key:
            item["latest_keyframe_blurred_url"] = image_url(blurred_key)

    def _apply_keyframe_urls(
        self,
        item: dict[str, Any],
        *,
        image_url: ImageUrlFactory,
    ) -> dict[str, Any]:
        minio_key = item.get("minio_key")
        if isinstance(minio_key, str) and minio_key:
            item["image_url"] = image_url(minio_key)
        blurred_key = item.get("blurred_minio_key") or item.get("minio_blurred_key")
        if isinstance(blurred_key, str) and blurred_key:
            item["blurred_image_url"] = image_url(blurred_key)
        return item
