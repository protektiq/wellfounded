# Wellfounded — MVP Product Requirements Document

**Document version:** 0.9 · Draft for engineering review
**Author:** Founding team
**Status:** Approved for build
**Target launch:** Closed alpha with 3 design partners, T+12 weeks

---

## 1. Overview

Wellfounded is a vertical AI workbench for the affirmative asylum (I-589) practice. The full product comprises four integrated surfaces — country conditions, declaration drafting, evidence packet assembly, and credibility auditing — sharing a single case-file spine.

**This PRD scopes the MVP, which is a deliberately narrow cut: country conditions memo generation, declaration drafting, and the case-file primitive that holds them.** Evidence packet assembly and credibility auditing are deferred to v1.1 and v1.2 respectively. Cutting them is uncomfortable but correct: each requires significant practitioner-validated infrastructure that cannot be rushed.

The MVP exists to answer one question: **does a practitioner-validated, citation-enforced workbench produce drafts that asylum attorneys will pay to use as a starting point for filings?** If the answer is yes, we earn the right to build the rest. If the answer is no, the rest does not matter.

### 1.1 Goals

1. Reduce country conditions research time from 4–8 hours to under 30 minutes of attorney review per case, while maintaining 100% citation faithfulness.
2. Produce client declaration first drafts from interview audio in the client's native language that require 60% less attorney revision time than current ad hoc workflows, while explicitly flagging gaps and inconsistencies for human resolution.
3. Maintain a structured case file that holds intake, country conditions, declaration drafts, and document uploads, with full version history and audit logging.
4. Ship to three design-partner legal aid organizations within 12 weeks of engineering kickoff.

### 1.2 Non-goals

The MVP **does not** include:

- Automated evidence packet assembly with exhibit indexing (v1.1).
- Cross-document credibility audit (v1.2).
- I-589 form auto-population (v1.3).
- Removal defense / EOIR workflows (v2).
- Case management features (calendar, billing, time tracking) — we integrate with Clio, we do not replace it.
- Direct filing with USCIS — Wellfounded produces drafts that attorneys file through existing channels.
- Public client-facing tools — only attorneys and authorized paralegals use the system.
- Mobile native apps — responsive web only.

These deferrals are first-principles: each deferred feature requires more practitioner depth than we have on day one. We earn each by shipping the prior in a defensible state.

---

## 2. Users & Personas

### Primary persona — Asylum staff attorney at a legal aid organization

Daria, 34, staff attorney at a CLINIC-affiliated nonprofit serving an urban metro. Carries a caseload of 40–55 active matters, of which 12–20 are affirmative asylum. Bilingual in English and Spanish, depends on contract interpreters for other languages. Bills against a grant-funded program budget; cannot personally authorize software purchases over $200/month.

Daria's pain is the document-prep treadmill. Country conditions research consumes her Saturday mornings. Declarations get drafted in 3am bursts before filing deadlines. She knows ChatGPT exists, has used it twice, and is privately worried about both the malpractice risk and the bar ethics implications.

She does not need magic. She needs a tool that gives her a credible 80%-complete draft on Monday morning, so she can spend her billable time on the parts that actually require her judgment: client meetings, theory of the case, oral preparation.

### Secondary persona — Director of immigration legal services

Marcus, 47, oversees a four-attorney asylum team at a nonprofit. He buys the software. He needs a tool that demonstrably increases case throughput per attorney, that holds up to a board-level question about AI safety and ethics, that fits a grant budget line, and that he can use to recruit and retain the staff attorneys he is constantly trying to replace.

### Tertiary persona — Asylum clinic student

A second-year law student rotating through a clinic for a semester. Less experienced, supervised by a faculty member. Uses the tool with training wheels: every output reviewed by a supervising attorney before any external use. Critical for adoption signal — students bring tools with them when they graduate — but not the buyer.

---

## 3. User stories

The MVP supports these user stories, in priority order.

### Country conditions

**CC-01.** As an attorney, I can specify a country, a basis of claim (political opinion, religion, particular social group, gender-based, race, nationality), a relevant group description, and a timeframe, and receive a structured country conditions memo within 90 seconds.

**CC-02.** Every factual claim in the memo cites a verifiable source. I can click any citation to view the source passage, the URL of origin, and the date the source was last verified. No claim appears without a citation.

