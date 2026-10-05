import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Signed-out visitors go to /login before any page renders. This only checks that a session cookie is
// present; the API still validates the session on every request and answers 401 if it is not valid.
export function proxy(request: NextRequest) {
  if (request.cookies.has("gsth_session")) return NextResponse.next();
  const login = new URL("/login", request.url);
  const next = request.nextUrl.pathname + request.nextUrl.search;
  if (next !== "/") login.searchParams.set("next", next);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except the login page, client upload links (/u/<token>: the token is the credential and the
  // API checks it), the API proxy and static assets.
  matcher: ["/((?!login|u/|api|_next/static|_next/image|favicon.ico).*)"],
};
