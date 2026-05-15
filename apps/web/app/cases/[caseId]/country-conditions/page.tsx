import Link from "next/link";
import { notFound } from "next/navigation";
import { z } from "zod";

import { NewMemoForm } from "@/components/country-conditions/new-memo-form";
import {
  parseCaseDetail,
  parseMemoDetail,
  parseMemoSummaries,
} from "@/lib/cc-schemas";
import { serverFetchJsonOrRedirect } from "@/lib/server-api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const _uuidParam = z.string().length(36).regex(
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/,
);

const statusVariant = (
  s: string,
): "default" | "secondary" | "destructive" | "outline" => {
  if (s === "complete") {
    return "default";
  }
  if (s === "failed") {
    return "destructive";
  }
  return "secondary";
};

export default async function CountryConditionsListPage({
  params,
  searchParams,
}: Readonly<{
  params: Promise<{ caseId: string }>;
  searchParams: Promise<{ fromMemo?: string }>;
}>) {
  const { caseId } = await params;
  const sp = await searchParams;
  if (!_uuidParam.safeParse(caseId).success) {
    notFound();
  }

  const [caseRes, listRes] = await Promise.all([
    serverFetchJsonOrRedirect(`/cases/${caseId}`),
    serverFetchJsonOrRedirect(`/cases/${caseId}/country-conditions`),
  ]);
  if (!caseRes.ok) {
    throw new Error(`Case request failed (${caseRes.status})`);
  }
  if (!listRes.ok) {
    throw new Error(`Memo list request failed (${listRes.status})`);
  }
  const kase = parseCaseDetail(await caseRes.json());
  const memos = parseMemoSummaries(await listRes.json());

  let prefill:
    | {
        country_code: string;
        basis: string;
        group_description: string;
        timeframe_start_year: number;
        jurisdiction_asylum_office: string | null;
      }
    | undefined;
  const fromId = sp.fromMemo;
  if (fromId !== undefined && _uuidParam.safeParse(fromId).success) {
    const memoRes = await serverFetchJsonOrRedirect(
      `/cases/${caseId}/country-conditions/${fromId}`,
    );
    if (memoRes.ok) {
      const memo = parseMemoDetail(await memoRes.json());
      const i = memo.inputs;
      prefill = {
        country_code: i.country_code,
        basis: i.basis,
        group_description: i.group_description,
        timeframe_start_year: i.timeframe_start_year,
        jurisdiction_asylum_office: i.jurisdiction_asylum_office,
      };
    }
  }

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
            Request a new memo
          </CardTitle>
        </CardHeader>
        <CardContent>
          <NewMemoForm
            caseId={caseId}
            defaultCountryCode={prefill?.country_code ?? kase.country_code}
            defaultBasis={prefill?.basis ?? kase.basis}
            defaultGroupDescription={
              prefill?.group_description ?? kase.group_description
            }
            defaultYear={prefill?.timeframe_start_year ?? new Date().getFullYear()}
            defaultAsylumOffice={
              prefill?.jurisdiction_asylum_office ?? kase.asylum_office
            }
          />
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
        {memos.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No country conditions memos yet. Submit the form to generate the first
            version.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {memos.map((m) => (
              <li key={m.id}>
                <Link
                  href={`/cases/${caseId}/country-conditions/${m.id}`}
                  className="block rounded-lg border border-border/80 bg-card p-4 transition-colors hover:border-[var(--oxblood)]/40 hover:bg-card/90"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-foreground">
                      Version {m.version}
                    </span>
                    <Badge variant={statusVariant(m.status)}>{m.status}</Badge>
                  </div>
                  {m.generated_at !== null ? (
                    <p className="mt-2 text-xs text-muted-foreground">
                      Generated {new Date(m.generated_at).toLocaleString()}
                    </p>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
