import Documents from "@/components/Documents";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export default async function DashboardPage() {
  const cookieStore = await cookies();
  const accessToken = cookieStore.get("access_token");

  if (!accessToken) {
    redirect("/signin");
  }

  return (
    <div>
      <div className="h-full max-w-7xl mx-auto">
        <h1 className="text-3xl p-5 bg-gray-100 font-extralight">My Documents</h1>
      <Documents />
    </div>
    </div>
  );
}