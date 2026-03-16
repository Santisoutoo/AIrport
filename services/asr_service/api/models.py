from pydantic import BaseModel

REDIS_KEY = "airport:asr_config"

DEFAULTS: dict[str, str] = {
    "input_device":       "default",
    "output_device":      "default",
    "ptt_key":            "Space",
    "backend":            "api",
    "hf_atc_model":       "jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper",
    "whisper_model_size": "small",
    "whisper_language":   "en",
    "ollama_url":         "http://host.docker.internal:11434",
    "ollama_model":       "whisper",
    "api_key":            "",
    "api_base_url":       "https://api.openai.com/v1",
    "api_model":          "whisper-1",
}


class AsrConfig(BaseModel):
    input_device:       str = "default"
    output_device:      str = "default"
    ptt_key:            str = "Space"
    backend:            str = "api"
    hf_atc_model:       str = "jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper"
    whisper_model_size: str = "small"
    whisper_language:   str = "en"
    ollama_url:         str = "http://host.docker.internal:11434"
    ollama_model:       str = "whisper"
    api_key:            str = ""
    api_base_url:       str = "https://api.openai.com/v1"
    api_model:          str = "whisper-1"
