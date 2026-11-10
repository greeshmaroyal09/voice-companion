import { AudioLines, Languages, LoaderCircle, Mic, ShieldCheck, Square } from 'lucide-react';
import { MAX_SECONDS } from './audio';

export function VoiceControl({ recording, busy, stage, seconds, level, status, onToggle }: {
  recording: boolean; busy: boolean; stage: string; seconds: number; level: number; status: string; onToggle: () => void;
}) {
  return <section className={`voice-card ${recording ? 'is-recording' : ''}`} aria-labelledby="voice-heading" id="voice-space">
    <div className="voice-topline"><span><AudioLines size={15} /> YOUR VOICE SPACE</span><span className="voice-language" lang="te"><Languages size={14} /> తెలుగు</span></div>
    <div className="voice-interaction">
      <div className="mic-orbit"><button className="record-button" onClick={onToggle} disabled={busy}
        aria-label={recording ? 'Stop recording' : 'Start recording'} aria-pressed={recording}>
        {busy ? <LoaderCircle size={31} className="spin" /> : recording ? <Square size={27} fill="currentColor" /> : <Mic size={34} strokeWidth={1.6} />}
      </button></div>
      <div className="voice-description"><h2 id="voice-heading">{recording ? 'You speak. We listen.' : busy ? 'One moment…' : 'A conversation, naturally.'}</h2>
        <p lang="te">{recording ? 'మాట్లాడండి, నేను వింటున్నాను' : 'మీ మాటల్లో చెప్పండి'}</p>
        <span className="voice-instruction">{recording ? 'Tap the square to finish' : busy ? (stage === 'permission' ? 'Allow access to your microphone' : 'Your conversation will appear here') : 'Tap the mic to start speaking'}</span>
      </div>
    </div>
    <div className="voice-feedback">
      <div className={`waveform ${recording ? 'active' : ''}`} aria-hidden="true">{Array.from({ length: 29 }, (_, index) => <span key={index} style={{ height: `${recording ? 4 + level * (10 + (Math.sin(index * 1.8) + 1) * 20) : 4}px` }} />)}</div>
      <p className="voice-status" role="status"><span className={`status-dot ${recording ? 'recording-dot' : ''}`} />{status}</p>
      <span className="record-limit">{recording ? `0:${seconds.toString().padStart(2, '0')} / 0:${MAX_SECONDS}` : `Telugu voice · Up to ${MAX_SECONDS} seconds`}</span>
    </div>
    <div className="voice-footer"><ShieldCheck size={14} /><span>Audio is sent to Gnani for processing.</span></div>
  </section>;
}
