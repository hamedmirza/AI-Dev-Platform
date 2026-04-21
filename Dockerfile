FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY app ./app
COPY docs ./docs
COPY prompts ./prompts
COPY scripts ./scripts
COPY tests ./tests
COPY .env.example ./.env.example

RUN pip install --no-cache-dir .

EXPOSE 8400

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8400"]
