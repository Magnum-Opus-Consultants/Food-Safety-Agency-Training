"use client";

import { AuditTrail } from "@/components/ui";
import { StubScreen } from "@/components/stubs";

export default function Page() {
  return (
    <>
      <StubScreen slug="data-layer" />
      <AuditTrail />
    </>
  );
}
