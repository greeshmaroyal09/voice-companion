"""Validate provider PCM WAVs, including streaming unknown-length headers."""
import io
import struct
import wave


def playable_wav(data: bytes) -> bytes:
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Not a WAV")
    declared = struct.unpack_from("<I", data, 4)[0]
    if declared != 0xFFFFFFFF and declared + 8 != len(data):
        raise ValueError("Incomplete RIFF")
    offset, pcm, fmt = 12, None, None
    while offset + 8 <= len(data):
        kind = data[offset:offset + 4]
        size = struct.unpack_from("<I", data, offset + 4)[0]
        offset += 8
        if size == 0xFFFFFFFF:
            # Some streaming writers finalize RIFF size but leave data size
            # unknown. The validated outer length still bounds those samples.
            if kind != b"data":
                raise ValueError("Unexpected unknown-length chunk")
            size = len(data) - offset
        if offset + size > len(data):
            raise ValueError("Truncated chunk")
        if kind == b"fmt ":
            fmt = data[offset:offset + size]
        if kind == b"data":
            if pcm is not None:
                raise ValueError("Duplicate audio chunk")
            pcm = data[offset:offset + size]
        offset += size + size % 2
    if offset != len(data) or fmt is None or len(fmt) < 16 or not pcm:
        raise ValueError("Missing or incomplete WAV chunks")
    encoding, channels, rate, byte_rate, align, bits = struct.unpack_from("<HHIIHH", fmt)
    if (encoding, channels, rate, bits, align, byte_rate) != (1, 1, 24000, 16, 2, 48000):
        raise ValueError("Unexpected reply audio format")
    if len(pcm) % align or len(pcm) > byte_rate * 120:
        raise ValueError("Invalid PCM length")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(bits // 8)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return output.getvalue()
