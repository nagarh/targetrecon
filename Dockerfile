FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY app.py .

RUN pip install --no-cache-dir .

EXPOSE 7860

CMD ["python", "app.py"]
