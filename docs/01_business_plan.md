# Wellfounded

**The case prep workbench for asylum attorneys.**

Business Plan — May 2026

---

## 1. Executive Summary

Wellfounded is a vertical AI workbench that compresses the four most time-consuming, document-heavy phases of an affirmative asylum case (I-589) into a single integrated workflow: country conditions research, client declaration drafting, evidence packet assembly, and cross-document credibility auditing.

The product is built for solo and small-firm immigration attorneys, nonprofit legal aid organizations, and law school asylum clinics — practitioners who handle work of profound human consequence with tooling that has not meaningfully improved in twenty years. A solo attorney who can today complete three asylum cases per year can plausibly complete eight to twelve with Wellfounded, without sacrificing the careful human judgment that asylum cases require.

We target a US TAM of approximately $15M ARR in asylum-only practice, expanding to $50–80M ARR across adjacent humanitarian immigration practice areas (removal defense, U/T-visa, VAWA self-petitions) within five years. The product is built on open-source LangChain and LangGraph, with a deliberately narrow vertical focus that horizontal legal AI players (Harvey, Lawxy, Irys) will not pursue.

The wedge is asylum. The platform is humanitarian immigration. The thesis is that practitioner-specific workflows beat horizontal "AI for legal" tools in every market where the work is sufficiently specialized and the buyers are sufficiently underserved.

---

## 2. The Problem

The US affirmative asylum system processes roughly 150,000–200,000 cases per year through USCIS Asylum Offices, with an additional several hundred thousand defensive cases in immigration court. The work is among the most document-intensive in legal practice:

- **Country conditions research**: each case requires a memo synthesizing State Department reports, USCIRF findings, UNHCR data, Human Rights Watch and Amnesty International reporting, and academic sources — three to eight billable hours per case, often unrecoverable for legal aid attorneys.
- **Client declarations**: drafted from interview notes in languages the attorney often does not speak (Spanish, Mandarin, Tigrinya, Dari, Haitian Creole, Pashto, Russian), structured around five protected grounds and a nexus requirement, requiring iterative revision with the client.
- **Evidence packets**: chaotic intake of phone photos, WhatsApp screenshots, medical records, police reports, and birth certificates — organized into exhibit-indexed packets matched to elements of the claim, with certified translations flagged.
- **Cross-document consistency**: declarations, the I-589 form, prior statements (credible fear interviews, airport statements), and evidence must align. Asylum officer credibility findings are the most common basis for denial.

The practitioners doing this work are systematically under-resourced:

- 80% of US law firms have five or fewer attorneys. 45% of legal professionals are solo practitioners.
- Legal aid organizations operating asylum programs are funded by foundations, EOJ Recognition and Accreditation programs, and individual donors — budgets are constrained and predictable.
- Law school asylum clinics rotate students every semester, losing institutional memory on each handoff.

Existing tooling is a patchwork of Microsoft Word, Dropbox, paid translation services, Google searches for country conditions, and increasingly ChatGPT used in ad hoc ways that practitioners know are unsafe but cannot afford to replace.

The horizontal legal AI market does not serve these practitioners. Harvey is priced at approximately $1,200 per seat per month with a 20-seat minimum and enterprise sales cycles — built for AmLaw 100 firms doing M&A diligence. Tools priced for solos (Irys, Lawxy) are practice-agnostic and do not understand the structural elements of asylum law.

---

## 3. The Product

Wellfounded is a single integrated workbench with four surfaces, organized around the case file as the shared spine:

**1. Country Conditions Memo Generator.** Given a country, claim basis (political opinion, religion, particular social group, gender-based, etc.), and timeframe, produces a cited memo pulling from authoritative sources (State Department, USCIRF, UNHCR, HRW, Amnesty, peer-reviewed academic sources). Structured around the legal elements the memo must address: general conditions, treatment of the relevant group, state actor involvement or inability/unwillingness to control, internal relocation analysis.

