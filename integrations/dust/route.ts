import { NextResponse } from "next/server";

import { ASTERIA_DUST_EVIDENCE } from "@/lib/asteria-dust-evidence";

export const dynamic = "force-static";

/**
 * Rejoue le résultat Dust vérifié de la démonstration Asteria.
 * Aucun secret, appel externe ou crédit n'est utilisé par cette route.
 */
export async function GET() {
  return NextResponse.json(ASTERIA_DUST_EVIDENCE, {
    headers: {
      "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
      "X-Flow-Scout-External-Calls": "0",
    },
  });
}