**CC-03.** The memo follows a fixed legal structure: general country conditions, treatment of the relevant group, state actor involvement or inability/unwillingness to control, internal relocation feasibility, recent trend analysis.

**CC-04.** I can request a regeneration of any section with additional guidance ("emphasize evidence post-2024," "include more on rural areas," "address internal flight specifically to the capital region").

**CC-05.** I can export the memo as a styled DOCX file ready to attach as evidence, with a footnote-style bibliography of cited sources.

**CC-06.** As a director, I can see a per-case audit log of which sources were used, when the memo was generated, and which attorney approved it before export.

### Declarations

**DEC-01.** As an attorney, I can upload an audio file (or record directly) of a client interview, identify the client's language, and receive a transcription in the source language and an English translation, with timestamp anchoring to the audio.

**DEC-02.** From a transcribed interview, I can request a first-draft client declaration. The draft is structured around the elements of an asylum claim (identity and background, past persecution, perpetrator and motivation, well-founded fear of future harm, internal relocation, one-year filing bar facts) and written in the first person in the client's voice.

**DEC-03.** The draft includes inline flags wherever (a) the source interview is ambiguous, (b) the model is making an inference rather than reporting client statement, (c) a known prior statement (uploaded credible fear interview, airport statement) differs from the current narrative, or (d) a required element is missing from the source material.

**DEC-04.** No flagged content is silently smoothed. The attorney must resolve each flag (accept, edit, add follow-up question for client meeting) before the draft can be marked complete.

**DEC-05.** I can iterate on the draft with the model, requesting specific changes ("strengthen the nexus paragraph," "remove inferences about the cousin's role," "the client never said this — remove paragraph 12").

**DEC-06.** I can export the declaration as a styled DOCX, with optional inline flag annotations for my own working copy and a clean version for client review.

**DEC-07.** Supported languages at launch: Spanish, Mandarin, French, Haitian Creole, Tigrinya, Dari. Each language is treated as a first-class supported flow with practitioner-validated test cases.

### Case file

**CF-01.** As an attorney, I can create a case file with: client identifier (pseudonymous in MVP — no PII fields), country of origin, basis of claim, filing deadline, asylum office, and intake notes.

**CF-02.** A case file holds all artifacts produced for that case: country conditions memos (versioned), declaration drafts (versioned), uploaded interview audio and transcripts, uploaded prior statements, and any uploaded supporting documents.

**CF-03.** Every artifact has a version history. I can see who generated each version, when, and with what inputs. I can revert to a prior version.

**CF-04.** As a director, I can see all case files within my organization, assign attorneys, and view organization-level activity logs.

**CF-05.** A case file can be archived (read-only) or deleted. Deletion is soft for 30 days with admin recovery, then hard-deleted with no recovery.

---

## 4. Functional Requirements

### 4.1 Country conditions memo generator

**Inputs:**
- Country (ISO 3166 country code)
- Basis of claim (enum: political opinion, religion, particular social group, gender-based, race, nationality, mixed)
- Group description (free text, e.g. "Eritrean journalists who have reported on government detention practices")
- Timeframe (start year, with default of 5 years prior to current date)
- Optional: jurisdiction (asylum office or circuit), to bias toward authority within that jurisdiction

**Source library at launch:**
- US Department of State Country Reports on Human Rights Practices (current + 4 prior years)
- US Commission on International Religious Freedom annual reports
- UNHCR Eligibility Guidelines and country information
- UN Human Rights Council Universal Periodic Review reports
- Human Rights Watch country reports and topical reports
- Amnesty International country reports
- Freedom House Freedom in the World annual reports
- CPJ (Committee to Protect Journalists) — country pages and topical reports
- Refugee Documentation Centre (RDC) packages (Ireland), Country of Origin Information from EUAA
- Curated peer-reviewed academic sources from a maintained allowlist (~200 sources at launch, growing)

**Source library properties:**
- All sources are ingested into a maintained vector store with citation metadata: source name, document title, publication date, page or section anchor, retrieval URL.
- Sources are re-ingested on a 30-day cycle for living documents (State Dept reports), and on publication for academic sources.
- A "last verified" date is shown on every citation in the memo.

