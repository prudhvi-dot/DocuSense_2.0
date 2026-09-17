// proxy.ts (rename from middleware.ts, same location — project root)
import { NextRequest, NextResponse } from "next/server";

const PROTECTED_PATHS = ["/dashboard"];
const AUTH_PATHS = ["/signin", "/signup"];

export function proxy(request: NextRequest) {  
  const token = request.cookies.get("access_token");
  const { pathname } = request.nextUrl;

  const isProtected = PROTECTED_PATHS.some((path) => pathname.startsWith(path));
  const isAuthPage = AUTH_PATHS.some((path) => pathname.startsWith(path));

  if (isProtected && !token) {
    return NextResponse.redirect(new URL("/signin", request.url));
  }

  if (isAuthPage && token) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/signin", "/signup"],
};