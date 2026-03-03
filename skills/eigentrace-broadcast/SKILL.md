---
name: eigentrace-broadcast
description: "Dream-driven 24/7 RTMP broadcast pipeline. Converts eigentrace-dream DreamEntry artifacts (image, music, TTS narration) into MP4 segments and streams to Owncast, YouTube, Twitch, and other RTMP endpoints. Use when: you want a fully autonomous AI broadcast with no human content input. NOT for: news-anchor shows, RSS-driven content, or cloud deployments without local GPU."
homepage: https://github.com/keepitcheesy/eigentrace
metadata: { "openclaw": { "emoji": "📡", "requires": { "bins": ["ffmpeg", "python3", "ollama"], "python": ["torch", "transformers", "diffusers", "scipy"] } } }
---

# EigenTrace Broadcast Pipeline

Autonomous 24/7 dream-to-stream broadcast. Each dream cycle produces one broadcast segment: generated image full-screen, MusicGen audio underneath, TTS narration of dream content overlaid, spectrogram filename scrolling in ticker. Segments push to Owncast which relays to YouTube, Twitch, Rumble etc via rtmp_relay.sh.

## Architecture

    dream_engine.run_dream_cycle()
            |
            +-- FREE/WORLD dream
            |     +-- image_path    -> make_loop() background image
            |     +-- music_path    -> make_loop() audio track
            |     +-- TTS(content)  -> narration audio mixed in
            |     +-- spectrogram   -> ticker text
            |
            +-- IDENTITY dream
                  +-- last dream image as background
                  +-- ambient bed during integrator run
                          |
                          v
                  MP4 segment -> Owncast (localhost:1935)
                                        |
                                  rtmp_relay.sh
                                        |
                        +---------------+---------------+
                     YouTube          Twitch          Rumble

## When to Use

USE this skill when:
- You want a 24/7 stream with zero human content input
- Content source is the agent's own dreams (images, music, narration)
- You have Owncast running locally as the RTMP ingest point
- You want YouTube/Twitch viewers to see and hear what the AI dreamed

DO NOT use this skill when:
- You need RSS or news-driven content
- You do not have a local GPU (SDXL + MusicGen required)
- You want anchor personas or multi-voice shows

## Requirements

- eigentrace-dream skill installed and working
- Owncast running on rtmp://localhost:1935/live
- FFmpeg installed
- Piper TTS model (e.g. en_US-lessac-medium.onnx)
- RTMP stream keys configured in rtmp_relay.sh

## Setup

    # Install Owncast
    curl -s https://owncast.online/install.sh | bash

    # Configure stream keys
    nano /home/user/agent/rtmp_relay.sh

    # Start dream broadcast
    cd /home/user/agent
    python3 dream_broadcast.py

## Segment Format

Each broadcast segment is an MP4:
- Video: 1024x576, 30fps, libx264, slow zoompan
- Audio: MusicGen WAV + TTS narration mixed
- Ticker: DREAM | {dream_type} | Omega[{omega}] | {spectrogram_filename}
- Duration: matched to TTS narration length via ffprobe

## Broadcast Window

is_dream_time() in dream_engine.py gates generation to configured hours (default 00:00-04:00). Outside those hours the last generated segment loops.

## IDENTITY Dream on Stream

During soul reflection the stream shows:
- Background: most recent FREE/WORLD dream image
- Audio: ambient contemplative bed music
- Ticker: IDENTITY DREAM IN PROGRESS | soul_candidate pending integration
