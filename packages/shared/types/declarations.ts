/** Declaration drafting types (mirrors backend Pydantic models). */

import type { SourceLanguage } from "./transcription";

export type DeclarationDraftStatus =
  | "pending"
  | "generating"
  | "draft_ready"
  | "flags_unresolved"
  | "ready_for_review"
  | "finalized"
  | "failed";

export type DeclarationFlagType =
  | "GAP"
  | "INFERENCE"
  | "INCONSISTENCY"
  | "AMBIGUITY"
  | "TRANSLATION_UNCERTAINTY";

export type DeclarationFlagStatus = "open" | "resolved" | "deferred";

export type PriorStatementType =
  | "credible_fear_interview"
  | "airport_statement"
  | "other";

export interface FlagSpan {
  start: number;
  end: number;
}

export interface DeclarationFlag {
  id: string;
  type: DeclarationFlagType;
  paragraph_id: string;
  span: FlagSpan;
  description: string;
  suggested_resolution: string;
  status: DeclarationFlagStatus;
  resolved_by_user_id: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  element_key: string | null;
  prior_statement_id: string | null;
  transcript_quote: string | null;
  prior_quote: string | null;
}

export interface InferenceSpan {
  start: number;
  end: number;
  rationale: string;
}

export interface DeclarationParagraph {
  id: string;
  text: string;
  source_segment_ids: string[];
  inference_spans: InferenceSpan[];
}

export interface DeclarationSection {
  section_id: string;
  paragraphs: DeclarationParagraph[];
}

export interface DeclarationDraftContent {
  sections: Record<string, DeclarationSection>;
}

export interface DeclarationDraftSummary {
  id: string;
  case_id: string;
  version: number;
  status: DeclarationDraftStatus;
  created_at: string;
}

export interface DeclarationDraftDetail {
  id: string;
  case_id: string;
  version: number;
  status: DeclarationDraftStatus;
  transcript_id: string;
  interview_audio_id: string | null;
  prior_statement_ids: string[];
  draft: DeclarationDraftContent | null;
  flags: DeclarationFlag[];
  claim_ir: Record<string, unknown> | null;
  created_at: string;
  finalized_at: string | null;
  error_message: string | null;
}

export interface DeclarationGenerateRequest {
  transcript_id: string;
  prior_statement_ids: string[];
}

export interface DeclarationGenerateResponse {
  draft_id: string;
  version: number;
  status: DeclarationDraftStatus;
}

export interface DeclarationReviseScope {
  paragraph_id?: string;
  section_id?: string;
}

export interface DeclarationReviseRequest {
  instruction: string;
  scope: DeclarationReviseScope;
}

export interface DeclarationReviseResponse {
  draft_id: string;
  version: number;
  status: DeclarationDraftStatus;
}

export interface FlagApplyRequest {
  resolution_text: string;
  status?: "resolved" | "deferred";
}

export interface PriorStatementCreate {
  statement_type: PriorStatementType;
  source_text: string;
  english_text: string;
  source_language: SourceLanguage;
}

export interface PriorStatementOut {
  id: string;
  case_id: string;
  statement_type: PriorStatementType;
  source_text: string;
  english_text: string;
  source_language: SourceLanguage;
  uploaded_at: string;
}

export interface InterviewAudioSummary {
  id: string;
  case_id: string;
  source_filename: string;
  source_language: SourceLanguage;
  duration_seconds: number;
  transcription_status: import("./transcription").TranscriptionStatus;
  uploaded_at: string;
  transcript_id: string | null;
}

export const DECLARATION_SECTION_LABELS: Record<string, string> = {
  identity_background: "Identity and background",
  past_persecution: "Past persecution",
  perpetrator_motivation: "Perpetrator and motivation",
  well_founded_fear_future: "Well-founded fear of future harm",
  internal_relocation: "Internal relocation",
  filing_bar_facts: "One-year filing bar facts",
};

export const REQUIRED_CLEAN_EXPORT_FLAG_TYPES: DeclarationFlagType[] = [
  "GAP",
  "INFERENCE",
  "INCONSISTENCY",
];
