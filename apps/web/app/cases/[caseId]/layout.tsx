import { notFound } from "next/navigation";
import { z } from "zod";

import { CaseNav } from "@/components/cases/case-nav";
import { parseCaseDetail } from "@/lib/cc-schemas";
import { serverFetchJsonOrRedirect } from "@/lib/server-api";

const _uuidParam = z.string().length(36).regex(
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/,
);

const basisLabel: Record<string, string> = {
  political_opinion: "Political opinion",
  religion: "Religion",
  particular_social_group: "Particular social group",
  gender_based: "Gender-based",
  race: "Race",
  nationality: "Nationality",
  mixed: "Mixed",
};

export default async function CaseWorkbenchLayout({
  children,
  params,
}: Readonly<{
  children: React.ReactNode;
  params: Promise<{ caseId: string }>;
}>) {
  const { caseId } = await params;
  const idParse = _uuidParam.safeParse(caseId);
  if (!idParse.success) {
    notFound();
  }
  const res = await serverFetchJsonOrRedirect(`/cases/${caseId}`);
  if (res.status === 404) {
    notFound();
  }
  if (!res.ok) {
    throw new Error(`Case request failed with status ${res.status}`);
  }
  const kase = parseCaseDetail(await res.json());
  const basis =
    basisLabel[kase.basis] ?? kase.basis.replaceAll("_", " ");

  return (
    <div className="wf-workbench-shell min-h-screen bg-background">
      <div className="wf-workbench-inner">
        <header className="sticky top-0 z-40 border-b border-border/80 bg-background/90 backdrop-blur-md">
          <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-4 sm:px-6 lg:px-8">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <div>
                <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
                  Case file
                </p>
                <h1
                  className="text-2xl font-medium tracking-tight text-foreground sm:text-3xl"
                  style={{
                    fontFamily: "var(--font-display), ui-serif, Georgia, serif",
                  }}
                >
                  {kase.pseudonym}
                </h1>
              </div>
              <div className="text-right text-sm text-muted-foreground">
                <p>
                  <span className="text-foreground">{kase.country_code}</span>{" "}
                  country code
                </p>
                <p>{basis}</p>
              </div>
            </div>
            <CaseNav caseId={caseId} />
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