**Generation flow (LangGraph):**
1. **Plan step** — given inputs, produce a structured outline of the five required sections, with retrieval queries for each section.
2. **Retrieval step** — for each section, execute retrieval over the source library, returning top-k passages per query with metadata.
3. **Draft step** — for each section, draft prose with citations enforced via structured generation. Every factual sentence must include at least one inline citation token referencing a retrieved passage.
4. **Verification step** — a separate model pass verifies that each cited claim is supported by the cited passage. Unverified claims are removed or rewritten.
5. **Synthesis step** — combine sections, deduplicate citations, generate bibliography, format output.

**Output format:**
- Structured JSON internally, rendered as: web view, downloadable DOCX, downloadable PDF (post-MVP).
- Citations appear as superscript numbers linking to a footnote bibliography.
- Every citation links to the source passage in a side panel for verification.

**Quality bar:**
- Citation faithfulness: 100%. No claim in production output appears without a cited source from the verified library. Hallucinated citations are treated as P0 incidents.
- Length: 1,200–2,000 words for a typical memo. Configurable for shorter or longer.
- Generation time: <90 seconds at the 95th percentile.

### 4.2 Declaration drafter

**Inputs:**
- Audio file (WAV, MP3, M4A, OGG; up to 60 minutes per file, multiple files per case supported) OR text transcript already prepared.
- Source language (from supported set).
- Client metadata from the case file (pseudonymous identifier, country of origin, claim basis).
- Optional: uploaded prior statements (credible fear interview transcript, airport statement, prior I-589 if any) for cross-reference.

**Transcription:**
- Primary: Whisper-large-v3 for transcription with VAD-based diarization. Provider-agnostic — model swap is configurable.
- Multi-speaker handling for attorney-client interviews with interpreters present.
- Output: source-language transcript with speaker labels and timestamps; English translation aligned at the segment level.

**Drafting flow (LangGraph):**
1. **Structured extraction step** — from the transcript, extract: client biographical data, timeline of events, identified persecutors, articulated harms, basis-of-claim elements (protected ground, nexus, well-founded fear), one-year filing bar facts. Stored as a structured intermediate representation.
2. **Gap analysis step** — compare extracted elements to a checklist of required asylum claim elements. Flag missing elements.
3. **Inconsistency check** — if prior statements are provided, identify factual divergences. Flag for human resolution.
4. **Drafting step** — produce a first-person declaration draft in the client's voice, structured around the standard sections, with inline flags rendered as comment-anchored annotations.
5. **Inference highlighting** — every sentence that goes beyond direct client statement (e.g., inferring the year from contextual cues) is highlighted in the working copy.

**Flag taxonomy:**
| Flag type | Meaning | Resolution required before export |
|---|---|---|
| GAP | Required element missing from source | Yes |
| INFERENCE | Model inferred fact not directly stated | Yes |
| INCONSISTENCY | Conflict with prior statement | Yes |
| AMBIGUITY | Source unclear on a point | Recommended |
| TRANSLATION_UNCERTAINTY | Translator-level confidence is low for a passage | Recommended |

**Output format:**
- DOCX with two render modes: "working copy" (flags as comments, inferences highlighted, ambiguities marked) and "clean copy" (no annotations, for client review only after attorney approval).
- Numbered paragraphs in standard declaration format.
- Optional: parallel English / source-language render.

**Quality bar:**
- No flagged content removed during clean-copy export until attorney explicitly resolves each flag.
- Transcription WER (word error rate) target: <8% for supported languages on test corpus.
- Translation BLEU target: ≥35 for supported language pairs on legal-domain test corpus (with caveats — BLEU is imperfect, we also do practitioner review on every release).

### 4.3 Case file primitive

**Data model (logical):**

```
Organization
  └── User (role: admin | attorney | paralegal | student)
  └── Case
       ├── intake_record (client pseudonym, country, basis, deadlines)
       ├── country_conditions_memo[] (versioned)
       ├── declaration_draft[] (versioned)
       ├── uploaded_file[] (audio, transcript, prior statement, evidence)
       └── audit_log_entry[]
```

**Access control:**
- Users belong to one Organization. Cross-organization access is not supported in MVP.
- Within an Organization, roles determine permissions:
  - Admin: full access to all cases, billing, settings.
  - Attorney: full access to assigned cases; read-only on unassigned cases (configurable).
  - Paralegal: read-write on assigned cases, no export of clean-copy declarations.
  - Student: read-write on assigned cases under supervising attorney; supervising attorney must approve every export.
