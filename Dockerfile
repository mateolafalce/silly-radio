# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build and install the package into a throwaway prefix.
# Nothing from this stage reaches the final image except /install.
# ---------------------------------------------------------------------------
FROM python:3.12-alpine AS builder

WORKDIR /src
COPY pyproject.toml README.md ./
COPY selecto_radio ./selecto_radio

# The project is pure stdlib, so no dependency resolution happens here.
RUN python -m pip install --no-cache-dir --no-compile --prefix=/install . \
    && find /install -name '__pycache__' -type d -prune -exec rm -rf {} +

# ---------------------------------------------------------------------------
# Stage 2: runtime. Only Python, mpv and the installed package.
# mpv is the smallest of the three backends supported by player.py.
# ---------------------------------------------------------------------------
FROM python:3.12-alpine AS runtime

RUN apk add --no-cache mpv ca-certificates \
    && adduser -D -u 1000 radio \
    && addgroup radio audio

COPY --from=builder /install /usr/local

ENV HOME=/home/radio \
    TERM=xterm-256color \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER radio
WORKDIR /home/radio

ENTRYPOINT ["radio"]
