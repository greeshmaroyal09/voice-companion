"""Opt-in live TTS check using only an approved, generic Telugu greeting."""
import asyncio
import io
import json
import math
import struct
import wave
from pathlib import Path

from fastapi import HTTPException
from backend.main import TTS_URL, gnani_request
from backend.audio import playable_wav

TEXT = "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?"
OUTPUT = Path('artifacts/live-tts')


async def verify():
    # gnani_request retains HTTPX certificate and hostname verification.
    # No conversation store, transcript, or user details are read here.
    try:
        response = await gnani_request(TTS_URL, json={
            'text': TEXT, 'model': 'timbre-v2.5', 'voice': 'Lavanya',
            'language': 'te-IN', 'speed': 1.0,
            'audio_config': {'sample_rate': 24000, 'num_channels': 1,
                             'sample_width': 2, 'encoding': 'linear_pcm', 'container': 'wav'},
        })
    except HTTPException as error:
        print(json.dumps({'status': error.status_code, 'error': error.detail}))
        raise SystemExit(1)
    normalized = playable_wav(response.content)
    with wave.open(io.BytesIO(normalized), 'rb') as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        pcm = wav.readframes(frames)
    samples = struct.unpack(f'<{len(pcm) // 2}h', pcm)
    peak = max(abs(value) for value in samples)
    rms = math.sqrt(sum(value * value for value in samples) / len(samples))
    if not peak:
        raise ValueError('Provider returned silent audio')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'greeting.wav').write_bytes(normalized)
    report = {'provider_status': response.status_code, 'provider_bytes': len(response.content),
              'wav_bytes': len(normalized), 'header_repaired': normalized != response.content,
              'sample_rate': rate, 'frames': frames, 'seconds': frames / rate,
              'peak': peak, 'rms': round(rms, 2), 'certificate_verification': True}
    (OUTPUT / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    asyncio.run(verify())
