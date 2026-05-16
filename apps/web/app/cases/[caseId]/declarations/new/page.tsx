import { notFound } from "next/navigation";
import { z } from "zod";

import { NewDeclarationForm } from "@/components/declarations/new-declaration-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { parseInterviewSummaries } from "@/lib/declaration-schemas";
import { serverFetchJsonOrRedirect } from "@/lib/server-api";

const _uuidParam = z.string().length(36).regex(
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/,
);

export default async function NewDeclarationPage({
  params,
}: Readonly<{
  params: Promise<{ caseId: string }>;
}>) {
  const { caseId } = await params;
  if (!_uuidParam.safeParse(caseId).success) {
    notFound();
  }

  const interviewsRes = await serverFetchJsonOrRedirect(
    `/cases/${caseId}/interviews`,
  );
  const interviews =
    interviewsRes.ok
      ? parseInterviewSummaries(await interviewsRes.json())
      : [];

  return (
    <Card className="max-w-2xl border-border/80 shadow-sm">
      <CardHeader>
        <CardTitle
          className="text-lg"
          style={{
            fontFamily: "var(--font-display), ui-serif, Georgia, serif",
          }}
        >
          Request a first draft
        </CardTitle>
      </CardHeader>
      <CardContent>
        <NewDeclarationForm caseId={caseId} interviews={interviews} />
      </CardContent>
    </Card>
  );
}
