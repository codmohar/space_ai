import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ChatResponse } from "../api/client";

export type VoiceMode = "ptt" | "handsfree";
export type VoiceState =
  | "idle"
  | "listening"
  | "transcribing"
  | "thinking"
  | "speaking"
  | "error";

interface UseVoiceAssistantOptions {
  conversationId: string | null;
  mission: string;
  selectorMode: string;
  onTranscript: (text: string) => void;
  onAnswer: (res: ChatResponse, spokenText: string) => void;
}

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((ev: any) => void) | null;
  onerror: ((ev: any) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

export function useVoiceAssistant({
  conversationId,
  mission,
  selectorMode,
  onTranscript,
  onAnswer,
}: UseVoiceAssistantOptions) {
  const [mode, setMode] = useState<VoiceMode>("ptt");
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [liveTranscript, setLiveTranscript] = useState<string>("");
  const [spokenCaption, setSpokenCaption] = useState<string>("");
  const [engineBadge, setEngineBadge] = useState<string>("WS / faster-whisper");
  const [waveformLevels, setWaveformLevels] = useState<number[]>(() =>
    Array.from({ length: 12 }, () => 0.12)
  );
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const handsFreeActiveRef = useRef<boolean>(false);
  const voiceStateRef = useRef<VoiceState>("idle");
  const speechActiveRef = useRef<boolean>(false);
  const silenceStartRef = useRef<number>(0);

  const onTranscriptRef = useRef(onTranscript);
  const onAnswerRef = useRef(onAnswer);
  onTranscriptRef.current = onTranscript;
  onAnswerRef.current = onAnswer;

  const setVState = useCallback((s: VoiceState) => {
    voiceStateRef.current = s;
    setVoiceState(s);
  }, []);

  const stopAudioPlayback = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    if (audioElRef.current) {
      audioElRef.current.pause();
      audioElRef.current.currentTime = 0;
      audioElRef.current = null;
    }
  }, []);

  const speakWithBrowserFallback = useCallback(
    (text: string) => {
      if (!text.trim()) {
        setVState("idle");
        return;
      }
      setSpokenCaption(text);
      if (typeof window === "undefined" || !("speechSynthesis" in window)) {
        setVState("idle");
        return;
      }
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(text);
      utter.rate = 1.03;
      utter.pitch = 1.0;
      utter.onstart = () => setVState("speaking");
      utter.onend = () => {
        if (voiceStateRef.current === "speaking") {
          setVState(handsFreeActiveRef.current ? "listening" : "idle");
        }
      };
      utter.onerror = () => {
        setVState(handsFreeActiveRef.current ? "listening" : "idle");
      };
      setVState("speaking");
      window.speechSynthesis.speak(utter);
    },
    [setVState]
  );

  const ensureSocket = useCallback((): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      const existing = wsRef.current;
      if (existing && existing.readyState === WebSocket.OPEN) {
        resolve(existing);
        return;
      }

      const ws = new WebSocket(api.voiceWsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(
          JSON.stringify({
            type: "config",
            conversation_id: conversationId,
            mission: mission || null,
            selector_mode: selectorMode || null,
          })
        );
        resolve(ws);
      };

      ws.onerror = () => {
        setErrorMsg("Voice WebSocket connection error.");
        reject(new Error("WebSocket connection error"));
      };

      ws.onclose = () => {
        if (wsRef.current === ws) {
          wsRef.current = null;
        }
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "transcript") {
            const text = (msg.text || "").trim();
            setLiveTranscript(text);
            if (text) {
              setVState("thinking");
              onTranscriptRef.current(text);
            } else {
              setVState(handsFreeActiveRef.current ? "listening" : "idle");
            }
          } else if (msg.type === "stt_fallback") {
            setEngineBadge("Browser Web Speech Fallback");
            startBrowserSpeechFallback();
          } else if (msg.type === "answer") {
            const chatRes = msg.chat_response as ChatResponse;
            const spoken = (msg.spoken_text || chatRes.spoken_text || "").trim();
            setSpokenCaption(spoken);
            onAnswerRef.current(chatRes, spoken);
          } else if (msg.type === "tts_audio") {
            const bytes = Uint8Array.from(atob(msg.audio_b64), (c) =>
              c.charCodeAt(0)
            );
            const blob = new Blob([bytes], { type: msg.mime || "audio/wav" });
            const url = URL.createObjectURL(blob);
            stopAudioPlayback();
            const audio = new Audio(url);
            audioElRef.current = audio;
            setVState("speaking");
            audio.onended = () => {
              URL.revokeObjectURL(url);
              setVState(handsFreeActiveRef.current ? "listening" : "idle");
            };
            audio.play().catch(() => {
              setVState(handsFreeActiveRef.current ? "listening" : "idle");
            });
          } else if (msg.type === "tts_fallback") {
            speakWithBrowserFallback(msg.text || "");
          } else if (msg.type === "interrupted") {
            stopAudioPlayback();
            setVState(handsFreeActiveRef.current ? "listening" : "idle");
          } else if (msg.type === "error") {
            setErrorMsg(msg.message || "Voice processing error");
            setVState("error");
          }
        } catch {
          // ignore malformed frames
        }
      };
    });
  }, [
    conversationId,
    mission,
    selectorMode,
    setVState,
    speakWithBrowserFallback,
    stopAudioPlayback,
  ]);

  // Detect active server voice capabilities on mount
  useEffect(() => {
    let mounted = true;
    api
      .voiceCapabilities()
      .then((cap) => {
        if (!mounted) return;
        if (cap.server_stt_engine === "sarvam" || cap.server_tts_engine === "sarvam") {
          setEngineBadge("Sarvam AI Voice");
        } else if (cap.server_stt_engine) {
          setEngineBadge(`WS / ${cap.server_stt_engine}`);
        }
      })
      .catch(() => {
        // keep default
      });
    return () => {
      mounted = false;
    };
  }, []);

  // Sync updated conversation/mission/selector settings to open WS
  useEffect(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: "config",
          conversation_id: conversationId,
          mission: mission || null,
          selector_mode: selectorMode || null,
        })
      );
    }
  }, [conversationId, mission, selectorMode]);

  const interrupt = useCallback(() => {
    stopAudioPlayback();
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // ignore
      }
      recognitionRef.current = null;
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "interrupt" }));
    }
    setVState(handsFreeActiveRef.current ? "listening" : "idle");
  }, [setVState, stopAudioPlayback]);

  const startBrowserSpeechFallback = useCallback(() => {
    const SpeechRec =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;
    if (!SpeechRec) {
      setErrorMsg("Server STT unavailable and browser Web Speech API unsupported.");
      setVState("error");
      return;
    }
    setEngineBadge("Web Speech API -> WS RAG");
    const rec: SpeechRecognitionLike = new SpeechRec();
    rec.lang = "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    let finalSent = false;

    rec.onresult = async (ev: any) => {
      let interim = "";
      let finalStr = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const res = ev.results[i];
        if (res.isFinal) {
          finalStr += res[0].transcript;
        } else {
          interim += res[0].transcript;
        }
      }
      setLiveTranscript((finalStr || interim).trim());
      if (finalStr.trim() && !finalSent) {
        finalSent = true;
        setVState("thinking");
        try {
          const ws = await ensureSocket();
          ws.send(
            JSON.stringify({ type: "transcript_text", text: finalStr.trim() })
          );
        } catch {
          setErrorMsg("Failed to send transcript over WebSocket.");
          setVState("error");
        }
      }
    };
    rec.onerror = () => {
      setVState("idle");
    };
    rec.onend = () => {
      recognitionRef.current = null;
      if (voiceStateRef.current === "listening") {
        setVState("idle");
      }
    };
    recognitionRef.current = rec;
    setVState("listening");
    rec.start();
  }, [ensureSocket, setVState]);

  const stopMediaCapture = useCallback((sendEndOfSpeech: boolean) => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    setWaveformLevels(Array.from({ length: 12 }, () => 0.12));

    const rec = mediaRecorderRef.current;
    if (rec && rec.state !== "inactive") {
      rec.onstop = () => {
        if (
          sendEndOfSpeech &&
          wsRef.current &&
          wsRef.current.readyState === WebSocket.OPEN
        ) {
          wsRef.current.send(JSON.stringify({ type: "end_of_speech", suffix: ".webm" }));
        }
      };
      rec.stop();
    } else if (
      sendEndOfSpeech &&
      wsRef.current &&
      wsRef.current.readyState === WebSocket.OPEN
    ) {
      wsRef.current.send(JSON.stringify({ type: "end_of_speech", suffix: ".webm" }));
    }
    mediaRecorderRef.current = null;

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => undefined);
      audioCtxRef.current = null;
    }
  }, []);

  const startRecordingUtterance = useCallback(
    async (isHandsFreeMonitor = false) => {
      setErrorMsg(null);
      // Barge-in immediately if assistant is currently speaking
      if (voiceStateRef.current === "speaking") {
        interrupt();
      }

      try {
        const ws = await ensureSocket();
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        streamRef.current = stream;

        const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm";
        const recorder = new MediaRecorder(stream, { mimeType });
        mediaRecorderRef.current = recorder;

        recorder.ondataavailable = async (ev) => {
          if (ev.data.size > 0 && ws.readyState === WebSocket.OPEN) {
            const buf = await ev.data.arrayBuffer();
            ws.send(buf);
          }
        };
        recorder.start(250);
        setVState("listening");
        setLiveTranscript("");

        // Web Audio analyser for live waveform & hands-free VAD + barge-in
        const audioCtx = new AudioContext();
        audioCtxRef.current = audioCtx;
        const src = audioCtx.createMediaStreamSource(stream);
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 64;
        src.connect(analyser);
        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        speechActiveRef.current = false;
        silenceStartRef.current = 0;

        const tick = () => {
          if (!audioCtxRef.current) return;
          analyser.getByteTimeDomainData(dataArray);
          let sumSq = 0;
          for (let i = 0; i < dataArray.length; i++) {
            const norm = (dataArray[i] - 128) / 128;
            sumSq += norm * norm;
          }
          const rms = Math.sqrt(sumSq / dataArray.length);
          const bars = Array.from({ length: 12 }, (_, idx) => {
            const freqVal = dataArray[(idx * 2) % dataArray.length] / 255;
            return Math.min(1, Math.max(0.12, rms * 3.5 + freqVal * 0.3));
          });
          setWaveformLevels(bars);

          if (isHandsFreeMonitor && handsFreeActiveRef.current) {
            const now = performance.now();
            if (rms > 0.04) {
              if (voiceStateRef.current === "speaking") {
                // Automatic hands-free barge-in!
                interrupt();
              }
              speechActiveRef.current = true;
              silenceStartRef.current = 0;
            } else if (speechActiveRef.current) {
              if (silenceStartRef.current === 0) {
                silenceStartRef.current = now;
              } else if (now - silenceStartRef.current > 1150) {
                speechActiveRef.current = false;
                silenceStartRef.current = 0;
                stopMediaCapture(true);
                setVState("transcribing");
                // Re-arm hands-free listener after short pause
                setTimeout(() => {
                  if (handsFreeActiveRef.current && voiceStateRef.current !== "listening") {
                    startRecordingUtterance(true);
                  }
                }, 400);
                return;
              }
            }
          }

          rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
      } catch (err) {
        setErrorMsg(
          err instanceof Error
            ? `Microphone/WS unavailable: ${err.message}`
            : "Microphone access denied."
        );
        setVState("error");
      }
    },
    [ensureSocket, interrupt, setVState, stopMediaCapture]
  );

  const startPushToTalk = useCallback(() => {
    handsFreeActiveRef.current = false;
    setMode("ptt");
    startRecordingUtterance(false);
  }, [startRecordingUtterance]);

  const stopPushToTalk = useCallback(() => {
    if (voiceStateRef.current === "listening") {
      setVState("transcribing");
      stopMediaCapture(true);
    }
  }, [setVState, stopMediaCapture]);

  const toggleHandsFree = useCallback(() => {
    if (handsFreeActiveRef.current) {
      handsFreeActiveRef.current = false;
      stopMediaCapture(false);
      interrupt();
      setVState("idle");
    } else {
      handsFreeActiveRef.current = true;
      setMode("handsfree");
      startRecordingUtterance(true);
    }
  }, [interrupt, setVState, startRecordingUtterance, stopMediaCapture]);

  useEffect(() => {
    return () => {
      handsFreeActiveRef.current = false;
      stopMediaCapture(false);
      stopAudioPlayback();
      wsRef.current?.close();
    };
  }, [stopAudioPlayback, stopMediaCapture]);

  return {
    mode,
    setMode,
    voiceState,
    liveTranscript,
    spokenCaption,
    engineBadge,
    waveformLevels,
    errorMsg,
    startPushToTalk,
    stopPushToTalk,
    toggleHandsFree,
    interrupt,
    speakWithBrowserFallback,
  };
}
