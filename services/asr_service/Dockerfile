FROM python:3.11-slim

WORKDIR /app

# System deps: ffmpeg for audio decoding
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Available models:
#   jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper  (default)
#   jacktol/whisper-large-v3-finetuned-for-ATC
ARG ASR_HF_MODEL=jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper
ENV ASR_HF_MODEL=${ASR_HF_MODEL}

COPY download_model.py .
RUN python download_model.py

COPY . .

# Cloud Run injects PORT env var; default to 8000
ENV PORT=8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
