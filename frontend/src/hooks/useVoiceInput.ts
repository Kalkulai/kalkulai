/**
 * useVoiceInput - Azure Speech-to-Text hook for real-time voice input.
 * 
 * This hook provides a secure, token-based connection to Azure Speech Services.
 * The API key is never exposed to the frontend - instead, short-lived tokens
 * are fetched from the backend.
 * 
 * Usage:
 * ```tsx
 * const { 
 *   isListening, 
 *   transcript, 
 *   interimTranscript,
 *   startListening, 
 *   stopListening,
 *   isEnabled,
 *   error 
 * } = useVoiceInput({
 *   language: "de-DE",
 *   onTranscript: (text) => console.log("Final:", text),
 *   onInterim: (text) => console.log("Interim:", text),
 * });
 * ```
 */

import { useState, useCallback, useRef, useEffect } from "react";
import * as SpeechSDK from "microsoft-cognitiveservices-speech-sdk";
import { api } from "@/lib/api";

export interface UseVoiceInputOptions {
  /** Language for speech recognition (default: "de-DE") */
  language?: string;
  /** Callback fired when final transcript is available */
  onTranscript?: (text: string) => void;
  /** Callback fired for interim (partial) results during speech */
  onInterim?: (text: string) => void;
  /** Callback fired when an error occurs */
  onError?: (error: string) => void;
  /** Auto-stop after silence (milliseconds, default: 3000) */
  silenceTimeout?: number;
}

export interface UseVoiceInputReturn {
  /** Whether voice recognition is currently active */
  isListening: boolean;
  /** Final recognized transcript */
  transcript: string;
  /** Interim (partial) transcript while speaking */
  interimTranscript: string;
  /** Start voice recognition */
  startListening: () => Promise<void>;
  /** Stop voice recognition */
  stopListening: () => void;
  /** Whether voice input is available (backend configured) */
  isEnabled: boolean;
  /** Whether we're currently checking if speech is enabled */
  isChecking: boolean;
  /** Current error message, if any */
  error: string | null;
  /** Clear the current transcript */
  clearTranscript: () => void;
}

export function useVoiceInput(options: UseVoiceInputOptions = {}): UseVoiceInputReturn {
  const {
    language = "de-DE",
    onTranscript,
    onInterim,
    onError,
    silenceTimeout = 3000,
  } = options;

  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [isEnabled, setIsEnabled] = useState(false);
  const [isChecking, setIsChecking] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Refs for cleanup
  const recognizerRef = useRef<SpeechSDK.SpeechRecognizer | null>(null);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Check if speech is enabled on mount
  useEffect(() => {
    let mounted = true;
    
    async function checkEnabled() {
      try {
        const config = await api.speechConfig();
        if (mounted) {
          setIsEnabled(config.enabled);
          setIsChecking(false);
        }
      } catch {
        if (mounted) {
          setIsEnabled(false);
          setIsChecking(false);
        }
      }
    }
    
    checkEnabled();
    
    return () => {
      mounted = false;
    };
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognizerRef.current) {
        recognizerRef.current.stopContinuousRecognitionAsync();
        recognizerRef.current.close();
        recognizerRef.current = null;
      }
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
      }
    };
  }, []);

  const clearTranscript = useCallback(() => {
    setTranscript("");
    setInterimTranscript("");
  }, []);

  const stopListening = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }

    if (recognizerRef.current) {
      recognizerRef.current.stopContinuousRecognitionAsync(
        () => {
          recognizerRef.current?.close();
          recognizerRef.current = null;
          setIsListening(false);
        },
        (err) => {
          console.error("Error stopping recognition:", err);
          recognizerRef.current?.close();
          recognizerRef.current = null;
          setIsListening(false);
        }
      );
    } else {
      setIsListening(false);
    }
  }, []);

  const startListening = useCallback(async () => {
    if (isListening) return;
    if (!isEnabled) {
      const errMsg = "Spracherkennung nicht verfügbar";
      setError(errMsg);
      onError?.(errMsg);
      return;
    }

    setError(null);
    setInterimTranscript("");
    
    try {
      // Fetch fresh token from backend
      const tokenResponse = await api.speechToken();
      
      // Create speech config with token (not API key!)
      const speechConfig = SpeechSDK.SpeechConfig.fromAuthorizationToken(
        tokenResponse.token,
        tokenResponse.region
      );
      speechConfig.speechRecognitionLanguage = language;
      
      // Use the default microphone
      const audioConfig = SpeechSDK.AudioConfig.fromDefaultMicrophoneInput();
      
      // Create recognizer
      const recognizer = new SpeechSDK.SpeechRecognizer(speechConfig, audioConfig);
      recognizerRef.current = recognizer;

      // Reset silence timer
      const resetSilenceTimer = () => {
        if (silenceTimerRef.current) {
          clearTimeout(silenceTimerRef.current);
        }
        silenceTimerRef.current = setTimeout(() => {
          stopListening();
        }, silenceTimeout);
      };

      // Handle interim results (while speaking)
      recognizer.recognizing = (_sender, event) => {
        if (event.result.reason === SpeechSDK.ResultReason.RecognizingSpeech) {
          const text = event.result.text;
          setInterimTranscript(text);
          onInterim?.(text);
          resetSilenceTimer();
        }
      };

      // Handle final results
      recognizer.recognized = (_sender, event) => {
        if (event.result.reason === SpeechSDK.ResultReason.RecognizedSpeech) {
          const text = event.result.text;
          if (text) {
            setTranscript((prev) => {
              const newTranscript = prev ? `${prev} ${text}` : text;
              onTranscript?.(newTranscript);
              return newTranscript;
            });
            setInterimTranscript("");
            resetSilenceTimer();
          }
        } else if (event.result.reason === SpeechSDK.ResultReason.NoMatch) {
          // No speech recognized, but keep listening
          resetSilenceTimer();
        }
      };

      // Handle errors
      recognizer.canceled = (_sender, event) => {
        if (event.reason === SpeechSDK.CancellationReason.Error) {
          const errMsg = `Fehler: ${event.errorDetails}`;
          console.error("Speech recognition error:", event.errorDetails);
          setError(errMsg);
          onError?.(errMsg);
        }
        stopListening();
      };

      // Handle session end
      recognizer.sessionStopped = () => {
        stopListening();
      };

      // Start continuous recognition
      setIsListening(true);
      recognizer.startContinuousRecognitionAsync(
        () => {
          resetSilenceTimer();
        },
        (err) => {
          const errMsg = `Konnte Spracherkennung nicht starten: ${err}`;
          console.error(errMsg);
          setError(errMsg);
          onError?.(errMsg);
          setIsListening(false);
        }
      );
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "Unbekannter Fehler";
      console.error("Failed to start voice input:", err);
      setError(errMsg);
      onError?.(errMsg);
      setIsListening(false);
    }
  }, [isListening, isEnabled, language, onTranscript, onInterim, onError, silenceTimeout, stopListening]);

  return {
    isListening,
    transcript,
    interimTranscript,
    startListening,
    stopListening,
    isEnabled,
    isChecking,
    error,
    clearTranscript,
  };
}

export default useVoiceInput;

