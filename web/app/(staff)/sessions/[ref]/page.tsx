"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AuditTrail, PageHeader } from "@/components/ui";
import { SessionPanel } from "@/components/SessionPanel";

/** A session on its own page, for links that point straight at it. The list opens it under its row. */
export default function SessionRegister() {
  const { ref } = useParams<{ ref: string }>();
  return (
    <>
      <div className="row"><Link href="/sessions" className="small"><i className="fas fa-arrow-left" aria-hidden /> All sessions</Link></div>
      <PageHeader lead={ref} />
      <section className="card" style={{ padding: 16 }}><SessionPanel code={ref} /></section>
      <AuditTrail screen="sessions" />
    </>
  );
}
