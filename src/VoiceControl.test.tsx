import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { VoiceControl } from './VoiceControl';

const props = { recording: false, busy: false, stage: 'idle', seconds: 0, level: 0, status: 'Ready when you are', onToggle: () => {} };

describe('truthful voice-control presentation', () => {
  it('never shows recording or animated activity while idle', () => {
    const html = renderToStaticMarkup(<VoiceControl {...props} />);
    expect(html).toContain('aria-label="Start recording"');
    expect(html).toContain('aria-pressed="false"');
    expect(html).toContain('Ready when you are');
    expect(html).not.toContain('waveform active');
    expect(html).not.toContain('is-recording');
    expect(html).not.toContain('Listening to you');
  });
  it('uses captured recording state and level for the stop control and waveform', () => {
    const html = renderToStaticMarkup(<VoiceControl {...props} recording stage="recording" seconds={9} level={0.7} status="Listening to you…" />);
    expect(html).toContain('aria-label="Stop recording"');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('waveform active');
    expect(html).toContain('0:09 / 0:25');
    expect(html).not.toContain('disabled');
    const silent = renderToStaticMarkup(<VoiceControl {...props} recording stage="recording" level={0} />);
    expect(silent.match(/height:4px/g)).toHaveLength(29);
  });
  it('distinguishes permission and processing states without claiming to listen', () => {
    const html = renderToStaticMarkup(<VoiceControl {...props} busy stage="permission" status="Waiting for microphone access…" />);
    expect(html).toContain('Allow access to your microphone');
    expect(html).toContain('disabled');
    expect(html).not.toContain('waveform active');
    const processing = renderToStaticMarkup(<VoiceControl {...props} busy stage="transcribing" status="Turning your speech into words…" />);
    expect(processing).toContain('Turning your speech into words…');
    expect(processing).not.toContain('is-recording');
  });
});
