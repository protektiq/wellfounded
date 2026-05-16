"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { getApiBaseUrl } from "@/lib/api-base";
import type {
  InterviewAudioSummary,
  SourceLanguage,
} from "@/lib/declaration-schemas";
import { sourceLanguageSchema } from "@/lib/declaration-schemas";
import { cn } from "@/lib/utils";

const LANGUAGE_OPTIONS: { value: SourceLanguage; label: string }[] = [
  { value: "es", label: "Spanish" },
  { value: "zh", label: "Mandarin" },
  { value: "fr", label: "French" },
  { value: "ht", label: "Haitian Creole" },
  { value: "ti", label: "Tigrinya" },
  { value: "prs", label: "Dari" },
];

type NewDeclarationFormProps = {
  caseId: string;
  interviews: InterviewAudioSummary[];
};

export const NewDeclarationForm = ({
  caseId,
  interviews,
}: NewDeclarationFormProps) => {
  const router = useRouter();
  const [mode, setMode] = useState<"upload" | "existing">(
    interviews.length > 0 ? "existing" : "upload",
  );
  const [sourceLanguage, setSourceLanguage] = useState<SourceLanguage>("es");
  const [selectedAudioId, setSelectedAudioId] = useState(
    interviews[0]?.id ?? "",
  );
  const [priorEnglish, setPriorEnglish] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const pollTranscript = useCallback(
    async (audioId: string): Promise<string | null> => {
      for (let i = 0; i < 120; i += 1) {
        const r = await fetch(
          `${getApiBaseUrl()}/cases/${caseId}/interviews/${audioId}`,
          { credentials: "include" },
        );
        if (!r.ok) {
          return null;
        }
        const body = (await r.json()) as {
          transcription_status?: string;
          transcript_id?: string | null;
        };
        if (
          body.transcription_status === "complete" &&
          typeof body.transcript_id === "string"
        ) {
          return body.transcript_id;
        }
        if (body.transcription_status === "failed") {
          return null;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      return null;
    },
    [caseId],
  );

  const uploadPriorIfNeeded = async (): Promise<string[]> => {
    const trimmed = priorEnglish.trim();
    if (trimmed.length === 0) {
      return [];
    }
    const r = await fetch(`${getApiBaseUrl()}/cases/${caseId}/prior-statements`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        statement_type: "credible_fear_interview",
        source_text: trimmed,
        english_text: trimmed,
        source_language: sourceLanguage,
      }),
    });
    if (!r.ok) {
      throw new Error("Could not upload prior statement.");
    }
    const body = (await r.json()) as { id?: string };
    if (typeof body.id !== "string") {
      throw new Error("Invalid prior statement response.");
    }
    return [body.id];
  };

  const startDraft = async (transcriptId: string, priorIds: string[]) => {
    const r = await fetch(`${getApiBaseUrl()}/cases/${caseId}/declarations`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transcript_id: transcriptId,
        prior_statement_ids: priorIds,
      }),
    });
    if (r.status === 401) {
      window.location.href = "/";
      return;
    }
    if (!r.ok) {
      throw new Error("Could not start declaration generation.");
    }
    const body = (await r.json()) as { draft_id?: string };
    if (typeof body.draft_id !== "string") {
      throw new Error("Invalid draft response.");
    }
    router.push(`/cases/${caseId}/declarations/${body.draft_id}`);
    router.refresh();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setPending(true);
    setStatusMessage(null);
    try {
      const langParsed = sourceLanguageSchema.safeParse(sourceLanguage);
      if (!langParsed.success) {
        setError("Select a valid source language.");
        return;
      }

      let transcriptId: string | null = null;

      if (mode === "existing") {
        if (selectedAudioId.length === 0) {
          setError("Select an interview.");
          return;
        }
        const interview = interviews.find((i) => i.id === selectedAudioId);
        if (interview?.transcript_id !== null && interview?.transcript_id !== undefined) {
          transcriptId = interview.transcript_id;
        } else {
          setStatusMessage("Waiting for transcription to complete...");
          transcriptId = await pollTranscript(selectedAudioId);
        }
      } else {
        if (file === null) {
          setError("Choose an audio file to upload.");
          return;
        }
        setStatusMessage("Uploading interview audio...");
        const form = new FormData();
        form.append("file", file);
        form.append("source_language", langParsed.data);
        const r = await fetch(`${getApiBaseUrl()}/cases/${caseId}/interviews`, {
          method: "POST",
          credentials: "include",
          body: form,
        });
        if (!r.ok) {
          throw new Error("Interview upload failed.");
        }
        const up = (await r.json()) as {
          interview_audio_id?: string;
          transcript_id?: string;
        };
        const audioId = up.interview_audio_id;
        if (typeof audioId !== "string") {
          throw new Error("Invalid upload response.");
        }
        setStatusMessage("Waiting for transcription...");
        transcriptId =
          typeof up.transcript_id === "string"
            ? await pollTranscript(audioId).then((id) => id ?? up.transcript_id ?? null)
            : await pollTranscript(audioId);
      }

      if (transcriptId === null || transcriptId.length === 0) {
        setError("Transcript is not ready. Try again shortly.");
        return;
      }

      setStatusMessage("Starting declaration draft...");
      const priorIds = await uploadPriorIfNeeded();
      await startDraft(transcriptId, priorIds);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setPending(false);
    }
  };

  useEffect(() => {
    if (interviews.length > 0 && selectedAudioId.length === 0) {
      const first = interviews[0];
      if (first !== undefined) {
        setSelectedAudioId(first.id);
      }
    }
  }, [interviews, selectedAudioId]);

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="space-y-5">
      <div className="flex gap-4">
        <Button
          type="button"
          variant={mode === "upload" ? "default" : "outline"}
          onClick={() => setMode("upload")}
        >
          Upload audio
        </Button>
        <Button
          type="button"
          variant={mode === "existing" ? "default" : "outline"}
          disabled={interviews.length === 0}
          onClick={() => setMode("existing")}
        >
          Use prior interview
        </Button>
      </div>

      <div>
        <Label htmlFor="source-language">Source language</Label>
        <select
          id="source-language"
          className="mt-1 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs"
          value={sourceLanguage}
          onChange={(e) => {
            const parsed = sourceLanguageSchema.safeParse(e.target.value);
            if (parsed.success) {
              setSourceLanguage(parsed.data);
            }
          }}
        >
          {LANGUAGE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {mode === "upload" ? (
        <div>
          <Label htmlFor="audio-file">Interview audio</Label>
          <input
            id="audio-file"
            type="file"
            accept="audio/*,.wav,.mp3,.m4a"
            className="mt-1 block w-full text-sm"
            onChange={(e) => {
              const f = e.target.files?.[0];
              setFile(f ?? null);
            }}
          />
        </div>
      ) : (
        <div>
          <Label htmlFor="prior-interview">Interview</Label>
          <select
            id="prior-interview"
            className="mt-1 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs"
            value={selectedAudioId}
            onChange={(e) => setSelectedAudioId(e.target.value)}
          >
            {interviews.map((i) => (
              <option key={i.id} value={i.id}>
                {i.source_filename} ({i.transcription_status})
              </option>
            ))}
          </select>
        </div>
      )}

      <div>
        <Label htmlFor="prior-statement">Prior statement (optional)</Label>
        <Textarea
          id="prior-statement"
          value={priorEnglish}
          onChange={(e) => setPriorEnglish(e.target.value)}
          rows={4}
          className="mt-1"
          placeholder="Paste credible fear interview or airport statement in English..."
        />
      </div>

      {statusMessage !== null ? (
        <p className="text-sm text-muted-foreground">{statusMessage}</p>
      ) : null}
      {error !== null ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}

      <div className="flex gap-3">
        <Button type="submit" disabled={pending}>
          Request first draft
        </Button>
        <Link
          href={`/cases/${caseId}/declarations`}
          className={cn(buttonVariants({ variant: "ghost" }))}
        >
          Cancel
        </Link>
      </div>
    </form>
  );
};
