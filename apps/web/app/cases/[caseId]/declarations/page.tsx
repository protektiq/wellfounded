import Link from "next/link";
import { notFound } from "next/navigation";
import { z } from "zod";

import { buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  parseDeclarationDraftSummaries,
  statusBadgeVariant,
  statusPillLabel,
} from "@/lib/declaration-schemas";
import { serverFetchJsonOrRedirect } from "@/lib/server-api";
import { cn } from "@/lib/utils";

const _uuidParam = z.string().length(36).regex(
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/,
);

export default async function DeclarationsListPage({
  params,
}: Readonly<{
  params: Promise<{ caseId: string }>;
}>) {
  const { caseId } = await params;
  if (!_uuidParam.safeParse(caseId).success) {
    notFound();
  }

  const listRes = await serverFetchJsonOrRedirect(
    `/cases/${caseId}/declarations`,
  );
  if (!listRes.ok) {
    throw new Error(`Declaration list failed (${listRes.status})`);
  }
  const drafts = parseDeclarationDraftSummaries(await listRes.json());

  return (
    <div className="grid gap-8 lg:grid-cols-2">
      <Card className="border-border/80 shadow-sm">
        <CardHeader>
          <CardTitle
            className="text-lg"
            style={{
              fontFamily: "var(--font-display), ui-serif, Georgia, serif",
            }}
          >
            New declaration draft
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-muted-foreground">
            Upload an interview or reuse a transcribed recording, then generate a
            flagged first draft.
          </p>
          <Link
            href={`/cases/${caseId}/declarations/new`}
            className={cn(buttonVariants({ variant: "default" }))}
          >
            Start guided flow
          </Link>
        </CardContent>
      </Card>

      <div>
        <h2
          className="mb-4 text-lg font-medium text-foreground"
          style={{
            fontFamily: "var(--font-display), ui-serif, Georgia, serif",
          }}
        >
          Versions
        </h2>
        {drafts.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No declaration drafts yet.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {drafts.map((d) => (
              <li key={d.id}>
                <Link
                  href={`/cases/${caseId}/declarations/${d.id}`}
                  className="block rounded-lg border border-border/80 bg-card p-4 transition-colors hover:border-[var(--oxblood)]/40 hover:bg-card/90"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-foreground">
                      Version {d.version}
                    </span>
                    <Badge variant={statusBadgeVariant(d.status)}>
                      {statusPillLabel(d.status, null)}
                    </Badge>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Created {new Date(d.created_at).toLocaleString()}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
