FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

ARG ASR_HF_MODEL=jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper
ENV ASR_HF_MODEL=${ASR_HF_MODEL}

COPY download_model.py .
RUN python download_model.py

COPY . .

EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
