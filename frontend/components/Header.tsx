// components/Header.tsx
import { cookies } from "next/headers";
import { LogoutButton } from "./LogoutButton";

async function getCurrentUser() {
  const cookieStore = await cookies();
  const res = await fetch("http://127.0.0.1:8000/api/users/me", {
    headers: { Cookie: cookieStore.toString() },
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

function getInitials(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export async function Header() {
  const user = await getCurrentUser();

  return (
    <header className="flex sticky top-0 x-10 shrink-0 items-center justify-between border-b px-6 py-4">
      <span className="text-lg font-semibold">DocuSense</span>

      {user && (
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-sm font-medium">
            {getInitials(user.username)}
          </div>
          <span className="text-sm font-medium">{user.name}</span>
          <LogoutButton />
        </div>
      )}
    </header>
  );
}