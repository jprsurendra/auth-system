import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PROTECTED = ["/dashboard", "/profile", "/settings"];
const AUTH_ONLY = ["/login", "/register", "/verify"];

export function middleware(request: NextRequest) {
  const { pathname }   = request.nextUrl;
  const token          = request.cookies.get("access_token")?.value;
  const isAuthenticated = Boolean(token);

  // Authenticated users should not see login/register pages
  if (
    isAuthenticated &&
    AUTH_ONLY.some((p) => pathname.startsWith(p))
  ) {
    return NextResponse.redirect(
      new URL("/dashboard", request.url)
    );
  }

  // Unauthenticated users cannot access protected pages
  if (
    !isAuthenticated &&
    PROTECTED.some((p) => pathname.startsWith(p))
  ) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|api/).*)",
  ],
};
