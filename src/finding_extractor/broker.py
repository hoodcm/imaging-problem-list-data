"""TaskIQ broker configuration for API and worker processes."""

import os

import taskiq_fastapi
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

_redis_url = os.getenv("FINDING_EXTRACTOR_REDIS_URL", "redis://localhost:6379")

result_backend = RedisAsyncResultBackend(redis_url=_redis_url, result_ex_time=3600)
broker = RedisStreamBroker(url=_redis_url).with_result_backend(result_backend)

# Must be registered in the broker module so worker startup gets FastAPI DI context.
taskiq_fastapi.init(broker, "finding_extractor.api:app")
