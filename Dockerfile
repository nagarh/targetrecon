FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl unzip && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY app.py .

RUN pip install --no-cache-dir .

# Download Ketcher into the INSTALLED package location (site-packages)
RUN STATIC_DIR=$(python -c "import targetrecon, os; print(os.path.join(os.path.dirname(targetrecon.__file__), 'static'))") && \
    mkdir -p "$STATIC_DIR/ketcher2" && \
    curl -fL "https://github.com/epam/ketcher/releases/download/v3.12.0/ketcher-standalone-3.12.0.zip" \
         -o /tmp/ketcher2.zip && \
    unzip -q /tmp/ketcher2.zip -d /tmp/ketcher2_extracted/ && \
    cp -r /tmp/ketcher2_extracted/standalone/. "$STATIC_DIR/ketcher2/" && \
    rm -rf /tmp/ketcher2.zip /tmp/ketcher2_extracted && \
    echo "Ketcher installed at $STATIC_DIR/ketcher2" && ls "$STATIC_DIR/ketcher2/index.html"

EXPOSE 7860

CMD ["python", "app.py"]
