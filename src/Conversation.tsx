import { AudioLines, ArrowUpRight, Check, FileText, Landmark, LoaderCircle, Square, Volume2 } from 'lucide-react';

export type ConversationTurn = {
  session_id: string;
  turn_id: string;
  transcript: string;
  reply: string;
  details: Record<string, string | null>;
};

const starters = [
  { icon: Landmark, label: 'Open a bank account', detail: 'Start with the basics', message: 'నేను SBIలో ఖాతా తెరవాలనుకుంటున్నా.' },
  { icon: FileText, label: 'Understand a document', detail: 'Make unfamiliar words familiar', message: 'PAN అంటే ఏంటి?' },
];

export function Conversation({ turns, disabled, loading, loadingText, restoring, onAsk, audioBusy, playing, audioUrl, onListen }: {
  turns: ConversationTurn[]; disabled: boolean; loading: boolean; loadingText: string; restoring: boolean;
  onAsk: (message: string) => void; audioBusy: boolean; playing: boolean; audioUrl: string; onListen: () => void;
}) {
  if (!turns.length) return <div className="conversation-empty">
    <span className="welcome-mark" aria-hidden="true"><AudioLines size={30} strokeWidth={1.5} /></span>
    <p className="eyebrow">A LITTLE GUIDANCE GOES A LONG WAY</p>
    <h2>Let’s make your next<br />bank visit a little easier.</h2>
    <p className="empty-description">Ask a question. Say it your way.<br />We’ll take it one step at a time.</p>
    <p className="empty-telugu" lang="te">మీ మాటల్లో అడగండి. కలిసి తెలుసుకుందాం.</p>
    <div className="starter-grid">{starters.map(({ icon: Icon, label, detail, message }) =>
      <button key={label} className="starter" disabled={disabled} onClick={() => onAsk(message)}>
        <Icon size={21} strokeWidth={1.6} aria-hidden="true" /><span><strong>{label}</strong><small>{detail}</small></span><ArrowUpRight size={17} aria-hidden="true" />
      </button>)}</div>
    {restoring && <p className="inline-status" role="status"><LoaderCircle size={16} className="spin" /> Restoring your conversation…</p>}
    {loading && <p className="inline-status" role="status"><LoaderCircle size={16} className="spin" />{loadingText}</p>}
  </div>;

  return <div className="message-list" role="log" aria-label="Conversation messages" aria-live="polite" aria-relevant="additions" aria-busy={loading}>
    <div className="conversation-beginning"><span />YOUR CONVERSATION<span /></div>
    {turns.map((turn, index) => <div className="message-turn" key={turn.turn_id}>
      <article className="message message-user" aria-label={`Your message ${index + 1}`}>
        <div className="message-meta">YOU <Check size={13} aria-label="Received" /></div>
        <p className="message-copy" dir="auto">{turn.transcript}</p>
      </article>
      <article className="message message-assistant" aria-label={`Companion reply ${index + 1}`}>
        <div className="assistant-avatar" aria-hidden="true"><AudioLines size={18} /></div>
        <div className="assistant-body"><div className="message-meta">VOICE COMPANION<span>One step at a time</span></div>
          <p className="message-copy" dir="auto">{turn.reply}</p>
          {index === turns.length - 1 && <button className={`listen-button ${playing ? 'is-playing' : ''}`} onClick={onListen} disabled={disabled || audioBusy}
            aria-label={audioBusy ? 'Preparing reply audio' : playing ? 'Stop reply playback' : audioUrl ? 'Listen to reply' : 'Retry generating reply audio'}>
            {audioBusy ? <LoaderCircle size={16} className="spin" /> : playing ? <Square size={13} /> : <Volume2 size={16} />}
            {audioBusy ? 'Preparing audio…' : playing ? 'Stop playback' : audioUrl ? 'Listen to reply' : 'Retry reply audio'}
            {playing && <span className="playback-indicator" aria-hidden="true"><i /><i /><i /></span>}
          </button>}
        </div>
      </article>
    </div>)}
    {loading && <div className="message-loading" role="status"><span className="assistant-avatar"><AudioLines size={18} /></span><LoaderCircle size={16} className="spin" /><span>{loadingText}</span></div>}
  </div>;
}