- All actions are audit-logged with user, timestamp, action, and affected artifact.

**Pseudonymity:**
- In MVP, case files use a pseudonymous client identifier (e.g., "M.A. — Eritrea"). Full client names are not stored in Wellfounded's database.
- This is an explicit security and ethics design decision: it reduces blast radius of a breach and removes Wellfounded from the chain of PII for the most sensitive identifier.
- Attorneys map pseudonyms to client identities in their own practice management system or paper file.

---

## 5. Architecture

### 5.1 Stack

- **Orchestration:** LangChain + LangGraph (open source). LangGraph for stateful multi-step flows with human-in-the-loop checkpoints (declaration drafting, country conditions verification).
- **Models:**
  - Primary drafting/reasoning: Anthropic Claude (latest available stable model at build time), via API with Zero Data Retention contract.
  - Embeddings: OpenAI text-embedding-3-large for retrieval index, via ZDR contract.
  - Transcription: Whisper-large-v3, self-hosted on GPU infrastructure for sensitive audio (cost vs. control tradeoff revisited at scale).
  - Translation: NMT model (NLLB-200 or commercial equivalent) for segment-level translation; LLM-level translation review pass.
- **Retrieval:** Vector store (Postgres + pgvector for MVP; revisit Weaviate or LanceDB at scale).
- **Application:** TypeScript / Next.js (React) frontend; Python (FastAPI) backend for orchestration; PostgreSQL for relational data.
- **Document processing:** Azure Document Intelligence for OCR and layout; PyMuPDF for PDF rendering and annotation.
- **DOCX generation:** python-docx with custom asylum-practice templates.
- **Storage:** S3-compatible object storage (audio, uploaded documents, generated artifacts) with per-tenant encryption keys.
- **Hosting:** AWS, single region (us-east-1) at launch; SOC 2 controls implemented from day one.

### 5.2 Key engineering decisions and rationale

**LangGraph over a bespoke orchestration layer.** LangGraph's state-machine model fits the declaration and credibility flows cleanly. The investment in a custom orchestrator does not pay back at MVP scale, and migration off LangGraph at scale is acceptable if needed. Open source dependency is a strategic asset for the AGPL-aware nonprofit buyer segment.

**Pseudonymity over full PII storage.** A breach of a system storing asylum-seeker identities is a worst-case event for clients who may have fled state actors. We engineer to not be that system. This requires accepting a small UX cost (attorneys hold the name-to-pseudonym mapping in their own systems).

**Citation enforcement via structured generation, not post-hoc check.** Every retrieval-grounded section uses constrained generation that emits citation tokens inline. A post-hoc check would catch errors but allow them in early drafts. We treat citation faithfulness as a P0 quality property, not a "nice to have," and engineer accordingly.

**No public training on customer data, ever.** Contractually enforced via ZDR with model providers. Architecturally enforced via per-tenant isolation. Disclosed in the standard terms.

### 5.3 Evaluation infrastructure

We build an internal eval harness from day one:

- **Citation faithfulness eval:** golden-set country conditions queries with expected citation accuracy verified by the practitioner-in-residence. Run on every model release and weekly otherwise.
- **Declaration quality eval:** practitioner-reviewed declarations rated on a 5-point rubric (faithfulness to source, structural completeness, voice authenticity, flag accuracy, legal element coverage). Sample reviewed weekly.
- **Transcription/translation eval:** WER and BLEU on a held-out test corpus per supported language. Re-run on transcription model updates.
- **Regression tracking:** every eval result stored with model version, prompt version, and date. Regressions block release.

---

## 6. Security & Compliance

This work demands a higher security posture than typical SaaS at this stage.

### 6.1 Day-one controls

- TLS 1.3 in transit, AES-256 at rest with per-tenant data encryption keys.
- Authentication via passwordless email magic links + WebAuthn second factor required for admin roles.
- Audit logging of every read and write at the application level, with 12-month retention.
- Encrypted backups daily with 30-day retention; quarterly restore drills.
- Zero data retention contracts with all model providers (Anthropic, OpenAI).
- No training of any internal or external model on customer data, period.
- Data residency: US-only at launch. Region selection at launch for organizations that need it.

### 6.2 Compliance milestones

