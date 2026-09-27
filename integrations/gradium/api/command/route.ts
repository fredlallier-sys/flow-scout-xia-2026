import { NextResponse } from "next/server";

import { interpretFlowScoutVoiceCommandLocally } from "@/lib/flow-scout-voice";
import {
  GradiumServerError,
  readGradiumCredits,
  transcribeGradiumWav,
} from "@/lib/gradium-server";

const MAX_AUDIO_BYTES = 2 * 1024 * 1024;
const SUPPORTED_AUDIO_TYPES = new Set([
  "audio/wav",
  "audio/pcm",
  "audio/ogg",
  "audio/opus",
]);

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const form = await request.formData();
    if (form.get("confirmed_existing_credits") !== "true") {
      return NextResponse.json(
        { error: "Confirmation des crédits Gradium existants requise." },
        { status: 403 },
      );
    }
    const audio = form.get("audio");
    if (!(audio instanceof File) || audio.size === 0) {
      return NextResponse.json({ error: "Le fichier audio est vide." }, { status: 422 });
    }
    if (audio.size > MAX_AUDIO_BYTES) {
      return NextResponse.json(
        { error: "Le test vocal dépasse la limite de sécurité de 2 Mo." },
        { status: 413 },
      );
    }
    const contentType = audio.type || "audio/wav";
    if (!SUPPORTED_AUDIO_TYPES.has(contentType)) {
      return NextResponse.json(
        { error: `Format audio non autorisé : ${contentType}.` },
        { status: 422 },
      );
    }

    const creditsBefore = await readGradiumCredits();
    if (creditsBefore.remaining_credits <= 0) {
      return NextResponse.json(
        { error: "Aucun crédit Gradium restant : test bloqué." },
        { status: 403 },
      );
    }
    const transcript = await transcribeGradiumWav(
      await audio.arrayBuffer(),
      contentType,
    );
    const creditsAfter = await readGradiumCredits();
    return NextResponse.json({
      transcription: {
        schema_version: "flow-scout-gradium-transcription-v1",
        transcript,
        transcript_trust: "untrusted_human_declaration",
        language: "fr",
        credit_check: creditsBefore,
      },
      credits_before: creditsBefore,
      credits_after: creditsAfter,
      command: interpretFlowScoutVoiceCommandLocally(transcript),
    });
  } catch (cause) {
    const error = cause as GradiumServerError;
    return NextResponse.json(
      { error: error.message },
      { status: error.status || 502 },
    );
  }
}
