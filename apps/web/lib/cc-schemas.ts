import { z } from "zod";

const _UUID_RE =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

export const claimBasisSchema = z.enum([
  "political_opinion",
  "religion",
  "particular_social_group",
  "gender_based",
  "race",
  "nationality",
  "mixed",
]);

export const asylumOfficeSchema = z.enum([
  "arlington",
  "atlanta",
  "boston",
  "chicago",
  "houston",
  "los_angeles",
  "miami",
  "newark",
  "new_york",
  "new_orleans",
  "philadelphia",
  "san_francisco",
  "seattle",
]);

export const countryConditionsMemoStatusSchema = z.enum([
  "pending",
  "generating",
  "complete",
  "failed",
]);

const uuidString = z
  .string()
  .min(36)
  .max(36)
  .regex(_UUID_RE, "invalid uuid");

export const caseAssignmentSchema = z.object({
  user_id: uuidString,
  role_on_case: z.string().min(1).max(64),
});

export const caseDetailSchema = z.object({
  id: uuidString,
  pseudonym: z.string().min(1).max(512),
  country_code: z.string().length(2),
  basis: claimBasisSchema,
  group_description: z.string().max(16384),
  filing_deadline: z.string().nullable(),
  asylum_office: asylumOfficeSchema.nullable(),
  intake_notes: z.string().max(16384),
  created_by_user_id: uuidString,
  created_at: z.string().min(1).max(128),
  archived_at: z.string().nullable(),
  deleted_at: z.string().nullable(),
  assignments: z.array(caseAssignmentSchema).max(64),
  can_edit: z.boolean(),
});

export const countryConditionsMemoSummarySchema = z.object({
  id: uuidString,
  case_id: uuidString,
  version: z.number().int().min(1).max(9999),
  status: countryConditionsMemoStatusSchema,
  generated_at: z.string().nullable(),
});

export const countryConditionsInputsSchema = z.object({
  country_code: z.string().length(2),
  basis: claimBasisSchema,
  group_description: z.string().min(1).max(16384),
  timeframe_start_year: z.number().int().min(1990).max(2100),
  jurisdiction_asylum_office: asylumOfficeSchema.nullable(),
});

export const citedPassagePayloadSchema = z.object({
  passage_id: uuidString,
  source_family: z.string().min(1).max(64),
  document_title: z.string().min(1).max(512),
  publication_date: z.string().min(8).max(32),
  url: z.string().min(1).max(4096),
  section_anchor: z.string().min(1).max(1024),
  text: z.string().min(1).max(120_000),
});

export const memoSectionSchema = z.object({
  section_id: z.string().min(1).max(128),
  title: z.string().min(1).max(512),
  body: z.string().min(1).max(120_000),
});

export const finalMemoOutputSchema = z.object({
  sections: z.array(memoSectionSchema).length(5),
  bibliography: z.array(z.unknown()),
});

export const countryConditionsMemoDetailSchema = z.object({
  id: uuidString,
  case_id: uuidString,
  version: z.number().int().min(1).max(9999),
  status: countryConditionsMemoStatusSchema,
  inputs: countryConditionsInputsSchema,
  output: z.union([z.null(), z.record(z.string(), z.unknown())]),
  model_versions: z.record(z.string(), z.unknown()),
  error_message: z.string().nullable(),
  generated_at: z.string().nullable(),
  cited_passages: z.array(citedPassagePayloadSchema).max(500),
});

export type CaseDetail = z.infer<typeof caseDetailSchema>;
export type CountryConditionsMemoSummary = z.infer<
  typeof countryConditionsMemoSummarySchema
>;
export type CountryConditionsMemoDetail = z.infer<
  typeof countryConditionsMemoDetailSchema
>;
export type CountryConditionsInputs = z.infer<typeof countryConditionsInputsSchema>;
export type CitedPassagePayload = z.infer<typeof citedPassagePayloadSchema>;
export type FinalMemoOutput = z.infer<typeof finalMemoOutputSchema>;

export const parseCaseDetail = (raw: unknown): CaseDetail =>
  caseDetailSchema.parse(raw);

export const parseMemoSummaries = (raw: unknown): CountryConditionsMemoSummary[] =>
  z.array(countryConditionsMemoSummarySchema).max(200).parse(raw);

export const parseMemoDetail = (raw: unknown): CountryConditionsMemoDetail =>
  countryConditionsMemoDetailSchema.parse(raw);

export const parseFinalMemoOutput = (raw: unknown): FinalMemoOutput =>
  finalMemoOutputSchema.parse(raw);
