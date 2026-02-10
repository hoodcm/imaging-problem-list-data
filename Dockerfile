FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca

WORKDIR /app

ENV UV_LINK_MODE=copy
ENV UV_COMPILE_BYTECODE=1
ENV UV_NO_DEV=1

# Run as non-root in the final container.
RUN groupadd --system --gid 999 nonroot \
    && useradd --system --gid 999 --uid 999 --create-home nonroot
RUN mkdir -p /data \
    && chown -R nonroot:nonroot /app /data

# Install transitive dependencies first for better layer reuse.
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

# Then copy source and install the project itself.
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

ENV PATH="/app/.venv/bin:${PATH}"
USER nonroot

EXPOSE 8001

CMD ["uv", "run", "finding-extractor-api"]
