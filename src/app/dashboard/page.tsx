import { redirect } from "next/navigation";
import { isSignedIn } from "@/lib/session";
import { Dashboard } from "@/components/dashboard";

export default async function DashboardPage() {
  if (!(await isSignedIn())) redirect("/");
  return <Dashboard />;
}
