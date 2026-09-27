import { NextResponse } from "next/server";

import {
  GradiumServerError,
  readGradiumCredits,
} from "@/lib/gradium-server";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json(await readGradiumCredits());
  } catch (cause) {
    const error = cause as GradiumServerError;
    return NextResponse.json(
      { error: error.message },
      { status: error.status || 502 },
    );
  }
}
