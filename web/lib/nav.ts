// The rail: eight groups, 24 screens. Badges are read from /nav-counts only — never stored.
// `segment` decides visibility (the API enforces it regardless). `screen` keys the audit trail.

export type NavCounts = Record<string, number>;

export type NavItem = {
  href: string;
  icon: string;
  label: string;
  screen: string;
  segment: string;
  badge?: string;
  built: boolean;
  /** Shown indented under the item above it: a view of the same register. */
  sub?: boolean;
  /** Shown only to accounts with this permission from /me, on top of the segment. */
  needs?: "canSeeDesk";
};

export const NAV: { group: string; items: NavItem[] }[] = [
  { group: "Overview", items: [
    { href: "/training-home", icon: "fas fa-home", label: "Training home", screen: "home", segment: "overview", built: true },
    { href: "/desk", icon: "fas fa-user-tie", label: "Head of department desk", screen: "desk", segment: "overview", badge: "DeskEscalated", built: true, needs: "canSeeDesk" },
    { href: "/management-dashboard", icon: "fas fa-chart-line", label: "Management dashboard", screen: "dashboard", segment: "reporting", built: false },
    { href: "/monthly-report", icon: "fas fa-file-alt", label: "Monthly management report", screen: "report", segment: "reporting", built: false },
  ] },
  { group: "Clients & sales", items: [
    { href: "/enquiries", icon: "fas fa-inbox", label: "Enquiry queue", screen: "enquiries", segment: "demand", badge: "StaleEnquiries", built: true },
    { href: "/quotes", icon: "fas fa-file-invoice-dollar", label: "Quotations", screen: "quotes", segment: "demand", built: true },
  ] },
  { group: "Courses", items: [
    { href: "/catalogue", icon: "fas fa-book-open", label: "Course catalogue", screen: "catalogue", segment: "courses", built: true },
    { href: "/development", icon: "fas fa-pencil-ruler", label: "Course development & accreditation", screen: "development", segment: "courses", built: false },
    { href: "/packs", icon: "fas fa-box-archive", label: "Assessment & moderation packs", screen: "packs", segment: "courses", built: false },
  ] },
  { group: "Training delivery", items: [
    { href: "/plan", icon: "fas fa-calendar-alt", label: "Training plan & schedule", screen: "plan", segment: "delivery", built: true },
    { href: "/sessions", icon: "fas fa-clipboard-check", label: "Sessions & attendance", screen: "sessions", segment: "delivery", badge: "RegistersOutstanding", built: true },
    { href: "/facilitators", icon: "fas fa-id-badge", label: "Facilitators & accreditation", screen: "facilitators", segment: "delivery", badge: "AccredFlags", built: true },
  ] },
  { group: "Learners", items: [
    { href: "/learners", icon: "fas fa-user-graduate", label: "Learner directory", screen: "learners", segment: "learners", built: true },
    { href: "/enrolments", icon: "fas fa-user-plus", label: "Enrolments", screen: "enrolments", segment: "learners", badge: "GateIncomplete", built: true },
    { href: "/results", icon: "fas fa-tasks", label: "Results & moderation", screen: "results", segment: "results", badge: "AwaitingModeration", built: true },
    { href: "/certificates", icon: "fas fa-certificate", label: "Certification", screen: "certificates", segment: "certification", badge: "AwaitingCertificate", built: true },
  ] },
  { group: "Assurance", items: [
    { href: "/accreditation", icon: "fas fa-award", label: "Accreditation register", screen: "accreditation", segment: "assurance", built: true },
    { href: "/partnerships", icon: "fas fa-university", label: "Universities & vet placements", screen: "partnerships", segment: "assurance", badge: "PartnershipReportsDue", built: true },
    { href: "/risk", icon: "fas fa-exclamation-triangle", label: "Risk & escalation register", screen: "risk", segment: "assurance", badge: "RisksEscalated", built: true },
    { href: "/documents", icon: "fas fa-folder-open", label: "Training depository", screen: "documents", segment: "depository", badge: "DepositoryOutstanding", built: true },
  ] },
  { group: "Administration", items: [
    { href: "/users", icon: "fas fa-user-shield", label: "User management", screen: "users", segment: "admin", built: true },
    { href: "/integrations", icon: "fas fa-plug", label: "Integrations", screen: "integrations", segment: "overview", built: false },
  ] },
  { group: "Handoff", items: [
    { href: "/data-layer", icon: "fas fa-database", label: "Data layer & roles", screen: "datalayer", segment: "overview", built: false },
  ] },
];

export function findNav(pathname: string) {
  for (const g of NAV) {
    for (const item of g.items) {
      if (pathname === item.href || pathname.startsWith(item.href + "/")) return { group: g.group, item };
    }
  }
  return null;
}