**2. Declaration Drafter.** Attorney records or uploads a client interview in the client's language. The system transcribes, translates, and produces a first-draft declaration in the client's voice, structured around the protected grounds and nexus requirement, with flagged inconsistencies, gaps, and follow-up questions for the attorney to resolve with the client before finalizing.

**3. Evidence Packet Assembler.** Ingests a folder of mixed client documents — phone photos, WhatsApp screenshots, medical records, police reports, news clippings — and produces an organized exhibit list with proposed tabs, English summaries, certified translation flags, and a draft exhibit index matched to the elements of the asylum claim each exhibit supports.

**4. Credibility & Consistency Auditor.** Cross-checks the declaration, the I-589 form, prior statements available to the attorney (credible fear interview transcripts, airport statements, prior immigration filings), country conditions memo, and evidence packet for inconsistencies an asylum officer or immigration judge would flag. Produces a resolution memo with suggested paths for each inconsistency (clarify in declaration, address in pre-hearing brief, prepare client testimony, etc.).

The credibility auditor is the keystone — it is the feature that turns three useful tools into a defensible workflow, because it captures the mistakes that lose cases.

**Technical foundation.** Wellfounded is built on open-source LangChain (retrieval, tool orchestration, structured extraction) and LangGraph (stateful multi-step workflows with human-in-the-loop checkpoints). Frontier model access is provider-agnostic, with Anthropic Claude as the default for drafting and reasoning, and OpenAI embeddings for retrieval. Document processing uses commercial OCR (Azure Document Intelligence) plus open-source layout analysis. Translation uses a combination of NMT models and human review for any document entering the official record.

---

## 4. Market & Buyers

We sell into three buyer segments, in deliberate priority order:

**Segment 1 — Nonprofit legal aid organizations (lead wedge).** Approximately 150–300 nonprofit organizations in the US operate dedicated asylum or humanitarian immigration programs (CLINIC affiliates, Catholic Charities affiliates, HIAS partners, Lutheran Immigration and Refugee Service partners, regional refugee resettlement agencies, immigrant rights organizations). They are sophisticated software buyers with grant-funded budgets, real procurement processes, and a clear capacity expansion mandate.

**Segment 2 — Law school asylum and immigration clinics.** Approximately 50–80 active asylum clinics nationally. Lower revenue per account but high strategic value as a training ground — students become tomorrow's practitioners with Wellfounded as their default tool. Sold through clinic directors with academic-pricing tiers.

**Segment 3 — Solo and small-firm immigration attorneys.** AILA membership is approximately 16,000; we estimate 4,500–5,000 practitioners do meaningful asylum work. Hardest segment to sell into (low budgets, no procurement, fragmented buying) but high lifetime value once acquired.

**TAM math (US, asylum-only):**

| Segment | Count | Avg ACV | Subtotal |
|---|---|---|---|
| Solo / small firm | 5,000 attorneys | $2,000/yr | $10.0M |
| Nonprofit legal aid | 250 orgs × 4 attorneys avg | $1,500/seat/yr | $1.5M |
| Law school clinics | 70 clinics | $1,000/yr flat | $0.1M |
| **US asylum-only TAM** | | | **~$11.6M ARR** |

**TAM with adjacent expansion (5-year horizon):**

| Practice area expansion | Incremental TAM |
|---|---|
| Removal defense / EOIR practice | +$25M |
| U-visa / T-visa / VAWA | +$8M |
| Family-based humanitarian | +$5M |
| International (UK, Canada, EU asylum) | +$15M |
| **Total addressable** | **~$65M ARR** |

We are honest that this is not a $1B vertical. It is a defensible $25–40M ARR business at scale, with high mission alignment and a moat built from depth of practice-area expertise. The horizontal players cannot match the workflow specificity. The solo practitioner alternatives cannot match the integration.

---

## 5. Business Model

**Pricing tiers:**

| Tier | Audience | Price |
|---|---|---|
| Per-case | Very low volume practitioners | $79/case (capped at 6 cases) |
| Solo | Solo practitioners | $189/mo, billed annually |
| Small firm | 2–5 attorneys | $169/mo per seat, billed annually |
| Legal aid (501c3) | Nonprofit orgs | $129/mo per seat, billed annually |
| Academic clinic | Law school clinics | $999/year flat per clinic |
| Enterprise | Multi-state nonprofits, 15+ seats | Custom |

