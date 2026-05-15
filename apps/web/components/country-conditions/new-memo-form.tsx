"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getApiBaseUrl } from "@/lib/api-base";
import { asylumOfficeSchema, claimBasisSchema } from "@/lib/cc-schemas";

const generateBodySchema = z.object({
  country_code: z.string().length(2),
  basis: claimBasisSchema,
  group_description: z.string().min(1).max(16384),
  timeframe_start_year: z.number().int().min(1990).max(2100),
  jurisdiction_asylum_office: asylumOfficeSchema.nullable(),
});

const BASIS_OPTIONS: { value: z.infer<typeof claimBasisSchema>; label: string }[] =
  [
    { value: "political_opinion", label: "Political opinion" },
    { value: "religion", label: "Religion" },
    { value: "particular_social_group", label: "Particular social group" },
    { value: "gender_based", label: "Gender-based" },
    { value: "race", label: "Race" },
    { value: "nationality", label: "Nationality" },
    { value: "mixed", label: "Mixed" },
  ];

const ASYLUM_OPTIONS: { value: z.infer<typeof asylumOfficeSchema>; label: string }[] =
  [
    { value: "arlington", label: "Arlington" },
    { value: "atlanta", label: "Atlanta" },
    { value: "boston", label: "Boston" },
    { value: "chicago", label: "Chicago" },
    { value: "houston", label: "Houston" },
    { value: "los_angeles", label: "Los Angeles" },
    { value: "miami", label: "Miami" },
    { value: "newark", label: "Newark" },
    { value: "new_york", label: "New York" },
    { value: "new_orleans", label: "New Orleans" },
    { value: "philadelphia", label: "Philadelphia" },
    { value: "san_francisco", label: "San Francisco" },
    { value: "seattle", label: "Seattle" },
  ];

type NewMemoFormProps = {
  caseId: string;
  defaultCountryCode: string;
  defaultBasis: string;
  defaultGroupDescription: string;
  defaultYear: number;
  defaultAsylumOffice: string | null;
};

export const NewMemoForm = ({
  caseId,
  defaultCountryCode,
  defaultBasis,
  defaultGroupDescription,
  defaultYear,
  defaultAsylumOffice,
}: NewMemoFormProps) => {
  const router = useRouter();
  const [countryCode, setCountryCode] = useState(
    defaultCountryCode.trim().toUpperCase().slice(0, 2),
  );
  const [basis, setBasis] = useState(() => {
    const parsed = claimBasisSchema.safeParse(defaultBasis);
    return parsed.success ? parsed.data : "political_opinion";
  });
  const [groupDescription, setGroupDescription] = useState(defaultGroupDescription);
  const [year, setYear] = useState(String(defaultYear));
  const [asylum, setAsylum] = useState(defaultAsylumOffice ?? "");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const y = Number.parseInt(year, 10);
    if (!Number.isFinite(y)) {
      setError("Start year must be a number.");
      return;
    }
    const officeRaw = asylum.trim();
    let jurisdictionValue: string | null = null;
    if (officeRaw !== "") {
      const parsedOffice = asylumOfficeSchema.safeParse(officeRaw);
      if (!parsedOffice.success) {
        setError("Select a valid asylum office or leave blank.");
        return;
      }
      jurisdictionValue = parsedOffice.data;
    }
    const bodyRaw = {
      country_code: countryCode.trim().toUpperCase(),
      basis,
      group_description: groupDescription.trim(),
      timeframe_start_year: y,
      jurisdiction_asylum_office: jurisdictionValue,
    };
    const parsed = generateBodySchema.safeParse(bodyRaw);
    if (!parsed.success) {
      setError("Check all fields and try again.");
      return;
    }
    setPending(true);
    try {
      const res = await fetch(
        `${getApiBaseUrl()}/cases/${caseId}/country-conditions`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(parsed.data),
        },
      );
      if (res.status === 401) {
        router.replace("/");
        return;
      }
      if (res.status === 403) {
        setError("You do not have permission to generate a memo for this case.");
        return;
      }
      if (res.status !== 202) {
        let detail = `Request failed (${res.status})`;
        try {
          const j = (await res.json()) as { detail?: unknown };
          if (typeof j.detail === "string") {
            detail = j.detail;
          }
        } catch {
          /* ignore */
        }
        setError(detail);
        return;
      }
      const j = (await res.json()) as { memo_id?: string };
      if (typeof j.memo_id !== "string" || j.memo_id.length > 64) {
        setError("Unexpected response from server.");
        return;
      }
      router.push(`/cases/${caseId}/country-conditions/${j.memo_id}`);
      router.refresh();
    } catch {
      setError("Network error. Check your connection and try again.");
    } finally {
      setPending(false);
    }
  };

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-4">
      <div className="grid gap-2">
        <Label htmlFor="cc-country">Country code (ISO-3166-1 alpha-2)</Label>
        <Input
          id="cc-country"
          maxLength={2}
          value={countryCode}
          onChange={(e) =>
            setCountryCode(e.target.value.toUpperCase().replace(/[^A-Z]/g, ""))
          }
          className="max-w-[8rem] uppercase tracking-widest"
          required
          aria-required
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cc-basis">Basis</Label>
        <select
          id="cc-basis"
          value={basis}
          onChange={(e) => {
            const parsed = claimBasisSchema.safeParse(e.target.value);
            if (parsed.success) setBasis(parsed.data);
          }}
          className="h-9 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          required
          aria-required
        >
          {BASIS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cc-group">Group description</Label>
        <textarea
          id="cc-group"
          value={groupDescription}
          onChange={(e) => setGroupDescription(e.target.value)}
          maxLength={16384}
          rows={4}
          className="min-h-[100px] w-full resize-y rounded-lg border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          required
          aria-required
        />
      </div>
      <div className="grid gap-2 sm:grid-cols-2 sm:gap-4">
        <div className="grid gap-2">
          <Label htmlFor="cc-year">Timeframe start year</Label>
          <Input
            id="cc-year"
            type="number"
            min={1990}
            max={2100}
            value={year}
            onChange={(e) => setYear(e.target.value)}
            required
            aria-required
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="cc-asylum">Jurisdiction asylum office (optional)</Label>
          <select
            id="cc-asylum"
            value={asylum}
            onChange={(e) => setAsylum(e.target.value)}
            className="h-9 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <option value="">None</option>
            {ASYLUM_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      {error !== null ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <Button type="submit" disabled={pending} className="w-fit">
        {pending ? "Submitting" : "Generate memo"}
      </Button>
    </form>
  );
};
