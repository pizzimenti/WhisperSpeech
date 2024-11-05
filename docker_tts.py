# docker_tts.py

import sys
from encodec.model import EncodecModel
import whisper
import whisperx
from whisperspeech import WhisperSpeech
from speechbrain.pretrained import EncoderClassifier
from os.path import expanduser
import urllib.request
import soundfile as sf

def download_models():
    """Downloads and initializes the necessary models for WhisperSpeech."""
    print("Downloading and setting up models...")

    # Download EnCodec model (for audio encoding)
    EncodecModel.encodec_model_24khz()

    # Download Whisper models
    whisper.load_model('base.en')
    whisper.load_model('small.en')
    whisper.load_model('medium')
    
    # Load WhisperX models with different configurations
    load_whisperx('small.en', 'en')
    load_whisperx('medium.en', 'en')
    load_whisperx('large-v3', 'en')

    # Load speaker recognition model for speaker style or mimicry
    EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=expanduser("~/.cache/speechbrain/")
    )
    
    # Download additional model if needed
    urllib.request.urlretrieve(
        'https://github.com/marianne-m/brouhaha-vad/raw/main/models/best/checkpoints/best.ckpt',
        expanduser('~/.cache/brouhaha.ckpt')
    )

    print("Model setup complete.")

def load_whisperx(model, lang):
    """Loads a WhisperX model with the specified settings."""
    try:
        whisperx.asr.load_model(model, "cpu", compute_type="float16", language=lang)
    except ValueError as exc:
        print(f"Error loading WhisperX model: {exc}")

def synthesize_text(text, output_path="output.wav"):
    """Synthesizes speech from text input and saves it as a .wav file."""
    print("Initializing WhisperSpeech pipeline...")
    pipe = WhisperSpeech()  # Initialize WhisperSpeech TTS pipeline

    print("Generating audio...")
    audio_data = pipe.generate(text, lang="en", speaker=None)

    print(f"Saving audio to {output_path}...")
    sf.write(output_path, audio_data, samplerate=24000)  # Save audio at 24kHz
    print(f"Audio saved successfully to {output_path}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python docker_tts.py '<text_to_synthesize>' [output_path]")
        return

    text = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "output.wav"

    download_models()  # Ensure models are downloaded and ready
    synthesize_text(text, output_path)

if __name__ == "__main__":
    main()

