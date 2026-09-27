import type { FlowScoutVoiceCommand } from "@/lib/types";

const OBJECT_ID = /\b(?:AI|ACT|Q|FINDING|CTRL)-[A-Z0-9_-]+\b/i;

function normalize(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("fr");
}

function containsAny(value: string, ...needles: string[]): boolean {
  return needles.some((needle) => value.includes(needle));
}

function result(
  transcript: string,
  intent: string,
  route: string,
  operation: string,
  status: FlowScoutVoiceCommand["status"],
  spokenReply: string,
  options: {
    targetId?: string | null;
    arguments?: Record<string, unknown>;
    confirmationRequired?: boolean;
    externalCreditCall?: boolean;
    finalHumanApprovalRequired?: boolean;
  } = {},
): FlowScoutVoiceCommand {
  return {
    schema_version: "flow-scout-voice-command-v1",
    transcript,
    transcript_trust: "untrusted_human_declaration",
    intent,
    status,
    target_id: options.targetId ?? null,
    action: {
      route,
      operation,
      arguments: options.arguments ?? {},
    },
    gates: {
      confirmation_required: options.confirmationRequired ?? false,
      external_credit_call: options.externalCreditCall ?? false,
      existing_credits_only: options.externalCreditCall ?? false,
      final_human_approval_required:
        options.finalHumanApprovalRequired ?? false,
      automatic_blocking_decision_forbidden: true,
    },
    spoken_reply: spokenReply,
  };
}

/** Interprète gratuitement une commande texte, sans appel à un modèle externe. */
export function interpretFlowScoutVoiceCommandLocally(
  rawTranscript: string,
): FlowScoutVoiceCommand {
  const transcript = rawTranscript.trim().replace(/\s+/g, " ");
  const normalized = normalize(transcript);
  const explicitTargetId = transcript.match(OBJECT_ID)?.[0].toUpperCase() ?? null;
  const targetId =
    explicitTargetId ??
    (containsAny(
      normalized,
      "agent de reglement autonome",
      "agent de reglement",
      "agent de paiement",
    )
      ? "AI-002"
      : null);

  if (!transcript) {
    return result(
      transcript,
      "unknown",
      "voice_session",
      "none",
      "not_understood",
      "Je n'ai rien reçu. Tu peux écrire : aide.",
    );
  }

  if (
    normalized === "annule" ||
    normalized === "annuler" ||
    normalized === "laisse tomber" ||
    normalized === "stop"
  ) {
    return result(
      transcript,
      "cancel",
      "voice_session",
      "cancel_pending",
      "ready",
      "Action annulée. Aucune donnée ni décision n'a été modifiée.",
    );
  }

  if (containsAny(normalized, "valide", "validation", "accepte", "approuve")) {
    return result(
      transcript,
      "validate_answer",
      "flow_scout_local",
      "validate_human_answer",
      "needs_confirmation",
      "Cette validation peut lever un contrôle important. Je prépare l'action, mais un humain doit la relire et la confirmer.",
      {
        targetId,
        confirmationRequired: true,
        finalHumanApprovalRequired: true,
      },
    );
  }

  if (
    normalized.includes("dust") ||
    (containsAny(normalized, "cherche", "retrouve", "trouve") &&
      containsAny(normalized, "preuve", "source", "document"))
  ) {
    return result(
      transcript,
      "search_evidence",
      "dust",
      "search_authorized_sources",
      "needs_confirmation",
      "Je peux demander à Dust de rechercher des preuves autorisées. Cet appel peut utiliser tes crédits existants et exige donc ta confirmation.",
      {
        targetId,
        arguments: { query: transcript, output_contract: "evidence_bundle_v1" },
        confirmationRequired: true,
        externalCreditCall: true,
      },
    );
  }

  if (
    normalized.includes("pipelex") ||
    (containsAny(normalized, "reformule", "explique", "priorise") &&
      containsAny(normalized, "constat", "risque", "question", "direction"))
  ) {
    return result(
      transcript,
      "explain_governance",
      "pipelex",
      "review_governance_packet",
      "needs_confirmation",
      "Je peux soumettre ce constat sourcé à Pipelex pour une explication simple. Cet appel peut utiliser tes crédits existants et exige donc ta confirmation.",
      {
        targetId,
        arguments: { request: transcript, method: "flow-scout-governance" },
        confirmationRequired: true,
        externalCreditCall: true,
      },
    );
  }

  if (
    containsAny(normalized, "exporte", "exporter", "charge", "charger", "publie") &&
    containsAny(normalized, "atlas", "nexus")
  ) {
    const publish = containsAny(normalized, "charge", "publie");
    return result(
      transcript,
      "export_atlas",
      "atlas_bridge",
      publish ? "publish_atlas" : "export_atlas_v3",
      "needs_confirmation",
      "Je prépare l'export Atlas version 3. Rien ne sera publié ni chargé sans confirmation humaine.",
      {
        confirmationRequired: true,
        finalHumanApprovalRequired: true,
      },
    );
  }

  if (
    containsAny(normalized, "lance", "demarre", "execute") &&
    containsAny(normalized, "audit", "analyse", "flow scout")
  ) {
    return result(
      transcript,
      "start_audit",
      "flow_scout_local",
      "run_agent_once",
      "ready",
      "Audit local prêt à démarrer, sans appel externe. Le résultat Atlas restera en attente de validation.",
    );
  }

  if (containsAny(normalized, "statut", "etat", "ou en est", "resume", "synthese")) {
    return result(
      transcript,
      "get_status",
      "flow_scout_local",
      "summarize_current_run",
      "ready",
      "Je vais lire l'état courant de Flow Scout sans rien modifier.",
      { targetId },
    );
  }

  if (containsAny(normalized, "montre", "affiche", "ouvre") && targetId) {
    const spokenReply =
      targetId === "AI-002"
        ? "L'agent de règlement autonome est affiché avec ses preuves. Il pourrait envoyer un paiement sans autorisation humaine. Flow Scout bloque donc la publication et demande à une personne de décider. Aucune décision n'a été prise automatiquement. Sa référence technique est AI-002."
        : `${targetId} est affiché avec ses preuves et ses limites. Aucune décision n'a été prise automatiquement.`;
    return result(
      transcript,
      "show_object",
      "flow_scout_local",
      "show_object_with_evidence",
      "ready",
      spokenReply,
      { targetId },
    );
  }

  if (containsAny(normalized, "aide", "commandes", "que peux tu faire")) {
    return result(
      transcript,
      "help",
      "voice_session",
      "show_voice_help",
      "ready",
      "Tu peux écrire : lance l'audit, donne-moi le statut, montre l'agent de règlement autonome, cherche une preuve avec Dust, explique un risque avec Pipelex, ou exporte vers Atlas.",
    );
  }

  return result(
    transcript,
    "unknown",
    "voice_session",
    "none",
    "not_understood",
    "Je n'ai pas compris l'action avec assez de certitude. Je n'exécute rien. Écris aide pour voir les commandes.",
    { targetId },
  );
}