**Revenue model.** Pure SaaS subscription. No usage-based pricing in v1 — predictability matters more than maximizing per-customer revenue when selling to grant-funded buyers. Per-case pricing is a deliberate on-ramp for skeptical solos, not a long-term tier.

**Unit economics target (24 months):**
- Solo CAC: $400 via content marketing and AILA channels. LTV at 3-year retention: ~$5,400. LTV/CAC: 13×.
- Legal aid CAC: $4,000 via direct sales and nonprofit network referrals. LTV at 5-year retention: ~$30,000 (6 seats × $1,548 × 3.2 years effective). LTV/CAC: 7.5×.

**Gross margin target.** 75–80% at scale. Primary COGS is model inference, with provider-agnostic architecture allowing us to migrate to lower-cost models as quality permits.

---

## 6. Go-to-Market

**Phase 1 (months 1–9): Wedge through legal aid.**
- Partner with 3 anchor legal aid organizations as design partners at no charge, in exchange for usage data and case studies.
- Speak at CLINIC convening, the AILA annual conference asylum track, and regional nonprofit immigration conferences.
- Build relationships with state-level immigration coalitions (Massachusetts Law Reform Institute, New York Immigration Coalition, etc.).
- Goal: 10 paying legal aid customers, $250K ARR.

**Phase 2 (months 10–18): Expand into law school clinics.**
- Free academic tier for one year for clinics that adopt before semester start, converting to paid in year two.
- Build student-led research collaborations with refugee studies programs (Georgetown CILS, Hastings CGRS, Pennsylvania Penn Carey Toll).
- Use clinic adoption as a credentialing signal for solo segment.
- Goal: 20 clinics, 50 legal aid orgs, $1.2M ARR.

**Phase 3 (months 19–30): Open the solo segment.**
- Content marketing: a public country conditions database (free tier, gated for deep research) as a top-of-funnel asset.
- AILA partnership and member discount.
- Per-case tier launched as the no-commitment trial path.
- Goal: 200 solo attorneys + retention of segment 1 and 2 = $3.5M ARR.

We deliberately do not pursue paid advertising in year one. The buyers are reachable through community channels, and trust matters more than reach in this segment.

---

## 7. Competition

| Competitor | Positioning | Why we win |
|---|---|---|
| **Harvey** | BigLaw enterprise legal AI ($1,200/seat) | Not their market. They will not build asylum workflows. Their pricing alone disqualifies our buyers. |
| **Lawxy / Irys** | Solo/small-firm horizontal legal AI | Practice-agnostic. Cannot match workflow depth in asylum specifically. We compete on outcomes, not features. |
| **ChatGPT / Claude direct** | $20/month general-purpose | The default today, used unsafely. We replace unsafe ad hoc use with a defensible workflow and case file. |
| **Clio / PracticePanther** | Legal practice management | Adjacent, not competitive. We integrate, we do not replace. |
| **CLINIC's CIRS / pro bono platforms** | Nonprofit case management | Complementary. We sell into the same orgs and integrate. |
| **In-house tools** | Larger legal aid orgs sometimes build internal tools | Real risk but addressable; we are cheaper than a one-FTE engineer salary. |

The strategic risk is not from current competitors. It is from a horizontal player adding a "humanitarian immigration template" to a broader product. The defense is workflow depth — by the time a horizontal player ships a template, we have built credibility auditing, multilingual declaration drafting, exhibit indexing, and a country conditions library that took 18 months to mature.

---

## 8. Team & Build Plan

**Founding team (months 0–6).** Two-person founding team: a technical founder with applied LLM systems experience (LangChain/LangGraph, retrieval, evaluation infrastructure), and a domain founder who is a practicing or recently practicing asylum attorney with at least five years of frontline experience. The domain founder is non-negotiable. Without an attorney co-founder, the product will be wrong in ways the team cannot detect.

