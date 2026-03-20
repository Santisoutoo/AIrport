import os

model_id = os.environ.get("ASR_HF_MODEL", "jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper")
print(f"Pre-downloading model: {model_id}")

if "faster-whisper" in model_id:
    from faster_whisper import WhisperModel
    WhisperModel(model_id, device="cpu", compute_type="int8")
else:
    from transformers import pipeline
    pipeline("automatic-speech-recognition", model=model_id)

print("Model cached successfully.")
