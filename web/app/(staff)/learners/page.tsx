"use client";

import { AuditTrail, Hero, LoadError, Loading, Register } from "@/components/ui";
import { useRegister } from "@/lib/hooks";

type Learner = { ref: string; name: string; type: string; organisation: string; hrLinked: boolean; enrolments: string[];
  idNumber: string; studentNumber: string };

export default function LearnerDirectory() {
  const q = useRegister<Learner[]>("/learners");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const rows = q.data.data;
  const count = (t: string) => String(rows.filter((r) => r.type === t).length);
  return (
    <>
      <Hero
        title="One person across both hubs where the learner is an FSA employee."
        statement="A learner may be a public applicant, a corporate delegate, a university student, or an employee whose development plan commissioned the course. Employees link to the HR directory rather than being duplicated."
        stats={[
          { v: count("Public"), l: "Public", c: "Individual applicants" },
          { v: count("Corporate"), l: "Corporate", c: "Delegates of a client" },
          { v: count("University"), l: "University", c: "Placement students" },
          { v: count("Employee"), l: "Employee", c: "Linked to the HR directory" },
        ]}
      />
      <Register rows={rows} rowKey={(r) => r.ref} source={q.data.meta.source as string}
        columns={[
          { key: "ref", label: "Learner", render: (r) => r.ref, mono: true },
          { key: "name", label: "Name", render: (r) => <b>{r.name}</b> },
          { key: "type", label: "Type", render: (r) => r.type },
          { key: "org", label: "Organisation", render: (r) => r.organisation || "—" },
          { key: "id", label: "Identity", render: (r) => <span className={r.idNumber === "Not captured" ? "muted small" : "mono"}>{r.idNumber}</span> },
          { key: "hr", label: "HR directory", render: (r) => (r.hrLinked ? "Linked" : "—") },
          { key: "enr", label: "Enrolments", render: (r) => r.enrolments.map((e) => <div key={e} className="small">{e}</div>) },
        ]} />
      <AuditTrail />
    </>
  );
}
