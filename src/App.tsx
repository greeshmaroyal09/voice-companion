import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowRight, AudioLines, CircleAlert, CornerDownLeft, Languages, ListChecks, LockKeyhole, MessageSquare, Mic, Plus, Send, ShieldCheck, X } from 'lucide-react';
import { MAX_SECONDS, microphoneError, WavRecorder } from './audio';
import { apiRequest } from './api';
import { Checklist, type Preparation } from './Checklist';
import { Conversation } from './Conversation';
import { VoiceControl } from './VoiceControl';

type Stage = 'idle' | 'permission' | 'recording' | 'transcribing';
type Turn = { session_id: string; turn_id: string; transcript: string; reply: string; details: Record<string, string | null>; preparation?: Preparation };
const SESSION_KEY = 'voice-companion-session';

export default function App() {
  const [stage, setStage] = useState<Stage>('idle');
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [transcript, setTranscript] = useState('');
  const [reply, setReply] = useState('');
  const [audioUrl, setAudioUrl] = useState('');
  const [playing, setPlaying] = useState(false);
  const [audioBusy, setAudioBusy] = useState(false);
  const [error, setError] = useState('');
  const [setup, setSetup] = useState('');
  const [history, setHistory] = useState<Turn[]>([]);
  const [details, setDetails] = useState<Record<string, string | null>>({});
  const [preparation, setPreparation] = useState<Preparation>();
  const [typed, setTyped] = useState('');
  const [restoring, setRestoring] = useState(true);
  const [requestMode, setRequestMode] = useState<'text' | 'voice'>('text');
  const conversationEnd = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const sessionId = useRef<string | null>(null);
  const latestTurn = useRef<Turn | null>(null);
  const recorder = useRef<WavRecorder | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const active = useRef(false);
  const alive = useRef(true);
  const startedAt = useRef(0);
  const stopRef = useRef<() => void>(() => {});
  const audioRequest = useRef(0);
  const audioRequestId = useRef('');
  const activeAudioUrlRequestId = useRef('');
  const audioUrlRequestIds = useRef(new Map<string, string>());

  useEffect(() => {
    if (history.length || stage === 'transcribing') conversationEnd.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest' });
  }, [history.length, stage]);

  useEffect(() => {
    if (composer.current) {
      composer.current.style.height = 'auto';
      composer.current.style.height = `${Math.min(composer.current.scrollHeight, 160)}px`;
    }
  }, [typed]);

  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    apiRequest('/api/health').then((response) => response.json()).then((data) => {
      if (alive.current && !data.gnani_configured) setSetup('వాయిస్ సేవ ఇంకా సిద్ధం కాలేదు. టైప్ చేసి కొనసాగించవచ్చు.');
    }).catch(() => { if (alive.current) setSetup('సేవకు కనెక్ట్ కాలేకపోయాము. కొద్దిసేపటి తర్వాత ప్రయత్నించండి.'); });
    const saved = sessionStorage.getItem(SESSION_KEY);
    if (saved) {
      apiRequest('/api/conversation/restore', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: saved }) })
        .then((response) => response.json()).then((data) => {
          if (cancelled) return;
          sessionId.current = saved;
          const turns: Turn[] = data.turns.map((turn: Turn) => ({ ...turn, session_id: saved, details: data.details }));
          setHistory(turns); setDetails(data.details); setPreparation(data.preparation);
          const last = turns.at(-1);
          if (last) { latestTurn.current = last; setTranscript(last.transcript); setReply(last.reply); }
        }).catch(() => { if (!cancelled) { sessionStorage.removeItem(SESSION_KEY); setError('పాత సంభాషణను తెరవలేకపోయాము. కొత్తగా ప్రారంభించండి.'); } })
        .finally(() => { if (!cancelled) setRestoring(false); });
    } else setRestoring(false);
    return () => { cancelled = true; alive.current = false; recorder.current?.dispose(); };
  }, []);

  useEffect(() => () => {
    if (audioUrl) {
      const requestId = audioUrlRequestIds.current.get(audioUrl) ?? 'unknown';
      console.info(`[voice-audio] request_id=${requestId} stage=object_url_revoked source=blob`);
      URL.revokeObjectURL(audioUrl);
      audioUrlRequestIds.current.delete(audioUrl);
      if (activeAudioUrlRequestId.current === requestId) activeAudioUrlRequestId.current = '';
    }
  }, [audioUrl]);

  useEffect(() => {
    if (stage !== 'recording') return;
    const timer = window.setInterval(() => {
      const elapsed = (Date.now() - startedAt.current) / 1000;
      setSeconds(Math.min(MAX_SECONDS, Math.floor(elapsed)));
      if (elapsed >= MAX_SECONDS) stopRef.current();
    }, 100);
    return () => window.clearInterval(timer);
  }, [stage]);

  async function generateAudio(turn = latestTurn.current) {
    if (!turn) return;
    const request = ++audioRequest.current;
    const requestId = globalThis.crypto?.randomUUID?.() ?? `audio-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    audioRequestId.current = requestId;
    setAudioBusy(true);
    try {
      console.info(`[voice-audio] request_id=${requestId} stage=request_started`);
      const response = await apiRequest('/api/reply-audio', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Request-ID': requestId }, body: JSON.stringify({ session_id: turn.session_id, turn_id: turn.turn_id }) });
      const blob = await response.blob();
      const contentType = response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() ?? '';
      console.info(`[voice-audio] request_id=${requestId} stage=response status=${response.status} content_type=${contentType || 'missing'} body_bytes=${blob.size}`);
      if (!blob.size || contentType !== 'audio/wav' || blob.type.toLowerCase() !== 'audio/wav') throw new Error('The audio service returned an empty or unsupported audio file. Retry audio or continue the conversation.');
      if (alive.current && request === audioRequest.current) {
        const url = URL.createObjectURL(blob);
        audioUrlRequestIds.current.set(url, requestId);
        activeAudioUrlRequestId.current = requestId;
        console.info(`[voice-audio] request_id=${requestId} stage=object_url_created source=blob`);
        setAudioUrl(url);
      } else {
        console.info(`[voice-audio] request_id=${requestId} stage=stale_response_discarded`);
      }
    } catch (err) {
      const category = err instanceof Error && /TLS certificate/i.test(err.message) ? 'tls_certificate_verify_failed' : err instanceof Error && /Gnani .* returned HTTP/i.test(err.message) ? 'provider_http_error' : err instanceof Error ? err.name : 'unknown';
      console.warn(`[voice-audio] request_id=${requestId} stage=request_failed category=${category}`);
      if (alive.current && request === audioRequest.current) setError(err instanceof Error ? err.message : 'Could not prepare reply audio. Retry audio or continue the conversation.');
    } finally {
      if (alive.current && request === audioRequest.current) setAudioBusy(false);
    }
  }

  function acceptTurn(turn: Turn) {
    ++audioRequest.current;
    sessionId.current = turn.session_id; latestTurn.current = turn;
    sessionStorage.setItem(SESSION_KEY, turn.session_id);
    setTranscript(turn.transcript); setReply(turn.reply); setDetails(turn.details); setPreparation(turn.preparation);
    setHistory((previous) => [...previous, turn].slice(-50));
    setAudioUrl('');
  }

  async function sendText(message = typed) {
    if (!message.trim() || active.current || restoring) return;
    active.current = true; setError(''); setStage('transcribing');
    audio.current?.pause(); setPlaying(false);
    try {
      const typedRequestId = `typed-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`;
      console.info(`[voice-chat] request_id=${typedRequestId} stage=typed_request_started`);
      const response = await apiRequest('/api/conversation', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Request-ID': typedRequestId }, body: JSON.stringify({ text: message, session_id: sessionId.current }) });
      console.info(`[voice-chat] request_id=${typedRequestId} stage=typed_response status=${response.status}`);
      const turn: Turn = await response.json();
      acceptTurn(turn); setTyped('');
      void generateAudio(turn);
    } catch { setError('సందేశం పంపలేకపోయాము. మళ్లీ ప్రయత్నించండి. సంభాషణ గడువు ముగిస్తే New conversation నొక్కండి.'); }
    finally { active.current = false; setStage('idle'); }
  }

  async function newConversation() {
    if (active.current) return;
    active.current = true; setRestoring(true);
    ++audioRequest.current; setAudioBusy(false);
    if (sessionId.current) {
      try { await apiRequest('/api/conversation/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: sessionId.current }) }); }
      catch { /* A restarted/offline backend already cannot serve this session. */ }
    }
    audio.current?.pause(); setPlaying(false); setAudioUrl('');
    sessionId.current = null; latestTurn.current = null;
    sessionStorage.removeItem(SESSION_KEY);
    setHistory([]); setDetails({}); setPreparation(undefined); setTranscript(''); setReply(''); setError(''); setTyped('');
    active.current = false; setRestoring(false);
  }

  async function startRecording() {
    if (active.current) return;
    active.current = true;
    setError(''); setStage('permission');
    audio.current?.pause(); setPlaying(false);
    const next = new WavRecorder(); recorder.current = next;
    try {
      await next.start(setLevel);
      if (!alive.current) { next.dispose(); return; }
      setSeconds(0);
      startedAt.current = Date.now();
      setStage('recording');
    } catch (err) {
      if (alive.current) { setError(microphoneError(err)); setStage('idle'); }
      active.current = false;
    }
  }

  async function stopRecording() {
    const current = recorder.current;
    if (!current) return;
    recorder.current = null;
    setStage('transcribing'); setLevel(0);
    let sttRequestId = '';
    try {
      const blob = await current.stop();
      const form = new FormData(); form.append('audio', blob, 'recording.wav');
      if (sessionId.current) form.append('session_id', sessionId.current);
      sttRequestId = `stt-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`;
      console.info(`[voice-stt] request_id=${sttRequestId} stage=upload_started content_type=${blob.type || 'missing'} body_bytes=${blob.size}`);
      const response = await apiRequest('/api/transcribe', { method: 'POST', headers: { 'X-Request-ID': sttRequestId }, body: form });
      console.info(`[voice-stt] request_id=${sttRequestId} stage=response status=${response.status} content_type=${response.headers.get('content-type')?.split(';')[0] ?? 'missing'}`);
      const result = await response.json();
      if (!alive.current) return;
      acceptTurn(result); setSetup('');
      void generateAudio(result);
    } catch (err) {
      if (sttRequestId) console.warn(`[voice-stt] request_id=${sttRequestId} stage=request_failed category=${err instanceof Error && /TLS certificate/i.test(err.message) ? 'tls_certificate_verify_failed' : err instanceof Error && /Gnani .* returned HTTP/i.test(err.message) ? 'provider_http_error' : err instanceof Error ? err.name : 'unknown'}`);
      if (alive.current) setError(err instanceof Error ? err.message : 'Transcription failed. Please try again or type your message.');
    } finally {
      active.current = false;
      if (alive.current) setStage('idle');
    }
  }
  stopRef.current = () => { void stopRecording(); };

  async function playReply() {
    setError('');
    if (playing) { audio.current?.pause(); setPlaying(false); return; }
    if (!audioUrl) {
      if (active.current || audioBusy) return;
      await generateAudio();
      return; // A fresh tap plays the audio, including browsers that restrict autoplay.
    }
    try {
      if (audio.current) {
        console.info(`[voice-audio] request_id=${activeAudioUrlRequestId.current} stage=play_started source=${audio.current.currentSrc.startsWith('blob:') ? 'blob' : 'other'}`);
        audio.current.currentTime = 0;
        await audio.current.play();
      }
    } catch (err) {
      console.warn(`[voice-audio] request_id=${activeAudioUrlRequestId.current} stage=play_rejected category=${err instanceof Error ? err.name : 'unknown'}`);
      setError('The reply audio is ready, but playback could not start. Check sound settings and tap Listen again.');
    }
  }

  const recording = stage === 'recording';
  const busy = restoring || ['permission', 'transcribing'].includes(stage);
  const loadingText = requestMode === 'text' ? 'Thinking through your question…' : 'Turning your speech into words…';
  const status = restoring ? 'Restoring your conversation…' : {
    idle: playing ? 'Playing your reply' : audioBusy ? 'Preparing reply audio' : audioUrl ? 'Your reply is ready to listen' : 'Ready when you are',
    permission: 'Waiting for microphone access…', recording: 'Listening to you…', transcribing: loadingText,
  }[stage];
  const ask = (message: string) => { setRequestMode('text'); void sendText(message); };
  const toggleRecording = () => { if (recording) void stopRecording(); else { setRequestMode('voice'); void startRecording(); } };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#message">Skip to message</a>
      <aside className="sidebar" aria-label="Main navigation">
        <a className="brand" href="/" aria-label="Voice Companion home"><span className="brand-icon"><AudioLines size={24} /></span><span>voice<span className="brand-light">companion</span><small>A LITTLE MORE CONFIDENCE.</small></span></a>
        <div className="sidebar-section"><span className="nav-caption">YOUR COMPANION</span><nav>
          <a className="nav-item selected" href="#conversation" aria-current="page"><MessageSquare size={18} /> Conversation<span className="nav-current" /></a>
          <a className="nav-item" href="#visit-plan"><ListChecks size={18} /> Visit checklist<ArrowDown size={14} /></a>
        </nav></div>
        <div className="sidebar-bottom"><div className="sidebar-note"><span className="sidebar-note-icon"><Languages size={21} /></span><h2>Familiar words.<br />A clearer next step.</h2><p>Type in Telugu or English.<br />Speak naturally in Telugu.</p><span className="sidebar-language" lang="te">మీ మాటే మా మొదటి అడుగు.</span></div>
          <a className="sidebar-privacy" href="#privacy"><ShieldCheck size={16} /> Your privacy matters<ArrowRight size={14} /></a>
          <span className="independent-note">Independent guidance.<br />Not a bank or banking service.</span>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar"><div className="mobile-brand"><AudioLines size={23} /><span>voicecompanion</span></div><div className="breadcrumb"><span className="breadcrumb-icon"><MessageSquare size={15} /></span>Your companion<span>/</span><strong>Conversation</strong></div>
          <button className="new-conversation" disabled={busy || recording} onClick={() => void newConversation()}><Plus size={17} /><span>New conversation</span></button>
        </header>

        <main className="main-content">
          <div className="page-heading"><div><p className="eyebrow"><span /> BANKING, A LITTLE SIMPLER</p><h1>Your next step.<br className="small-break" /> <span>In your own words.</span></h1><p className="page-description">A little guidance for your bank visit. Speak or type — we’re here to help.</p></div><span className="language-pill"><Languages size={16} /><span lang="te">తెలుగు</span><span className="language-divider" /> English text</span></div>

          {setup && <div className="setup-note" role="status"><CircleAlert size={18} /><span lang="te">{setup}</span><button className="icon-button" aria-label="Dismiss setup notice" onClick={() => setSetup('')}><X size={17} /></button></div>}

          <div className="workspace-grid">
            <section className="conversation-surface" aria-labelledby="conversation-heading" id="conversation">
              <div className="conversation-heading"><div><span className="conversation-symbol"><MessageSquare size={18} /></span><h2 id="conversation-heading">Let’s talk</h2></div><span className="session-note"><span />{history.length ? 'Conversation in progress' : 'One step at a time'}</span></div>

              {Object.values(details).some(Boolean) && <div className="remembered" aria-label="Remembered details"><span className="remembered-label">REMEMBERED</span>{Object.entries(details).filter(([, value]) => value).map(([key, value]) => <span className="detail-tag" key={key}><strong>{key === 'intent' ? 'Purpose' : key.charAt(0).toUpperCase() + key.slice(1)}:</strong> {key === 'intent' ? ({ open_account: 'ఖాతా తెరవడం', close_account: 'ఖాతా మూసివేయడం', withdraw: 'డబ్బు తీసుకోవడం', deposit: 'డబ్బు జమ చేయడం', transfer: 'డబ్బు బదిలీ చేయడం', balance: 'బ్యాలెన్స్' }[value!] ?? value) : value}</span>)}</div>}

              <Conversation turns={history} disabled={busy || recording} loading={stage === 'transcribing'} loadingText={loadingText} restoring={restoring} onAsk={ask} audioBusy={audioBusy} playing={playing} audioUrl={audioUrl} onListen={() => void playReply()} />

              <div ref={conversationEnd} className="conversation-end" />
              <div className="composer-dock">
                {error && <div className="error-note" role="alert"><CircleAlert size={20} /><div><strong>We couldn’t finish that step</strong><p>{error}</p><span>Your conversation is still here. Try again when you’re ready.</span></div><button className="icon-button" onClick={() => setError('')} aria-label="Dismiss error"><X size={17} /></button></div>}
                {reply && <div className="conversation-actions" aria-label="Suggested follow-ups">{['అది ఏంటి?', 'మళ్ళీ చెప్పు', 'నాకు అది లేదు', 'తర్వాత'].map(text => <button key={text} disabled={busy || recording} onClick={() => ask(text)} lang="te">{text}{text === 'తర్వాత' && <ArrowRight size={14} aria-hidden="true" />}</button>)}</div>}
                <form className="text-entry" onSubmit={(event) => { event.preventDefault(); ask(typed); }}>
                  <label htmlFor="message" className="sr-only">Your message in Telugu or English</label>
                  <textarea ref={composer} id="message" value={typed} onChange={(event) => setTyped(event.target.value)} onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); ask(typed); }
                  }} rows={1} maxLength={2000} disabled={busy || recording} placeholder="మీ ప్రశ్న అడగండి… or type your question" aria-describedby="composer-help" />
                  <div className="composer-controls"><div className="composer-mode">{recording || stage === 'transcribing' || stage === 'permission' ? <span role="status">{recording ? `Listening · 0:${seconds.toString().padStart(2, '0')} / 0:${MAX_SECONDS}` : status}</span> : <><span><Languages size={14} /> Telugu & English</span><span className="keyboard-hint"><CornerDownLeft size={12} /> Enter to send</span></>}</div><div className="composer-buttons"><button type="button" className={`composer-mic ${recording ? 'is-recording' : ''}`} onClick={toggleRecording} disabled={busy} aria-pressed={recording} aria-label={recording ? 'Stop recording from message composer' : 'Start recording from message composer'}>{recording ? <span className="stop-symbol" aria-hidden="true" /> : <Mic size={19} />}</button><button type="submit" className="send-button" disabled={busy || recording || !typed.trim()} aria-label="Send message"><span>Send</span><Send size={16} /></button></div></div>
                </form>
                <p className="composer-help" id="composer-help"><LockKeyhole size={12} /><span>Keep document numbers, OTPs and PINs private.</span><span className="multiline-hint">Shift + Enter for a new line</span></p>
              </div>
              <div className="conversation-footnote"><ShieldCheck size={13} /><span>Guidance for your visit. Confirm current requirements with your branch.</span></div>
            </section>

            <aside className="support-column" aria-label="Voice and visit preparation">
              <VoiceControl recording={recording} busy={busy} stage={stage} seconds={seconds} level={level} status={status} onToggle={toggleRecording} />
              <section className="visit-plan" id="visit-plan" aria-labelledby="visit-plan-heading"><div className="support-heading"><span className="plan-icon"><ListChecks size={20} /></span><div><p className="eyebrow">A LITTLE PREPARATION</p><h2 id="visit-plan-heading">Your visit, made clearer.</h2></div></div>
                {preparation?.checklist.length ? <Checklist preparation={preparation} disabled={busy || recording} onAsk={ask} /> : <div className="plan-empty"><div className="plan-placeholder" aria-hidden="true"><span /><span /><span /></div><p>Your visit checklist will appear here as we learn what you need.</p><span>No need to figure it all out at once.</span></div>}
              </section>
              {!!preparation?.reply_sources?.length && <details className="reply-sources"><summary>ఆధారాలు / Reply sources</summary>{preparation.reply_sources.map(source => <p key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a><span>Checked {source.checked_on}</span></p>)}</details>}
              <details className="privacy-details" id="privacy"><summary><ShieldCheck size={17} /> A private detail can stay private.</summary><p lang="te">పత్రాలు అప్‌లోడ్ చేయవద్దు. ఆధార్/PAN నంబర్లు, OTP, PIN, పాస్‌వర్డ్‌లు చెప్పవద్దు. పత్రం పేరు మాత్రమే చాలు.</p><p>Your details stay in this conversation. Correct them anytime. New conversation clears this session.</p><p>Audio is sent to Gnani for processing. This is preparation guidance, not a guarantee that an account will be opened.</p></details>
            </aside>
          </div>
          <footer className="page-footer"><span>HUMAN WORDS. A LITTLE MORE CONFIDENCE.</span><span>Made for everyday conversations <span>·</span> Telugu voice + text</span></footer>
        </main>
      </div>

      <audio ref={audio} src={audioUrl || undefined}
        onCanPlay={() => console.info(`[voice-audio] request_id=${activeAudioUrlRequestId.current} stage=can_play source=${audio.current?.currentSrc.startsWith('blob:') ? 'blob' : 'other'}`)}
        onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
        onEnded={() => { console.info(`[voice-audio] request_id=${activeAudioUrlRequestId.current} stage=play_ended`); setPlaying(false); }}
        onError={() => {
          const mediaError = audio.current?.error;
          console.warn(`[voice-audio] request_id=${activeAudioUrlRequestId.current} stage=decode_failed media_error=${mediaError?.code ?? 'unknown'} source=${audio.current?.currentSrc.startsWith('blob:') ? 'blob' : 'other'}`);
          if (audioUrl) { setPlaying(false); setAudioUrl(''); setError('The audio arrived, but this browser could not decode it. Retry audio or continue the conversation.'); }
        }} />
    </div>
  );
}
