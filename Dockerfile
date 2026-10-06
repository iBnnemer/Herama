FROM python:3.11-slim

WORKDIR /herama

# تثبيت المتطلبات (llama-cpp-python يحتاج cmake للبناء)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

ENV HERAMA_HOST=0.0.0.0
ENV HERAMA_PORT=11434
ENV HERAMA_MODELS=/models
ENV HERAMA_ROOT=/herama

VOLUME ["/models", "/herama/.memory", "/herama/skills"]

EXPOSE 11434

CMD ["python", "-m", "app.main"]
