"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export const DeclarationStatusPoller = ({ active }: { active: boolean }) => {
  const router = useRouter();
  useEffect(() => {
    if (!active) {
      return;
    }
    const t = setInterval(() => {
      router.refresh();
    }, 2000);
    return () => clearInterval(t);
  }, [active, router]);
  return null;
};
