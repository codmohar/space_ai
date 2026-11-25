import { Mic, MicOff, Radio, Square, Volume2 } from "lucide-react";
import type { VoiceMode, VoiceState } from "../../hooks/useVoiceAssistant";

interface VoiceConsoleBarProps {
  mode: VoiceMode;
  voiceState: VoiceState;
  liveTranscript: string;
  spokenCaption: string;
  engineBadge: string;
  waveformLevels: number[];
  errorMsg: string | null;
  onPttStart: () => void;
  onPttEnd: () => void;
  onToggleHandsFree: () => void;
  onInterrupt: () => void;
}

export function VoiceConsoleBar({
  mode,
  voiceState,
  liveTranscript,
  spokenCaption,
  engineBadge,
  waveformLevels,
  errorMsg,
  onPttStart,
  onPttEnd,
  onToggleHandsFree,
  onInterrupt,
}: VoiceConsoleBarProps) {
  const isListening = voiceState === "listening";
  const isSpeaking = voiceState === "speaking";
  const isBusy = voiceState === "transcribing" || voiceState === "thinking";

  return (
    <div className="border-b border-console-border bg-console-surface px-4 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {/* Push-To-Talk Hold Button */}
          <button
            type="button"
            onMouseDown={onPttStart}
            onMouseUp={onPttEnd}
            onMouseLeave={() => isListening && mode === "ptt" && onPttEnd()}
            onTouchStart={onPttStart}
            onTouchEnd={onPttEnd}
            aria-label="Hold to speak (Push-to-Talk)"
            className={`inline-flex items-center gap-1.5 rounded border px-3 py-1.5 font-mono text-xs font-medium transition-colors ${
              isListening && mode === "ptt"
                ? "border-signal-amber bg-signal-amber text-console-base"
                : "border-console-borderStrong bg-console-bg text-ink-primary hover:border-signal-amber"
            }`}
          >
            <Mic className="h-3.5 w-3.5" />
            {isListening && mode === "ptt" ? "RELEASE TO SEND" : "HOLD TO TALK (PTT)"}
          </button>

          {/* Hands-Free VAD Toggle */}
          <button
            type="button"
            onClick={onToggleHandsFree}
            aria-pressed={mode === "handsfree" && isListening}
            className={`inline-flex items-center gap-1.5 rounded border px-2.5 py-1.5 font-mono text-xs transition-colors ${
              mode === "handsfree" && isListening
                ? "border-status-verified bg-status-verified/15 text-status-verified"
                : "border-console-borderStrong bg-console-bg text-ink-secondary hover:text-ink-primary"
            }`}
          >
            {mode === "handsfree" && isListening ? (
              <Radio className="h-3.5 w-3.5" />
            ) : (
              <MicOff className="h-3.5 w-3.5" />
            )}
            HANDS-FREE
          </button>

          {/* Barge-In / Interrupt */}
          {(isSpeaking || isBusy || isListening) && (
            <button
              type="button"
              onClick={onInterrupt}
              aria-label="Interrupt voice response"
              className="inline-flex items-center gap-1 rounded border border-status-conflict/60 bg-status-conflict/15 px-2.5 py-1.5 font-mono text-xs text-status-conflict hover:bg-status-conflict/25"
            >
              <Square className="h-3 w-3 fill-current" />
              INTERRUPT
            </button>
          )}
        </div>

        {/* Waveform & Status */}
        <div className="flex items-center gap-3">
          <div
            aria-hidden="true"
            className="flex h-5 items-end gap-0.5"
          >
            {waveformLevels.map((lvl, i) => (
              <span
                key={i}
                style={{ height: `${Math.round(lvl * 100)}%` }}
                className={`w-1 rounded-sm transition-all duration-75 ${
                  isListening
                    ? "bg-signal-amber"
                    : isSpeaking
                      ? "bg-status-verified"
                      : "bg-console-borderStrong"
                }`}
              />
            ))}
          </div>
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink-secondary">
            {voiceState.toUpperCase()}
          </span>
          <span className="hidden rounded border border-console-border px-1.5 py-0.5 font-mono text-[10px] text-ink-muted sm:inline-block">
            {engineBadge}
          </span>
        </div>
      </div>

      {/* Live Transcript & Spoken Captions (WCAG AA Accessibility) */}
      {(liveTranscript || spokenCaption || errorMsg) && (
        <div
          aria-live="polite"
          className="mt-2 space-y-1 rounded border border-console-border bg-console-bg px-3 py-2 text-xs"
        >
          {liveTranscript && (
            <div className="font-mono text-[11px] text-ink-secondary">
              <span className="mr-2 text-signal-amber">MIC TRANSCRIPT:</span>
              {liveTranscript}
            </div>
          )}
          {spokenCaption && (
            <div className="flex items-start gap-1.5 text-[12px] text-ink-primary">
              <Volume2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-verified" />
              <span>
                <span className="mr-1.5 font-mono text-[10px] uppercase text-status-verified">
                  CAPTIONS:
                </span>
                {spokenCaption}
              </span>
            </div>
          )}
          {errorMsg && (
            <div className="font-mono text-[11px] text-status-conflict">
              {errorMsg}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
