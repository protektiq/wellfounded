import { z } from "zod";

const _UUID_RE =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

const uuidString = z
  .string()
  .min(36)
  .max(36)
  .regex(_UUID_RE, "invalid uuid");

export const sourceLanguageSchema = z.enum([
  "es",
  "zh",
  "fr",
  "ht",
  "ti",
  "prs",
]);

export const declarationDraftStatusSchema = z.enum([
  "pending",
  "generating",
  "draft_ready",
  "flags_unresolved",
  "ready_for_review",
  "finalized",
  "failed",
]);

export const declarationFlagTypeSchema = z.enum([
  "GAP",
  "INFERENCE",
  "INCONSISTENCY",
  "AMBIGUITY",
  "TRANSLATION_UNCERTAINTY",
]);

export const declarationFlagStatusSchema = z.enum([
  "open",
  "resolved",
  "deferred",
]);

export const flagSpanSchema = z.object({
  start: z.number().int().min(0),
  end: z.number().int().min(0),
});

export const declarationFlagSchema = z.object({
  id: uuidString,
  type: declarationFlagTypeSchema,
  paragraph_id: z.string().min(1).max(256),
  span: flagSpanSchema,
  description: z.string().min(1).max(16_384),
  suggested_resolution: z.string().min(1).max(16_384),
  status: declarationFlagStatusSchema,
  resolved_by_user_id: uuidString.nullable(),
  resolved_at: z.string().nullable(),
  resolution_note: z.string().nullable(),
  element_key: z.string().nullable(),
  prior_statement_id: uuidString.nullable(),
  transcript_quote: z.string().nullable(),
  prior_quote: z.string().nullable(),
});

export const inferenceSpanSchema = z.object({
  start: z.number().int().min(0),
  end: z.number().int().min(0),
  rationale: z.string().min(1).max(4096),
});

export const declarationParagraphSchema = z.object({
  id: z.string().min(1).max(256),
  text: z.string().min(1).max(32_768),
  source_segment_ids: z.array(z.string().max(128)).max(256),
  inference_spans: z.array(inferenceSpanSchema).max(64),
});

export const declarationSectionSchema = z.object({
  section_id: z.string().min(1).max(128),
  paragraphs: z.array(declarationParagraphSchema).max(256),
});

export const declarationDraftContentSchema = z.object({
  sections: z.record(z.string(), declarationSectionSchema),
});

export const declarationDraftSummarySchema = z.object({
  id: uuidString,
  case_id: uuidString,
  version: z.number().int().min(1).max(9999),
  status: declarationDraftStatusSchema,
  created_at: z.string().min(1).max(128),
});

export const declarationDraftDetailSchema = z.object({
  id: uuidString,
  case_id: uuidString,
  version: z.number().int().min(1).max(9999),
  status: declarationDraftStatusSchema,
  transcript_id: uuidString,
  interview_audio_id: uuidString.nullable(),
  prior_statement_ids: z.array(uuidString).max(32),
  draft: declarationDraftContentSchema.nullable(),
  flags: z.array(declarationFlagSchema).max(512),
  claim_ir: z.record(z.string(), z.unknown()).nullable(),
  created_at: z.string().min(1).max(128),
  finalized_at: z.string().nullable(),
  error_message: z.string().nullable(),
});

export const transcriptSegmentSchema = z.object({
  start: z.number().min(0),
  end: z.number().min(0),
  speaker: z.string().min(1).max(64),
  source_text: z.string().max(16_384),
  english_text: z.string().max(16_384),
});

export const transcriptDetailSchema = z.object({
  id: uuidString,
  case_id: uuidString,
  interview_audio_id: uuidString.nullable(),
  status: z.enum(["pending", "processing", "complete", "failed"]),
  source_language: sourceLanguageSchema,
  segments: z.array(transcriptSegmentSchema).nullable(),
  full_source_text: z.string().nullable(),
  full_english_text: z.string().nullable(),
  model_version: z.string().nullable(),
  completed_at: z.string().nullable(),
  error_message: z.string().nullable(),
  created_at: z.string().min(1).max(128),
});

export const interviewAudioSummarySchema = z.object({
  id: uuidString,
  case_id: uuidString,
  source_filename: z.string().min(1).max(512),
  source_language: sourceLanguageSchema,
  duration_seconds: z.number().min(0),
  transcription_status: z.enum([
    "pending",
    "processing",
    "complete",
    "failed",
  ]),
  uploaded_at: z.string().min(1).max(128),
  transcript_id: uuidString.nullable(),
});

export type DeclarationDraftDetail = z.infer<typeof declarationDraftDetailSchema>;
export type DeclarationDraftSummary = z.infer<typeof declarationDraftSummarySchema>;
export type DeclarationFlag = z.infer<typeof declarationFlagSchema>;
export type DeclarationDraftContent = z.infer<typeof declarationDraftContentSchema>;
export type TranscriptDetail = z.infer<typeof transcriptDetailSchema>;
export type InterviewAudioSummary = z.infer<typeof interviewAudioSummarySchema>;
export type SourceLanguage = z.infer<typeof sourceLanguageSchema>;

export const parseDeclarationDraftSummaries = (
  data: unknown,
): DeclarationDraftSummary[] => {
  const arr = z.array(declarationDraftSummarySchema).parse(data);
  return arr;
};

export const parseDeclarationDetail = (data: unknown): DeclarationDraftDetail => {
  return declarationDraftDetailSchema.parse(data);
};

export const parseTranscriptDetail = (data: unknown): TranscriptDetail => {
  return transcriptDetailSchema.parse(data);
};

export const parseInterviewSummaries = (
  data: unknown,
): InterviewAudioSummary[] => {
  return z.array(interviewAudioSummarySchema).parse(data);
};

export const REQUIRED_CLEAN_EXPORT_TYPES = new Set([
  "GAP",
  "INFERENCE",
  "INCONSISTENCY",
]);

export const unresolvedRequiredFlagIds = (
  flags: DeclarationFlag[],
): string[] => {
  return flags
    .filter(
      (f) =>
        f.status === "open" && REQUIRED_CLEAN_EXPORT_TYPES.has(f.type),
    )
    .map((f) => f.id);
};

export const statusPillLabel = (status: string, finalizedAt: string | null): string => {
  if (finalizedAt !== null || status === "finalized") {
    return "Finalized";
  }
  if (status === "pending" || status === "generating") {
    return "Drafting";
  }
  if (status === "flags_unresolved") {
    return "Flags unresolved";
  }
  if (status === "draft_ready" || status === "ready_for_review") {
    return "Ready for review";
  }
  if (status === "failed") {
    return "Failed";
  }
  return status.replaceAll("_", " ");
};

export const SECTION_LABELS: Record<string, string> = {
  identity_background: "Identity and background",
  past_persecution: "Past persecution",
  perpetrator_motivation: "Perpetrator and motivation",
  well_founded_fear_future: "Well-founded fear of future harm",
  internal_relocation: "Internal relocation",
  filing_bar_facts: "One-year filing bar facts",
};

export const SECTION_ORDER = [
  "identity_background",
  "past_persecution",
  "perpetrator_motivation",
  "well_founded_fear_future",
  "internal_relocation",
  "filing_bar_facts",
] as const;

export const statusBadgeVariant = (
  status: string,
): "default" | "secondary" | "destructive" | "outline" => {
  if (status === "draft_ready" || status === "ready_for_review" || status === "finalized") {
    return "default";
  }
  if (status === "failed") {
    return "destructive";
  }
  if (status === "flags_unresolved") {
    return "outline";
  }
  return "secondary";
};
