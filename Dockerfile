FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY ai_commerce/ ./ai_commerce/
COPY tests/ ./tests/
COPY examples/ ./examples/
RUN useradd --uid 10001 --create-home appuser
USER appuser
EXPOSE 8000
CMD ["python", "-m", "ai_commerce", "serve", "--host", "0.0.0.0", "--port", "8000"]
