import { notFound } from "next/navigation";
import { z } from "zod";

import { DeclarationDetailClient } from "@/components/declarations/declaration-detail-client";
import {
  parseDeclarationDetail,
  parseTranscriptDetail,
} from "@/lib/declaration-schemas";
import { serverFetchJsonOrRedirect } from "@/lib/server-api";

const _uuidParam = z.string().length(36).regex(
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/,
);

export default async function DeclarationDetailPage({
  params,
}: Readonly<{
  params: Promise<{ caseId: string; draftId: string }>;
}>) {
  const { caseId, draftId } = await params;
  if (
    !_uuidParam.safeParse(caseId).success ||
    !_uuidParam.safeParse(draftId).success
  ) {
    notFound();
  }

  const draftRes = await serverFetchJsonOrRedirect(
    `/cases/${caseId}/declarations/${draftId}`,
  );
  if (draftRes.status === 404) {
    notFound();
  }
  if (!draftRes.ok) {
    throw new Error(`Declaration detail failed (${draftRes.status})`);
  }
  const detail = parseDeclarationDetail(await draftRes.json());

  let transcript = null;
  if (detail.transcript_id.length > 0) {
    const txRes = await serverFetchJsonOrRedirect(
      `/cases/${caseId}/transcripts/${detail.transcript_id}`,
    );
    if (txRes.ok) {
      transcript = parseTranscriptDetail(await txRes.json());
    }
  }

  return (
    <DeclarationDetailClient
      caseId={caseId}
      draftId={draftId}
      detail={detail}
      transcript={transcript}
    />
  );
}
