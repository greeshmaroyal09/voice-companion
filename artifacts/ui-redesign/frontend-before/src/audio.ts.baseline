export const MAX_SECONDS = 25;

/** Signed 16-bit little-endian PCM in a genuine RIFF/WAVE container. */
export function encodeWav(samples: Float32Array, sampleRate = 16000): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const write = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };
  write(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true);
  write(8, 'WAVE'); write(12, 'fmt '); view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  write(36, 'data'); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
  }
  return buffer;
}

export function microphoneError(error: unknown): string {
  if (error instanceof DOMException) {
    if (['NotAllowedError', 'SecurityError'].includes(error.name)) {
      return 'Microphone permission was denied. Allow microphone access in your browser’s site settings, then try again.';
    }
    if (error.name === 'NotFoundError') return 'No microphone was found. Connect one and try again.';
    if (error.name === 'NotReadableError') return 'Your microphone is busy or unavailable. Close other apps using it and try again.';
  }
  return error instanceof Error ? error.message : 'Could not start recording. Please try again.';
}

export class WavRecorder {
  private stream?: MediaStream;
  private context?: AudioContext;
  private node?: AudioWorkletNode;
  private source?: MediaStreamAudioSourceNode;
  private chunks: Float32Array[] = [];
  private stopped?: () => void;
  private cancelled = false;

  async start(onLevel: (level: number) => void) {
    if (!navigator.mediaDevices?.getUserMedia || !window.isSecureContext) {
      throw new Error('Microphone recording needs a supported browser on localhost or HTTPS.');
    }
    // Resume the audio context in the original tap gesture (important on mobile).
    this.context = new AudioContext();
    try {
      await this.context.resume();
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      if (this.cancelled) { this.dispose(); throw new Error('Recording was cancelled.'); }
      await this.context.audioWorklet.addModule('/recorder-worklet.js');
      if (this.cancelled) throw new Error('Recording was cancelled.');
      this.node = new AudioWorkletNode(this.context, 'pcm-recorder');
      this.node.port.onmessage = ({ data }) => {
        if (data.type === 'stopped') { this.stopped?.(); return; }
        const samples: Float32Array = data.samples;
        this.chunks.push(samples);
        let power = 0;
        for (const sample of samples) power += sample * sample;
        onLevel(Math.min(1, Math.sqrt(power / samples.length) * 8));
      };
      this.source = this.context.createMediaStreamSource(this.stream);
      this.source.connect(this.node);
      // The worklet outputs silence; connecting keeps it processing without echo.
      this.node.connect(this.context.destination);
    } catch (error) { this.dispose(); throw error; }
  }

  async stop(): Promise<Blob> {
    const rate = this.context?.sampleRate ?? 48000;
    try {
      await new Promise<void>((resolve) => {
        const timeout = window.setTimeout(resolve, 500);
        this.stopped = () => { window.clearTimeout(timeout); resolve(); };
        this.node?.port.postMessage('stop');
      });
      const length = Math.min(this.chunks.reduce((sum, chunk) => sum + chunk.length, 0), rate * MAX_SECONDS);
      if (length < rate * 0.25) throw new Error('The recording is too short. Speak for at least a second and try again.');
      const samples = new Float32Array(length);
      let offset = 0;
      for (const chunk of this.chunks) {
        const part = chunk.subarray(0, length - offset);
        samples.set(part, offset); offset += part.length;
        if (offset >= length) break;
      }
      if (!samples.some((value) => Math.abs(value) > 0.0005)) throw new Error('The recording is silent. Check your microphone and try again.');
      const offline = new OfflineAudioContext(1, Math.ceil(length * 16000 / rate), 16000);
      const input = offline.createBuffer(1, length, rate);
      input.copyToChannel(samples, 0);
      const source = offline.createBufferSource();
      source.buffer = input; source.connect(offline.destination); source.start();
      const rendered = await offline.startRendering();
      return new Blob([encodeWav(rendered.getChannelData(0))], { type: 'audio/wav' });
    } finally { this.dispose(); }
  }

  dispose() {
    this.cancelled = true;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.source?.disconnect(); this.node?.disconnect();
    if (this.context && this.context.state !== 'closed') void this.context.close().catch(() => {});
    this.chunks = [];
  }
}
