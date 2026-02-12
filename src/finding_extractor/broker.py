"""TaskIQ broker configuration for API and worker processes."""

import taskiq_fastapi
from taskiq import TaskiqEvents
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from finding_extractor.config import get_settings
from finding_extractor.logging_setup import setup_logging
from finding_extractor.observability import configure_logfire

settings = get_settings()
_redis_url = settings.redis_url

result_backend = RedisAsyncResultBackend(redis_url=_redis_url, result_ex_time=settings.redis_result_ttl)
broker = RedisStreamBroker(url=_redis_url).with_result_backend(result_backend)

# Must be registered in the broker module so worker startup gets FastAPI DI context.
taskiq_fastapi.init(broker, "finding_extractor.api:app")


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def configure_worker_observability(_event: object) -> None:
    """Configure process-global worker observability once at worker startup."""
    runtime_settings = get_settings()
    logfire_enabled = configure_logfire(runtime="worker")
    setup_logging(runtime_settings, include_logfire_processor=logfire_enabled)
