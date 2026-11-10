/* Collect mono PCM. Never relay microphone audio to the speakers. */
class PcmRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(2048);
    this.offset = 0;
    this.frames = 0;
    this.active = true;
    this.port.onmessage = ({ data }) => {
      if (data === 'stop') {
        this.active = false;
        this.flush();
        this.port.postMessage({ type: 'stopped' });
      }
    };
  }
  flush() {
    if (!this.offset) return;
    const samples = this.buffer.slice(0, this.offset);
    this.port.postMessage({ type: 'samples', samples }, [samples.buffer]);
    this.offset = 0;
  }
  process(inputs) {
    const channels = inputs[0];
    if (this.active && channels?.length) {
      for (let i = 0; i < channels[0].length && this.frames < sampleRate * 25; i++) {
        let mono = 0;
        for (const channel of channels) mono += channel[i] / channels.length;
        this.buffer[this.offset++] = mono;
        this.frames++;
        if (this.offset === this.buffer.length) this.flush();
      }
    }
    return true;
  }
}
registerProcessor('pcm-recorder', PcmRecorder);
