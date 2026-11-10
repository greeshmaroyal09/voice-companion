import { describe, expect, it } from 'vitest';
import { encodeWav, microphoneError } from './audio';

describe('browser WAV encoding', () => {
  it('writes a 16 kHz mono PCM WAV header with exact duration and size', () => {
    const bytes = encodeWav(new Float32Array(16000));
    const header = new DataView(bytes);
    const text = (start: number, length: number) => new TextDecoder().decode(bytes.slice(start, start + length));
    expect(text(0, 4)).toBe('RIFF'); expect(text(8, 4)).toBe('WAVE');
    expect(text(12, 4)).toBe('fmt '); expect(text(36, 4)).toBe('data');
    expect(header.getUint32(4, true)).toBe(bytes.byteLength - 8);
    expect(header.getUint16(20, true)).toBe(1); // PCM
    expect(header.getUint16(22, true)).toBe(1); // mono
    expect(header.getUint32(24, true)).toBe(16000);
    expect(header.getUint32(28, true)).toBe(32000);
    expect(header.getUint16(32, true)).toBe(2);
    expect(header.getUint16(34, true)).toBe(16);
    expect(header.getUint32(40, true)).toBe(32000);
    expect(bytes.byteLength).toBe(32044);
  });
  it('clips amplitudes and writes signed little-endian samples', () => {
    const data = new DataView(encodeWav(new Float32Array([-2, -1, 0, 0.5, 1, 2])));
    expect(Array.from({ length: 6 }, (_, i) => data.getInt16(44 + i * 2, true))).toEqual([-32768, -32768, 0, 16384, 32767, 32767]);
  });
  it('wraps captured PCM as audio/wav with the expected duration and nonzero samples', () => {
    const pcm = new Float32Array(8000).fill(0.1);
    const bytes = encodeWav(pcm);
    const blob = new Blob([bytes], { type: 'audio/wav' });
    const view = new DataView(bytes);
    expect(blob.type).toBe('audio/wav');
    expect(blob.size).toBe(44 + 8000 * 2);
    expect(view.getInt16(44, true)).not.toBe(0);
    expect(view.getUint32(40, true) / 2 / 16000).toBe(0.5);
    // One-channel 16-bit PCM at 16 kHz: 8,000 samples is 0.5 seconds.
    expect(pcm.length / 16000).toBe(0.5);
  });
});

describe('microphone recovery guidance', () => {
  it('explains how to recover from denied permissions', () => {
    expect(microphoneError(new DOMException('', 'NotAllowedError'))).toContain('site settings');
  });
  it('distinguishes missing and busy microphones', () => {
    expect(microphoneError(new DOMException('', 'NotFoundError'))).toContain('No microphone');
    expect(microphoneError(new DOMException('', 'NotReadableError'))).toContain('busy');
  });
});
