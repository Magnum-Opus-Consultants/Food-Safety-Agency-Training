import type { Tone } from "./api";

export type SessionRow = {
  ref: string; block: string; course: string; venue: string; facilitator: string; start: string; end: string; mode: string;
  seats: number; capacity: number; registerState: string; tone: Tone; lockedAt: string | null; lockedBy: string | null;
  day: string | null; sequence: number | null; of: number | null; times: string;
  groups: { name: string; short: string; kind: string; learners: number }[];
};

export type Warning = { kind: string; tone: Tone; message: string };

export type Block = {
  ref: string; session: string | null; course: string; stream: string; streamCode: string; streamColour: string; facilitator: string;
  venue: string; mode: string; cadence: string; start: string; end: string; seats: number; capacity: number;
  fill: number; hours: number; notes: string; state: string; warnings: Warning[]; confirmBlockedBy: string[];
  courseCode: string; facilitatorRef: string; venueId: number; started: boolean;
  sessionCount: number; schedule: string; weekdays: number[]; startsAt: string; endsAt: string;
};
