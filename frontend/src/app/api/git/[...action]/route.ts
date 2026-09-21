import { NextResponse } from "next/server";

// Git has one authoritative implementation: the authenticated backend API.
// Do not restore filesystem access in this unauthenticated Next route.
function removed() {
  return NextResponse.json(
    { detail: "Use the authenticated backend /api/git API with a project_id." },
    { status: 410 },
  );
}

export const GET = removed;
export const POST = removed;