- **Day 1:** Documented security policies, internal SOC 2 readiness review.
- **Month 6:** SOC 2 Type I report.
- **Month 12:** SOC 2 Type II report. HIPAA Business Associate Agreement availability (some medical records appear in evidence packets and we treat this carefully even pre-evidence-packet feature).
- **Month 18:** State bar opinion or formal AI ethics statement from an outside expert.

### 6.3 Bar and ethics considerations

- The tool is positioned unambiguously as an attorney aid, not legal advice or representation. Every export carries a footer stating that the output is a draft requiring attorney review.
- Engagement with AILA's ethics committee from month 1 to ensure positioning aligns with the evolving AI guidance from state bars.
- Conflict-of-interest checking is out of scope for MVP — we integrate with Clio for this in v1.x.

---

## 7. Success Metrics

### 7.1 Product metrics

| Metric | Target at launch | Target at month 6 |
|---|---|---|
| Country conditions memos generated per active attorney per week | 1.5 | 3 |
| Declaration drafts generated per active attorney per month | 2 | 5 |
| Attorney time saved per case (self-reported via in-app survey) | 6 hours | 10 hours |
| Citation faithfulness (audit sample) | 100% | 100% |
| Cases moved from prep to filed within deadline | n/a (no comparable baseline) | 85% |

### 7.2 Business metrics

| Metric | Target at launch | Target at month 12 |
|---|---|---|
| Paying customers (organizations) | 3 | 25 |
| ARR | $0 (free pilot) | $400K |
| Net revenue retention | n/a | >100% |
| Design partner NPS | >40 | >50 |

### 7.3 Quality and safety metrics

- Zero P0 hallucination incidents in shipped output (defined as a citation that does not exist or does not support its claim).
- Zero security incidents involving customer data.
- 100% of practitioner-in-residence reviews completed weekly.

---

## 8. Risks & Open Questions

### 8.1 Technical risks

**Citation enforcement reliability.** Constrained generation with citation tokens is robust but not perfect. We mitigate with verification pass and practitioner review, but a residual hallucination risk remains. The right answer may be tighter source binding via retrieval-then-extract rather than retrieval-then-generate. Open for prototype testing in week 3.

**Multilingual transcription quality variance.** Whisper-large-v3 has strong English and Spanish performance, acceptable French and Mandarin, and weaker performance on Tigrinya, Dari, and Haitian Creole. We may need to budget for human transcriber review on lower-resource languages at launch, with model-only flow for higher-resource. Practitioner input pending.

**DOCX fidelity for legal formatting.** Attorneys care about formatting more than most SaaS audiences. Bullet-pad pagination, footnote behavior, and table-of-exhibits formatting will require non-trivial template work. Estimated 2 engineer-weeks.

### 8.2 Product risks

