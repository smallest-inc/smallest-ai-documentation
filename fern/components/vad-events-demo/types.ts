// Shared types for the VAD events interactive demo.

export type SpeechEvent = {
  type: "speech_started" | "speech_ended";
  timestamp: number;
  session_id: string;
};

export type TranscriptEvent = {
  type: "transcription";
  transcript: string;
  is_final: boolean;
  is_last?: boolean;
  session_id: string;
  timestamp_est: number;
};

export type AnyEvent = SpeechEvent | TranscriptEvent;

export type Fixture = {
  name: string;
  audio: string;
  duration_s: number;
  sample_rate: number;
  waveform: number[];
  events: AnyEvent[];
};
