import { redirect } from "next/navigation";

// Every role lands on the department picture first (handoff section 6).
export default function Index() {
  redirect("/training-home");
}
