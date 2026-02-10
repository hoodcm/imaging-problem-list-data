"""Model discovery and Redis-backed caching for `/api/models`."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import uuid4

from anthropic import AsyncAnthropic
from google import genai
from openai import AsyncOpenAI
from redis.asyncio import Redis

from finding_extractor.config import Settings
from finding_extractor.model_policy import (
    canonical_model_key,
    model_ids_equivalent,
    output_model_prefix,
    provider_from_model_id,
    select_sota_model_ids,
    validate_model_id,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CatalogModel:
    """Single model option exposed from `/api/models`."""

    id: str
    provider: str
    tier: str
    is_default: bool = False


@dataclass(slots=True)
class ModelCatalog:
    """Serialized catalog payload with freshness metadata."""

    updated_at: str
    stale: bool
    refresh_interval_seconds: int
    models: list[CatalogModel]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _model_provider(model_id: str) -> str | None:
    return provider_from_model_id(model_id)


class ModelCatalogService:
    """Discover provider models and cache a SOTA-filtered catalog in Redis."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)
        self.cache_key = "finding_extractor:model_catalog:v1"
        self.lock_key = f"{self.cache_key}:lock"
        self.lock_ttl_seconds = 60

    async def close(self) -> None:
        with suppress(Exception):
            await self.redis.aclose()

    async def get_catalog(self) -> ModelCatalog:
        cached: ModelCatalog | None = None
        try:
            cached = await self._read_cache()
        except Exception:
            logger.warning("Model catalog cache read failed", exc_info=True)
        if cached is not None and not self._is_stale(cached.updated_at):
            return cached

        refreshed: ModelCatalog | None = None
        try:
            refreshed = await self._refresh_cache()
        except Exception:
            logger.warning("Model catalog cache refresh failed", exc_info=True)
        if refreshed is not None:
            return refreshed

        if cached is not None:
            cached.stale = True
            return cached

        # Redis unavailable and no cached value: compute an uncached fallback.
        models = await self._discover_models_safe()
        return ModelCatalog(
            updated_at=_iso_now(),
            stale=True,
            refresh_interval_seconds=self.settings.update_model_list_interval_seconds,
            models=models,
        )

    async def _refresh_cache(self) -> ModelCatalog | None:
        token = str(uuid4())
        acquired = await self.redis.set(
            self.lock_key,
            token,
            nx=True,
            ex=self.lock_ttl_seconds,
        )
        if acquired is not True:
            return None

        try:
            models = await self._discover_models()
            updated_at = _iso_now()
            payload = {
                "updated_at": updated_at,
                "refresh_interval_seconds": self.settings.update_model_list_interval_seconds,
                "models": [asdict(model) for model in models],
            }
            await self.redis.set(self.cache_key, json.dumps(payload))
            return ModelCatalog(
                updated_at=updated_at,
                stale=False,
                refresh_interval_seconds=self.settings.update_model_list_interval_seconds,
                models=models,
            )
        finally:
            with suppress(Exception):
                await self.redis.eval(
                    """
                    if redis.call('GET', KEYS[1]) == ARGV[1] then
                        return redis.call('DEL', KEYS[1])
                    end
                    return 0
                    """,
                    1,
                    self.lock_key,
                    token,
                )

    async def _read_cache(self) -> ModelCatalog | None:
        payload = await self.redis.get(self.cache_key)
        if not payload:
            return None
        try:
            data = json.loads(payload)
            models = [CatalogModel(**item) for item in data["models"]]
            return ModelCatalog(
                updated_at=str(data["updated_at"]),
                stale=False,
                refresh_interval_seconds=int(data["refresh_interval_seconds"]),
                models=models,
            )
        except Exception:
            logger.exception("Invalid model catalog cache payload")
            return None

    def _is_stale(self, updated_at: str) -> bool:
        try:
            updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        except ValueError:
            return True
        age_seconds = (datetime.now(UTC) - updated_dt).total_seconds()
        return age_seconds >= self.settings.update_model_list_interval_seconds

    async def _discover_models(self) -> list[CatalogModel]:
        tasks: list[asyncio.Task[tuple[str, set[str]]]] = []

        if self.settings.openai_api_key:
            tasks.append(asyncio.create_task(self._discover_openai()))
        if self.settings.anthropic_api_key:
            tasks.append(asyncio.create_task(self._discover_anthropic()))
        if self.settings.google_api_key:
            tasks.append(asyncio.create_task(self._discover_google()))

        provider_models: dict[str, set[str]] = {}
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning("Model discovery failed: %s", result)
                    continue
                if not isinstance(result, tuple) or len(result) != 2:
                    logger.warning("Unexpected model discovery result type: %r", result)
                    continue
                provider, model_ids = result
                provider_models[provider] = model_ids

        catalog: list[CatalogModel] = []
        for provider, model_ids in provider_models.items():
            if not model_ids:
                continue
            prefix = output_model_prefix(provider)
            for tier, model_id in select_sota_model_ids(provider, model_ids):
                full_model_id = f"{prefix}:{model_id}"
                catalog.append(
                    CatalogModel(
                        id=full_model_id,
                        provider=provider,
                        tier=tier,
                        is_default=model_ids_equivalent(full_model_id, self.settings.default_model),
                    )
                )

        if not catalog:
            default_model = self._default_catalog_model()
            if default_model is not None:
                catalog.append(default_model)

        return sorted(catalog, key=lambda item: (item.provider, item.tier, item.id))

    async def _discover_models_safe(self) -> list[CatalogModel]:
        try:
            return await self._discover_models()
        except Exception:
            logger.warning("Model discovery fallback failed", exc_info=True)
            default_model = self._default_catalog_model()
            return [default_model] if default_model is not None else []

    def _default_catalog_model(self) -> CatalogModel | None:
        model_id = self.settings.default_model
        try:
            validate_model_id(model_id)
        except ValueError:
            logger.warning("Configured default model excluded by policy: %s", model_id)
            return None

        canonical = canonical_model_key(model_id)
        if canonical is None:
            return CatalogModel(
                id=model_id,
                provider=_model_provider(model_id) or "unknown",
                tier="default",
                is_default=True,
            )

        provider, raw_model_id = canonical
        selected = select_sota_model_ids(provider, {raw_model_id})
        if not selected:
            logger.warning("Configured default model excluded by policy: %s", model_id)
            return None
        tier, _ = selected[0]
        return CatalogModel(
            id=model_id,
            provider=provider,
            tier=tier,
            is_default=True,
        )

    async def _discover_openai(self) -> tuple[str, set[str]]:
        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        model_ids: set[str] = set()
        try:
            pager = await client.models.list()
            async for model in pager:
                model_id = getattr(model, "id", None)
                if isinstance(model_id, str):
                    model_ids.add(model_id)
        finally:
            await client.close()
        return "openai", model_ids

    async def _discover_anthropic(self) -> tuple[str, set[str]]:
        client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        model_ids: set[str] = set()
        try:
            pager = await client.models.list(limit=100)
            async for model in pager:
                model_id = getattr(model, "id", None)
                if isinstance(model_id, str):
                    model_ids.add(model_id)
        finally:
            await client.close()
        return "anthropic", model_ids

    async def _discover_google(self) -> tuple[str, set[str]]:
        client = genai.Client(api_key=self.settings.google_api_key)
        model_ids: set[str] = set()
        try:
            pager = await client.aio.models.list()
            async for model in pager:
                model_name = getattr(model, "name", None)
                if isinstance(model_name, str):
                    model_ids.add(model_name.split("/", maxsplit=1)[-1])
        finally:
            await client.aio.aclose()
        return "google", model_ids
