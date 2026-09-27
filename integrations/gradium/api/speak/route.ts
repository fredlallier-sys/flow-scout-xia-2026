import { NextResponse } from "next/server";

import {
  GradiumServerError,
  readGradiumCredits,
  synthesizeGradium,
} from "@/lib/gradium-server";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const payload = (await request.json()) as {
      text?: unknown;
      voice_id?: unknown;
      confirmed_existing_credits?: unknown;
    };
    if (payload.confirmed_existing_credits !== true) {
      return NextResponse.json(
        { error: "Confirmation des crédits Gradium existants requise." },
        { status: 403 },
      );
    }
    const text = typeof payload.text === "string" ? payload.text.trim() : "";
    const voiceId =
      typeof payload.voice_id === "string" ? payload.voice_id.trim() : "";
    if (!text || !voiceId) {
      return NextResponse.json(
        { error: "Le texte et l’identifiant de voix sont obligatoires." },
        { status: 422 },
      );
    }
    if (text.length > 500) {
      return NextResponse.json(
        { error: "La réponse vocale est limitée à 500 caractères." },
        { status: 422 },
      );
    }
    const credits = await readGradiumCredits();
    if (credits.remaining_credits <= text.length) {
      return NextResponse.json(
        { error: "Crédits insuffisants : synthèse bloquée avant l’appel." },
        { status: 403 },
      );
    }
    const audio = await synthesizeGradium(text, voiceId);
    return new Response(audio, {
      headers: {
        "Cache-Control": "no-store",
        "Content-Disposition": 'inline; filename="flow-scout-reply.wav"',
        "Content-Type": "audio/wav",
      },
    });
  } catch (cause) {
    const error = cause as GradiumServerError;
    return NextResponse.json(
      { error: error.message },
      { status: error.status || 502 },
    );
  }
}
