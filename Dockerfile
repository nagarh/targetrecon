FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir targetrecon==0.1.5

COPY app.py .

EXPOSE 7860

CMD ["python", "app.py"]
