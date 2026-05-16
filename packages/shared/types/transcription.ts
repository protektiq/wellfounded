/** Interview upload and transcript status (mirrors backend Pydantic models). */

export type SourceLanguage = "es" | "zh" | "fr" | "ht" | "ti" | "prs";

export type TranscriptionStatus = "pending" | "processing" | "complete" | "failed";

export type TranscriptStatus = "pending" | "processing" | "complete" | "failed";

export interface TranscriptSegment {
  start: number;
  end: number;
  speaker: string;
  source_text: string;
  english_text: string;
}

export interface InterviewUploadResponse {
  interview_audio_id: string;
  transcript_id: string;
  status: TranscriptionStatus;
}

export interface InterviewAudioOut {
  id: string;
  case_id: string;
  source_filename: string;
  source_language: SourceLanguage;
  duration_seconds: number;
  transcription_status: TranscriptionStatus;
  error_message: string | null;
  uploaded_at: string;
  transcript_id: string | null;
}

export interface TranscriptDetailOut {
  id: string;
  case_id: string;
  interview_audio_id: string | null;
  status: TranscriptStatus;
  source_language: SourceLanguage;
  segments: TranscriptSegment[] | null;
  full_source_text: string | null;
  full_english_text: string | null;
  model_version: string | null;
  completed_at: string | null;
  error_message: string | null;
  created_at: string;
}
