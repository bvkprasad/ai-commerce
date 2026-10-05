FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AI_COMMERCE_HOST=0.0.0.0
COPY pyproject.toml README.md LICENSE ./
COPY ai_commerce/ ./ai_commerce/
COPY retrieval/ ./retrieval/
COPY experiments/ ./experiments/
COPY tests/ ./tests/
COPY examples/ ./examples/
RUN pip install --no-cache-dir ".[test]"
RUN useradd --uid 10001 --create-home appuser
USER appuser
EXPOSE 8000
CMD ["python", "-m", "ai_commerce"]
