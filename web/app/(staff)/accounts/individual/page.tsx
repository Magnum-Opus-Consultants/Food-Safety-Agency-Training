"use client";

// Accounts are now views of the quotations register: old links land on it, filtered.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Page() {
  const router = useRouter();
  useEffect(() => { router.replace("/quotes?view=individual"); }, [router]);
  return null;
}
