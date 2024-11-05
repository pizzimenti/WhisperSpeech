# Use a base image with Python
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the WhisperSpeech files
COPY . /app

# Install dependencies in one layer to reduce final image size
RUN pip install --upgrade pip && \
    pip install torch==1.13.1+cpu torchaudio transformers soundfile encodec

# Set the TTS script as the default entrypoint
ENTRYPOINT ["python", "/app/docker_tts.py"]