**Will attorneys trust a first-draft declaration enough to use it?** This is the single biggest product risk. The mitigation strategy is heavy practitioner-in-residence involvement, public publication of our own eval results, and aggressive flag visibility (we'd rather a draft be obviously incomplete than apparently complete). To be re-evaluated after first three design partners.

**Will the pseudonymity design create unacceptable workflow friction?** Attorneys must hold the name-mapping themselves. If this creates a 3-minute-per-case friction at scale, we may need to revisit. Design partner feedback in weeks 8–12 will tell us.

### 8.3 Open questions

- **Should v1 include a free public country conditions library as a top-of-funnel asset?** Pro: marketing leverage, practitioner credibility. Con: dilutes paid product. Decision: revisit after MVP launch.
- **Voice cloning for declarations?** A declaration in a client's voice could in principle be rendered as audio. This is technically feasible and clearly out of scope on ethical grounds. We will be explicit about not doing this in our product principles.
- **Asylum officer pattern data.** We could build a layer that surfaces patterns from public EOIR data per AO/IJ. Valuable, but adjacent. Defer to v1.3.

---

## 9. MVP Build Plan

### 9.1 Team

- 1 founding technical lead (full-time)
- 1 founding domain lead (asylum attorney, full-time)
- 2 senior engineers (1 backend/orchestration, 1 full-stack frontend)
- 1 design partner manager (part-time month 6+)
- Practitioner-in-residence (part-time, 1 day/week throughout)

### 9.2 12-week build

**Weeks 1–2: Foundation**
- Infrastructure setup (AWS, Postgres, vector store, auth, CI/CD).
- Source library ingestion pipeline. First 50 high-priority sources indexed.
- Domain lead drafts asylum claim element checklist; structural taxonomy of country conditions memo.

**Weeks 3–5: Country conditions vertical**
- LangGraph flow implementation: plan → retrieve → draft → verify → synthesize.
- Citation enforcement via constrained generation.
- DOCX export with footnote bibliography.
- Eval harness v1. First golden-set evaluation.

**Weeks 6–8: Declaration vertical**
- Transcription pipeline (Whisper) with multi-speaker handling.
- Translation pipeline for top 3 supported languages (Spanish, Mandarin, French).
- Structured extraction step. Gap analysis checklist.
- Draft flow with inline flag rendering.
- DOCX export with working/clean modes.

**Weeks 9–10: Case file & UI**
- Case file CRUD with versioning.
- Frontend workbench UI (case list, case detail, country conditions tab, declaration tab).
- Audit logging.
- Pseudonymity controls.

**Weeks 11–12: Hardening & alpha**
- Security audit and penetration test (third-party).
- Practitioner-in-residence final review of every workflow.
- Onboarding documentation for design partners.
- Alpha launch with 3 design partners.

### 9.3 Decision points

- **End of week 5:** if country conditions citation faithfulness is below 99% on golden set, we slip declaration work and harden country conditions first.
- **End of week 8:** if declaration drafting requires more than 40% practitioner revision time on test cases, we delay launch by 2 weeks and revise.
- **End of week 11:** if security audit surfaces any critical finding, we delay alpha launch until resolved.

---

## 10. What we are not solving in MVP, and why

We are explicit about every deferred feature, with rationale:

| Deferred | When | Why deferred |
|---|---|---|
| Evidence packet assembly | v1.1 (month 6) | Requires mature multi-format document ingestion infrastructure and exhibit-indexing taxonomy. Worth doing right. |
| Credibility audit | v1.2 (month 9) | Depends on having country conditions, declarations, and evidence packets in the system. Cannot meaningfully exist without those. |
| I-589 form auto-population | v1.3 (month 12) | Operational, not differentiating. Defer until core workflow proven. |
| Removal defense / EOIR | v2 (month 18) | Adjacent practice area; build after asylum mastery proven. |
| Calendar / case management | Never | Out of scope. We integrate with Clio. |
| Direct USCIS filing | Never | Out of scope. Attorneys file through existing channels. |
| Mobile native apps | Year 2+ | Responsive web suffices for the actual workflow. |
| Client-facing portal | Year 2+ | Asylum clients should communicate with attorneys, not with a software vendor. |

Each deferral is a commitment to not ship the feature until it can ship well.

---

## Appendix A — Glossary

- **I-589** — Application for Asylum and for Withholding of Removal, filed with USCIS for affirmative claims or with EOIR for defensive claims.
- **Affirmative asylum** — Asylum claim filed with USCIS by an applicant not in removal proceedings.
- **CFI (Credible Fear Interview)** — Initial screening interview conducted at the border; transcript often available as a prior statement.
- **PSG (Particular Social Group)** — One of the five protected grounds under the Refugee Act of 1980; legally complex with significant circuit-level variation.
- **Nexus** — The required connection between persecution and a protected ground.
- **One-year bar** — Statutory requirement to file an asylum application within one year of arrival in the US, with limited exceptions.
- **AO** — Asylum Office. USCIS asylum officers conduct affirmative asylum interviews.
- **IJ** — Immigration Judge. Adjudicates defensive asylum claims in immigration court (EOIR).
- **CLINIC** — Catholic Legal Immigration Network, Inc. National network of nonprofit immigration legal service providers.
- **AILA** — American Immigration Lawyers Association.

## Appendix B — Out-of-scope considered carefully

A complete list of things considered for MVP and explicitly rejected, with brief rationale:

- *Real-time interpreter mode.* Tempting but distinct workflow. Defer.
- *Client intake chatbot.* Wrong shape. Attorneys do intakes, not bots.
- *Public country conditions library (free tier).* Maybe. Defer post-MVP.
- *Practice analytics / billing.* Clio's territory.
- *AI-generated client photos or evidence.* Categorically rejected on ethical grounds.
- *Voice synthesis of declarations in client's voice.* Categorically rejected on ethical grounds.

---

**Document end.**
