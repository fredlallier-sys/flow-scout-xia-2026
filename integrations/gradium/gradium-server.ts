import "server-only";

const GRADIUM_BASE_URL = "https://api.gradium.ai/api";

export interface ServerGradiumCredits {
  remaining_credits: number;
  allocated_credits: number | null;
  billing_period: string | null;
  next_rollover_date: string | null;
  plan_name: string;
}

export class GradiumServerError extends Error {
  constructor(
    message: string,
    readonly status = 502,
  ) {
    super(message);
  }
}

function apiKey(): string {
  const key = process.env.GRADIUM_API_KEY?.trim();
  if (!key) {
    throw new GradiumServerError(
      "GRADIUM_API_KEY n’est pas configurée côté serveur.",
      503,
    );
  }
  return key;
}

async function gradiumFetch(path: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${GRADIUM_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        "x-api-key": apiKey(),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new GradiumServerError("Gradium est momentanément inaccessible.");
  }
  if (!response.ok) {
    throw new GradiumServerError(`Gradium a refusé l’appel (HTTP ${response.status}).`);
  }
  return response;
}

export async function readGradiumCredits(): Promise<ServerGradiumCredits> {
  const response = await gradiumFetch("/usages/credits", { method: "GET" });
  const payload = (await response.json()) as Partial<ServerGradiumCredits>;
  if (!Number.isInteger(payload.remaining_credits)) {
    throw new GradiumServerError("Le solde Gradium reçu est invalide.");
  }
  return {
    remaining_credits: payload.remaining_credits as number,
    allocated_credits:
      typeof payload.allocated_credits === "number"
        ? payload.allocated_credits
        : null,
    billing_period:
      typeof payload.billing_period === "string" ? payload.billing_period : null,
    next_rollover_date:
      typeof payload.next_rollover_date === "string"
        ? payload.next_rollover_date
        : null,
    plan_name: typeof payload.plan_name === "string" ? payload.plan_name : "",
  };
}

export async function transcribeGradiumWav(
  audio: ArrayBuffer,
  contentType: string,
): Promise<string> {
  const query = new URLSearchParams({
    json_config: JSON.stringify({ language: "fr" }),
  });
  const response = await gradiumFetch(`/post/speech/asr?${query.toString()}`, {
    method: "POST",
    headers: { "Content-Type": contentType },
    body: audio,
  });
  const body = await response.text();
  const transcript = body
    .split("\n")
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line) as { type?: string; text?: string };
      } catch {
        throw new GradiumServerError("Le flux de transcription Gradium est invalide.");
      }
    })
    .filter((message) => message.type === "text" && message.text?.trim())
    .map((message) => message.text?.trim())
    .join(" ")
    .trim();
  if (!transcript) {
    throw new GradiumServerError("Gradium n’a retourné aucune transcription.");
  }
  return transcript;
}

export async function synthesizeGradium(
  text: string,
  voiceId: string,
): Promise<ArrayBuffer> {
  const response = await gradiumFetch("/post/speech/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      voice_id: voiceId,
      output_format: "wav",
      only_audio: true,
    }),
  });
  return response.arrayBuffer();
}
