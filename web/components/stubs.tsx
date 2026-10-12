"use client";

import { Stub } from "@/components/ui";

export const STUBS: Record<string, { title: string; phase: string; body: string[] }> = {
  "management-dashboard": {
    title: "Eleven indicators for the GMs, the same set as the monthly report.",
    phase: "Phase 6 — assurance, reporting and administration",
    body: ["Name, actual, target, variance and tone per indicator, each derived from a register and naming its source.",
      "Training reports into both portfolios: GM Operations (Armand Visagie) and GM Corporate Services (Nicole Bergh), noted by the CEO's office."],
  },
  "monthly-report": {
    title: "The board and GM document, generated from the registers.",
    phase: "Phase 6 — acceptance: prints as clean A4 at letterhead geometry",
    body: ["Document control, position statement, findings, observations and recommendations, the indicator table, prior actions and next-period actions.",
      "Open item for FSA: generate in-app, or fill the Word letterhead template (README open question 5)."],
  },
  contacts: {
    title: "The CRM spine behind demand.",
    phase: "Phase 5 — demand and courses",
    body: ["Contact, organisation, sector, relationship, last activity, open value and position. Enquiries, quotes, registrations and placements hang off the contact, so a change of handler does not lose the history.",
      "The contacts and organisations are already stored; this screen presents them."],
  },
  development: {
    title: "Material projects moving through a five-stage gate.",
    phase: "Phase 5 — demand and courses",
    body: ["Concept and needs analysis, material drafting, internal moderation, manager sign-off, accredited and live.",
      "A project cannot advance while its gate is unmet, and the card names what is outstanding."],
  },
  packs: {
    title: "A pack is composed at runtime, never copied.",
    phase: "Phase 5 — acceptance: editing a template leaves a running instance unchanged",
    body: ["Eight master items plus the extras the course type requires. Each item is held, or not applicable with a recorded reason.",
      "A running instance holds a snapshot of its activity list, keyed on stable activity IDs, never positions."],
  },
  integrations: {
    title: "What is live, what is manual, and what is still to build.",
    phase: "Administration — read-only register",
    body: ["Outlook calendar (write invites, read availability), HPCSA and AgriSETA/SAATCA (manual capture), IMI (read, and write-back held until the record owner is agreed), WhatsApp Business (read into the shared queue).",
      "Nothing is connected in the demo."],
  },
  "data-layer": {
    title: "How the department explains the system to IT.",
    phase: "Handoff — read-only",
    body: ["The entity list, the roles and segment table, the badge-count fields with their rule and current value, and the lessons carried from the HR Hub.",
      "The live badge-count contract is served by /api/fsa/nav-counts."],
  },
};

export function StubScreen({ slug }: { slug: string }) {
  const s = STUBS[slug];
  return (
    <Stub title={s.title} phase={s.phase}>
      {s.body.map((p) => <p key={p} style={{ margin: "0 0 8px" }}>{p}</p>)}
    </Stub>
  );
}
