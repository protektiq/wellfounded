"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

import { getApiBaseUrl } from "@/lib/api-base";
import type { TranscriptDetail } from "@/lib/declaration-schemas";
import { cn } from "@/lib/utils";

export type TranscriptAudioHandle = {
  playSegment: (start: number, end: number) => void;
};

type TranscriptAudioPanelProps = {
  caseId: string;
  interviewAudioId: string | null;
  transcript: TranscriptDetail | null;
  onSegmentClick?: (start: number, end: number) => void;
};

const formatTimestamp = (seconds: number): string => {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m)}:${String(s).padStart(2, "0")}`;
};

export const TranscriptAudioPanel = forwardRef<
  TranscriptAudioHandle,
  TranscriptAudioPanelProps
>(function TranscriptAudioPanel(
  { caseId, interviewAudioId, transcript, onSegmentClick },
  ref,
) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const endTimeRef = useRef<number | null>(null);
  const blobUrlRef = useRef<string | null>(null);
  const [audioSrc, setAudioSrc] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (interviewAudioId === null) {
      setAudioSrc(null);
      return;
    }
    let cancelled = false;
    const load = async () => {
      setLoadError(null);
      const r = await fetch(
        `${getApiBaseUrl()}/cases/${caseId}/interviews/${interviewAudioId}/audio`,
        { credentials: "include" },
      );
      if (cancelled) {
        return;
      }
      if (r.status === 401) {
        window.location.href = "/";
        return;
      }
      if (!r.ok) {
        setLoadError("Could not load interview audio.");
        return;
      }
      const blob = await r.blob();
      if (cancelled) {
        return;
      }
      if (blobUrlRef.current !== null) {
        URL.revokeObjectURL(blobUrlRef.current);
      }
      const url = URL.createObjectURL(blob);
      blobUrlRef.current = url;
      setAudioSrc(url);
    };
    void load();
    return () => {
      cancelled = true;
      if (blobUrlRef.current !== null) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    };
  }, [caseId, interviewAudioId]);

  const playSegment = useCallback(
    (start: number, end: number) => {
      const el = audioRef.current;
      if (el === null) {
        return;
      }
      endTimeRef.current = end;
      el.currentTime = start;
      void el.play();
      onSegmentClick?.(start, end);
    },
    [onSegmentClick],
  );

  useImperativeHandle(ref, () => ({ playSegment }), [playSegment]);

  useEffect(() => {
    const el = audioRef.current;
    if (el === null) {
      return;
    }
    const onTimeUpdate = () => {
      const endAt = endTimeRef.current;
      if (endAt !== null && el.currentTime >= endAt) {
        el.pause();
        endTimeRef.current = null;
      }
    };
    el.addEventListener("timeupdate", onTimeUpdate);
    return () => el.removeEventListener("timeupdate", onTimeUpdate);
  }, [audioSrc]);

  if (transcript === null || transcript.segments === null) {
    return null;
  }

  return (
    <div className="rounded-lg border border-border/80 bg-card/50 p-4">
      {audioSrc !== null ? (
        <audio ref={audioRef} src={audioSrc} preload="metadata" className="sr-only">
          <track kind="captions" />
        </audio>
      ) : null}
      <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
        Transcript
      </p>
      {loadError !== null ? (
        <p className="mt-2 text-xs text-destructive">{loadError}</p>
      ) : null}
      <ul className="mt-3 max-h-48 space-y-2 overflow-y-auto text-sm">
        {transcript.segments.map((seg, idx) => (
          <li key={`seg-${String(idx)}`}>
            <button
              type="button"
              disabled={audioSrc === null}
              className={cn(
                "w-full rounded-md border border-transparent px-2 py-1.5 text-left transition-colors",
                audioSrc !== null
                  ? "hover:border-[var(--oxblood)]/30 hover:bg-[var(--oxblood)]/5 focus-visible:ring-2 focus-visible:ring-ring"
                  : "cursor-not-allowed opacity-60",
              )}
              onClick={() => playSegment(seg.start, seg.end)}
              aria-label={`Play transcript from ${formatTimestamp(seg.start)} to ${formatTimestamp(seg.end)}`}
            >
              <span className="font-mono text-xs text-[var(--oxblood)]">
                {formatTimestamp(seg.start)}
              </span>
              <span className="mt-0.5 block text-foreground">{seg.english_text}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
});
