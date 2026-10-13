"use client";

// Contacts and accounts are views of the quotations register now: old links land on it.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Page() {
  const router = useRouter();
  useEffect(() => { router.replace("/quotes"); }, [router]);
  return null;
}
