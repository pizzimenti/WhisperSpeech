# WhisperSpeech

WhisperSpeech is an Open Source text-to-speech (TTS) system that builds upon OpenAI’s Whisper model for high-quality, multilingual TTS. Previously known as **spear-tts-pytorch**, WhisperSpeech aims to be a flexible, high-performance TTS solution. This repository provides a Docker setup for ease of use on any system with Docker installed.

## Project Acknowledgments

WhisperSpeech was built by Collabora and LAION, with the goal of making a powerful, customizable TTS model accessible to everyone. This repository includes models trained on the English LibreLight dataset, with plans to expand to multiple languages.

> For more background on WhisperSpeech and its capabilities, please refer to the original documentation and progress updates provided by [Collabora on GitHub](https://github.com/collabora/WhisperSpeech).

## Docker Setup for WhisperSpeech

This repository has been updated to support a Docker-based workflow, allowing for simple text-to-speech conversion directly from the command line.

### 1. Prerequisites

- Ensure Docker is installed and running on your system. Instructions for installing Docker can be found [here](https://docs.docker.com/get-docker/).

### 2. Build the Docker Image

From the root of this repository, use the following command to build the Docker image:
```bash
docker build -t whisperspeech .
```

This command will give you speech back from the container:
```bash
docker run --rm -v "$(pwd):/output" whisperspeech "Hello, this is WhisperSpeech TTS" /output/output.wav
```
