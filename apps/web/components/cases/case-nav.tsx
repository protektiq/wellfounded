"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

type CaseNavProps = {
  caseId: string;
};

const linkClass = (active: boolean) =>
  cn(
    "border-b-2 pb-2 text-sm font-medium transition-colors",
    active
      ? "border-[var(--oxblood)] text-[var(--oxblood)]"
      : "border-transparent text-muted-foreground hover:text-foreground",
  );

export const CaseNav = ({ caseId }: CaseNavProps) => {
  const pathname = usePathname();
  const ccActive = pathname.includes("/country-conditions");
  const declActive = pathname.includes("/declarations");

  return (
    <nav aria-label="Case sections" className="flex gap-6 border-t border-border/60 pt-3">
      <Link
        href={`/cases/${caseId}/country-conditions`}
        className={linkClass(ccActive)}
      >
        <span className="mr-1.5 text-xs text-muted-foreground">01</span>
        Country conditions
      </Link>
      <Link
        href={`/cases/${caseId}/declarations`}
        className={linkClass(declActive)}
      >
        <span className="mr-1.5 text-xs text-muted-foreground">02</span>
        Declaration
      </Link>
    </nav>
  );
};
