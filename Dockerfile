FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY pakko ./pakko

RUN pip install --upgrade pip && pip install .

VOLUME ["/app/data"]

CMD ["python", "-m", "pakko.main"]
