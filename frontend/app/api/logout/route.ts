// app/api/logout/route.ts
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export async function POST() {
  const cookieStore = await cookies();
  cookieStore.delete("access_token");   // this works fine — server-side, not blocked by httpOnly
  return NextResponse.json({ message: "Logged out" });
}