**Critical early hires (months 6–18):**
- Senior backend engineer (retrieval infrastructure, document processing).
- Full-stack engineer (workbench UI, case file model).
- Practitioner-in-residence: a second asylum attorney, part-time, who reviews every shipped feature against actual case files.
- Customer success lead with legal aid sector background (months 12+).

**Headcount at $3.5M ARR (month 30):** 8–10 FTE.

---

## 9. Milestones

| Month | Milestone |
|---|---|
| 3 | Country conditions memo generator alpha with three design-partner orgs |
| 6 | Evidence packet assembler alpha |
| 9 | First 5 paying customers, all legal aid orgs ($120K ARR) |
| 12 | Declaration drafter beta. Multilingual support for top 6 languages (Spanish, Mandarin, French, Haitian Creole, Tigrinya, Dari) |
| 15 | Credibility auditor beta. Integrated workbench v1. |
| 18 | $1.2M ARR. 50 legal aid orgs + 20 clinics. |
| 24 | Solo tier launched. $2.2M ARR. |
| 30 | $3.5M ARR. Expansion into removal defense practice area begins. |
| 36 | $6M ARR. UK asylum pilot. |

---

## 10. Risks

**Hallucination in legal output.** The highest-stakes risk. Mitigated by: (a) the product produces drafts, never filings — the attorney is always the final author; (b) citation enforcement with verifiable sources; (c) credibility auditor as second-pass safety net; (d) practitioner-in-residence reviewing every shipped behavior. We will publish our own internal accuracy benchmarks and re-run them on every model release.

**Privacy and attorney-client privilege.** Asylum case data is among the most sensitive personal information that exists. Mitigated by: SOC 2 Type II from month 12, zero-retention model API contracts (Anthropic ZDR, OpenAI ZDR), encryption at rest with per-tenant keys, granular data residency options, and a documented data destruction policy.

**Funding environment for legal aid.** A change in federal policy or foundation priorities could compress legal aid budgets. Mitigated by deliberate diversification across segments (solo, clinic, legal aid) and a per-case tier that survives organizational budget cuts.

**Vertical TAM ceiling.** Asylum alone is too small to build a venture-scale business. Mitigated by deliberate adjacent expansion plan into removal defense (largest immigration practice area by volume) and humanitarian petitions, all of which reuse the underlying infrastructure.

**Horizontal AI player encroachment.** Harvey or a horizontal player ships an "asylum template." Mitigated by depth of workflow specificity — the credibility auditor and exhibit indexer are not template features, they are infrastructure that requires deep practice knowledge to build correctly.

**Regulatory risk.** State bar associations or USCIS could issue guidance restricting AI use in immigration practice. Mitigated by proactive engagement with bar associations and AILA's ethics committee, and by positioning the product unambiguously as an attorney tool, not a substitute for representation.

---

## 11. Why now

Three forces converge:

1. **Model capability** has crossed the threshold where structured legal extraction, multilingual transcription and translation, and citation-faithful drafting are reliable enough to ship as production tools, with appropriate human review.
2. **Asylum case volume** has roughly doubled over the past decade and continues to grow, while the supply of immigration attorneys has not kept pace. The capacity gap is structural.
3. **Open-source orchestration** (LangChain, LangGraph) has matured to the point where a small team can build production-grade agentic workflows in months, not years.

The window for a defensible vertical AI workbench in humanitarian immigration is open now and will not stay open for long. By the time a horizontal player decides to enter, the team with 18 months of practitioner depth wins.

---

## 12. Funding

**Seed target: $3M.** 18-month runway to $1.2M ARR and Series A readiness. Use of funds: founding team compensation (40%), engineering hires (35%), security and compliance buildout (10%), go-to-market and design partner program (10%), reserve (5%).

We will pursue mission-aligned investors with vertical AI conviction (Bloomberg Beta, Susa Ventures, Bain Capital Ventures, Coatue's mission-oriented arm, Founders Fund's vertical software thesis) and consider strategic angels from immigration law, legal aid leadership, and refugee policy.
