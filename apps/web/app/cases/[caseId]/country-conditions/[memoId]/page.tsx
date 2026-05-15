import { notFound } from "next/navigation";
import { z } from "zod";

import { MemoDetailClient } from "@/components/country-conditions/memo-detail-client";
import {
  finalMemoOutputSchema,
  parseMemoDetail,
} from "@/lib/cc-schemas";
import { serverFetchJsonOrRedirect } from "@/lib/server-api";

const _uuidParam = z.string().length(36).regex(
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/,
);

export default async function CountryConditionsMemoPage({
  params,
}: Readonly<{
  params: Promise<{ caseId: string; memoId: string }>;
}>) {
  const { caseId, memoId } = await params;
  if (!_uuidParam.safeParse(caseId).success || !_uuidParam.safeParse(memoId).success) {
    notFound();
  }
  const res = await serverFetchJsonOrRedirect(
    `/cases/${caseId}/country-conditions/${memoId}`,
  );
  if (res.status === 404) {
    notFound();
  }
  if (!res.ok) {
    throw new Error(`Memo request failed (${res.status})`);
  }
  const memo = parseMemoDetail(await res.json());
  const finalParsed =
    memo.status === "complete" && memo.output !== null
      ? finalMemoOutputSchema.safeParse(memo.output)
      : null;
  const finalMemo = finalParsed?.success === true ? finalParsed.data : null;

  return (
    <div>
      <div className="mb-8 border-b border-border/70 pb-6">
        <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
          Country conditions
        </p>
        <h1
          className="mt-1 text-3xl font-medium tracking-tight text-foreground"
          style={{
            fontFamily: "var(--font-display), ui-serif, Georgia, serif",
          }}
        >
          Memo version {memo.version}
        </h1>
      </div>
      <MemoDetailClient
        caseId={caseId}
        memoId={memoId}
        memo={memo}
        finalMemo={finalMemo}
      />
    </div>
  );
}
