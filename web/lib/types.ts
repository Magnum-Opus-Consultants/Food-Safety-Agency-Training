import type { Tone } from "./api";

export type SessionRow = {
  ref: string; block: string; course: string; venue: string; facilitator: string; start: string; end: string; mode: string;
  seats: number; capacity: number; registerState: string; tone: Tone; lockedAt: string | null; lockedBy: string | null;
};

export type Warning = { kind: string; tone: Tone; message: string };

export type Block = {
  ref: string; session: string | null; course: string; stream: string; streamCode: string; streamColour: string; facilitator: string;
  venue: string; mode: string; cadence: string; start: string; end: string; seats: number; capacity: number;
  fill: number; hours: number; notes: string; state: string; warnings: Warning[]; confirmBlockedBy: string[];
};
