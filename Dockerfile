# Use a base image with Python
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the WhisperSpeech files
COPY . /app

# Install necessary dependencies without Jupyter
RUN pip install --upgrade pip && \
    pip install torch torchaudio transformers soundfile

# Set the TTS script as the default entrypoint
ENTRYPOINT ["python", "/app/docker_tts.py"]

