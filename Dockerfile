FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl unzip && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY app.py .

RUN pip install --no-cache-dir .

# Download Ketcher standalone bundles (excluded from git due to size)
RUN mkdir -p src/targetrecon/static/ketcher2 && \
    curl -fL "https://github.com/epam/ketcher/releases/download/v3.12.0/ketcher-standalone-3.12.0.zip" \
         -o /tmp/ketcher2.zip && \
    unzip -q /tmp/ketcher2.zip -d src/targetrecon/static/ketcher2/ && \
    rm /tmp/ketcher2.zip

EXPOSE 7860

CMD ["python", "app.py"]
