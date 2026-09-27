"use client";

import { useRef, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { TextField } from "@/components/ui/TextField";
import {
  getGradiumCredits,
  interpretFlowScoutVoiceCommand,
  speakFlowScoutVoiceReply,
  transcribeFlowScoutGradiumCommand,
} from "@/lib/api";
import type { ApiAuth } from "@/lib/api";
import type { FlowScoutVoiceCommand, GradiumCredits } from "@/lib/types";

interface ActiveRecorder {
  context: AudioContext;
  processor: ScriptProcessorNode;
  source: MediaStreamAudioSourceNode;
  sink: GainNode;
  stream: MediaStream;
  samples: Float32Array[];
  sampleRate: number;
  timeoutId: number;
}

export function VoiceControl({
  auth,
  disabled,
}: {
  auth: ApiAuth;
  disabled?: boolean;
}) {
  const recorder = useRef<ActiveRecorder | null>(null);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [creditConsent, setCreditConsent] = useState(false);
  const [credits, setCredits] = useState<GradiumCredits | null>(null);
  const [creditsBefore, setCreditsBefore] = useState<number | null>(null);
  const [creditsAfter, setCreditsAfter] = useState<number | null>(null);
  const [typedCommand, setTypedCommand] = useState(
    "Montre l'agent de règlement autonome avec ses preuves",
  );
  const [command, setCommand] = useState<FlowScoutVoiceCommand | null>(null);
  const [voiceId, setVoiceId] = useState("7HhpTMy55D4HkXen");
  const [error, setError] = useState("");

  const refreshCredits = async () => {
    setError("");
    setBusy(true);
    try {
      const balance = await getGradiumCredits(auth);
      setCredits(balance);
      setCreditsBefore(balance.remaining_credits);
      setCreditsAfter(null);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const applyCommand = (nextCommand: FlowScoutVoiceCommand) => {
    setCommand(nextCommand);
    if (!nextCommand.target_id) return;
    window.requestAnimationFrame(() => {
      const target = document.getElementById(
        `flow-scout-object-${nextCommand.target_id}`,
      );
      target?.focus({ preventScroll: true });
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };

  const runTypedCommand = async () => {
    setError("");
    setBusy(true);
    try {
      applyCommand(await interpretFlowScoutVoiceCommand(typedCommand, auth));
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const startRecording = async () => {
    setError("");
    if (!creditConsent) {
      setError("Coche d'abord l'autorisation d'utiliser les crédits Gradium existants.");
      return;
    }
    setBusy(true);
    try {
      const balance = await getGradiumCredits(auth);
      setCredits(balance);
      if (balance.remaining_credits <= 0) {
        throw new Error("Aucun crédit Gradium restant : enregistrement bloqué.");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const context = new AudioContext();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const sink = context.createGain();
      sink.gain.value = 0;
      const samples: Float32Array[] = [];
      processor.onaudioprocess = (event) => {
        samples.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      };
      source.connect(processor);
      processor.connect(sink);
      sink.connect(context.destination);
      recorder.current = {
        context,
        processor,
        source,
        sink,
        stream,
        samples,
        sampleRate: context.sampleRate,
        timeoutId: window.setTimeout(() => void stopRecording(), 8_000),
      };
      setRecording(true);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const stopRecording = async () => {
    const active = recorder.current;
    if (!active) return;
    recorder.current = null;
    window.clearTimeout(active.timeoutId);
    setRecording(false);
    setBusy(true);
    active.processor.disconnect();
    active.source.disconnect();
    active.sink.disconnect();
    active.stream.getTracks().forEach((track) => track.stop());
    await active.context.close();
    try {
      const wav = encodeWav(active.samples, active.sampleRate);
      const file = new File([wav], "commande-flow-scout.wav", {
        type: "audio/wav",
      });
      const result = await transcribeFlowScoutGradiumCommand(
        file,
        creditConsent,
        auth,
      );
      setTypedCommand(result.transcription.transcript);
      applyCommand(result.command);
      setCredits(result.credits_after);
      setCreditsBefore(result.credits_before.remaining_credits);
      setCreditsAfter(result.credits_after.remaining_credits);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const speakReply = async () => {
    if (!command || !voiceId.trim()) {
      setError("Indique l'identifiant d'une voix Gradium pour lire la réponse.");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const audio = await speakFlowScoutVoiceReply(
        command.spoken_reply,
        voiceId,
        creditConsent,
        auth,
      );
      const url = URL.createObjectURL(audio);
      const player = new Audio(url);
      player.addEventListener("ended", () => URL.revokeObjectURL(url), {
        once: true,
      });
      await player.play();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="mb-6 border-accent/30">
      <CardHeader className="flex items-center justify-between gap-3">
        <span>Commander Flow Scout à la voix</span>
        <Badge tone={recording ? "danger" : "accent"}>
          {recording
            ? "Écoute en cours"
            : credits
              ? "Gradium connecté côté serveur"
              : "Gradium prêt à connecter"}
        </Badge>
      </CardHeader>
      <CardBody>
        <p className="text-sm text-ink-muted">
          Essaie gratuitement en texte, puis active le micro seulement après avoir
          vérifié tes crédits Gradium.
        </p>

        <div className="mt-4 flex flex-col gap-3 sm:flex-row">
          <TextField
            value={typedCommand}
            onChange={(event) => setTypedCommand(event.target.value)}
            aria-label="Commande Flow Scout"
          />
          <Button
            variant="secondary"
            disabled={disabled || busy || !typedCommand.trim()}
            onClick={runTypedCommand}
          >
            Interpréter sans crédit
          </Button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button variant="secondary" disabled={disabled || busy} onClick={refreshCredits}>
            Vérifier le solde
          </Button>
          <span className="text-sm text-ink-muted">
            {credits
              ? `${credits.remaining_credits.toLocaleString("fr-FR")} crédits restants`
              : "Solde non vérifié"}
          </span>
          {creditsBefore !== null ? (
            <Badge tone="neutral">Avant : {creditsBefore.toLocaleString("fr-FR")}</Badge>
          ) : null}
          {creditsAfter !== null ? (
            <Badge tone="accent">Après : {creditsAfter.toLocaleString("fr-FR")}</Badge>
          ) : null}
        </div>

        <label className="mt-4 flex items-start gap-2 text-sm text-ink-muted">
          <input
            type="checkbox"
            checked={creditConsent}
            onChange={(event) => setCreditConsent(event.target.checked)}
          />
          J'autorise cette commande à utiliser mes crédits Gradium existants, sans
          achat ni dépassement.
        </label>

        <div className="mt-4 flex flex-wrap gap-3">
          {recording ? (
            <Button variant="danger" onClick={stopRecording}>
              Arrêter et interpréter
            </Button>
          ) : (
            <Button
              disabled={disabled || busy || !creditConsent}
              onClick={startRecording}
            >
              Parler à Flow Scout · 8 s max
            </Button>
          )}
        </div>

        {command ? (
          <div className="mt-5 rounded-lg bg-canvas-tint p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={command.status === "ready" ? "accent" : "warn"}>
                {command.status}
              </Badge>
              <span className="text-sm font-medium">{command.intent}</span>
              {command.target_id ? (
                <span className="text-sm text-ink-muted">
                  · {command.target_id === "AI-002" ? "Agent de règlement autonome" : command.target_id}
                  <span className="ml-1 text-xs">({command.target_id})</span>
                </span>
              ) : null}
            </div>
            <p className="mt-3 text-sm text-ink">{command.spoken_reply}</p>
            <div className="mt-4 flex flex-col gap-2 sm:flex-row">
              <TextField
                value={voiceId}
                onChange={(event) => setVoiceId(event.target.value)}
                placeholder="Voix Gradium"
                aria-label="Identifiant de voix Gradium"
              />
              <span className="self-center text-xs text-ink-muted">
                Vianney · grave et héroïque
              </span>
              <Button
                variant="secondary"
                disabled={busy || !creditConsent || !voiceId.trim()}
                onClick={speakReply}
              >
                Écouter la réponse
              </Button>
            </div>
          </div>
        ) : null}

        {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      </CardBody>
    </Card>
  );
}

function encodeWav(chunks: Float32Array[], sampleRate: number): Blob {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + length * 2, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, length * 2, true);
  let offset = 44;
  for (const chunk of chunks) {
    for (const value of chunk) {
      const sample = Math.max(-1, Math.min(1, value));
      view.setInt16(offset, sample < 0 ? sample * 32768 : sample * 32767, true);
      offset += 2;
    }
  }
  return new Blob([view], { type: "audio/wav" });
}

function writeAscii(view: DataView, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}
