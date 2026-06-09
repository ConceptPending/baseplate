import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("access_token");
  if (!token) {
    return NextResponse.redirect(new URL("/admin/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // Cover both the bare /admin dashboard and its sub-routes (except the login
  // page). Without the standalone "/admin", a logged-out hit to the dashboard
  // root skipped the edge redirect.
  matcher: ["/admin", "/admin/((?!login).*)"],
};
