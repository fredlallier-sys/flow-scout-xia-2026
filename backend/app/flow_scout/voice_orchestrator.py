"""Interprétation locale et sûre des commandes vocales Flow Scout.

Gradium fournit uniquement une transcription et une restitution vocale. Ce module
reste l'autorité sur l'intention : il n'appelle aucun service externe, ne consomme
aucun crédit et ne valide jamais une décision bloquante.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_OBJECT_ID = re.compile(r"\b(?:AI|ACT|Q|FINDING|CTRL)-[A-Z0-9_-]+\b", re.IGNORECASE)
_QUESTION_ANSWER = re.compile(
    r"(?:reponds?|reponse)\s+(?:a\s+)?(?:la\s+)?question\s+"
    r"(?P<id>[A-Z]+-[A-Z0-9_-]+)\s*(?::|en\s+disant|avec)?\s*(?P<answer>.*)",
    re.IGNORECASE,
)


def interpret_voice_command(
    transcript: str,
    *,
    pending_action: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Transforme une transcription en commande explicite et contrôlable.

    La transcription est une déclaration non fiable. Une commande sensible est
    préparée, jamais exécutée, jusqu'à la confirmation humaine suivante.
    """
    clean = " ".join(transcript.strip().split())
    normalized = _normalize(clean)
    target = _extract_target(clean) or _extract_business_target(normalized)

    if not clean:
        return _result(
            clean,
            intent="unknown",
            route="voice_session",
            operation="none",
            status="not_understood",
            spoken_reply="Je n'ai rien entendu. Tu peux dire : aide.",
        )

    if normalized in {"annule", "annuler", "laisse tomber", "stop"}:
        return _result(
            clean,
            intent="cancel",
            route="voice_session",
            operation="cancel_pending",
            status="ready",
            spoken_reply="Action annulée. Aucune donnée ni décision n'a été modifiée.",
        )

    if normalized.startswith(("je confirme", "oui je confirme")):
        if not pending_action:
            return _result(
                clean,
                intent="confirm_pending",
                route="voice_session",
                operation="none",
                status="blocked",
                spoken_reply="Je n'ai aucune action précise en attente à confirmer.",
            )
        confirmed = _result(
            clean,
            intent="confirm_pending",
            route=str(pending_action.get("route", "voice_session")),
            operation=str(pending_action.get("operation", "none")),
            status="confirmed",
            target_id=str(pending_action.get("target_id", "")) or None,
            arguments=_mapping(pending_action.get("arguments")),
            spoken_reply=(
                "Confirmation enregistrée. L'application peut maintenant exécuter "
                "uniquement l'action relue à l'écran."
            ),
            confirmation_of=pending_action,
        )
        confirmed["action"] = dict(pending_action)
        return confirmed

    answer_match = _QUESTION_ANSWER.search(_normalize_keep_ids(clean))
    if answer_match:
        start, end = answer_match.span("answer")
        answer = clean[start:end].strip(" .")
        question_id = answer_match.group("id").upper()
        if not answer:
            return _result(
                clean,
                intent="answer_question",
                route="flow_scout_local",
                operation="record_human_declaration",
                status="blocked",
                target_id=question_id,
                spoken_reply="J'ai reconnu la question, mais pas la réponse à enregistrer.",
            )
        return _result(
            clean,
            intent="answer_question",
            route="flow_scout_local",
            operation="record_human_declaration",
            status="needs_confirmation",
            target_id=question_id,
            arguments={"answer": answer, "source_type": "human_declaration"},
            spoken_reply=(
                f"Tu proposes d'enregistrer pour {question_id} : {answer}. "
                "Cette réponse reste une déclaration humaine, pas une preuve. "
                "Dis je confirme pour l'enregistrer, ou annule."
            ),
            confirmation_required=True,
        )

    if _contains_any(normalized, "valide", "validation", "accepte", "approuve"):
        return _result(
            clean,
            intent="validate_answer",
            route="flow_scout_local",
            operation="validate_human_answer",
            status="needs_confirmation",
            target_id=target,
            spoken_reply=(
                "Une validation peut lever un contrôle bloquant. Je prépare l'action, "
                "mais elle doit être relue à l'écran et confirmée explicitement."
            ),
            confirmation_required=True,
            final_human_approval_required=True,
        )

    if "dust" in normalized or (
        _contains_any(normalized, "cherche", "retrouve", "trouve")
        and _contains_any(normalized, "preuve", "source", "document")
    ):
        return _result(
            clean,
            intent="search_evidence",
            route="dust",
            operation="search_authorized_sources",
            status="needs_confirmation",
            target_id=target,
            arguments={"query": clean, "output_contract": "evidence_bundle_v1"},
            spoken_reply=(
                "Je peux demander à Dust de rechercher des preuves dans les sources "
                "autorisées. Cet appel peut consommer tes crédits existants. Confirme "
                "l'appel Dust affiché à l'écran pour continuer."
            ),
            confirmation_required=True,
            external_credit_call=True,
        )

    if "pipelex" in normalized or (
        _contains_any(normalized, "reformule", "explique", "priorise")
        and _contains_any(normalized, "constat", "risque", "question", "direction")
    ):
        return _result(
            clean,
            intent="explain_governance",
            route="pipelex",
            operation="review_governance_packet",
            status="needs_confirmation",
            target_id=target,
            arguments={"request": clean, "method": "flow-scout-governance"},
            spoken_reply=(
                "Je peux soumettre le paquet sourcé à Pipelex pour une explication en "
                "français simple. Cet appel peut consommer tes crédits existants. "
                "Confirme l'appel Pipelex affiché à l'écran pour continuer."
            ),
            confirmation_required=True,
            external_credit_call=True,
        )

    if _contains_any(normalized, "exporte", "exporter", "charge", "charger", "publie") and (
        "atlas" in normalized or "nexus" in normalized
    ):
        operation = (
            "publish_atlas"
            if _contains_any(normalized, "charge", "publie")
            else "export_atlas_v3"
        )
        return _result(
            clean,
            intent="export_atlas",
            route="atlas_bridge",
            operation=operation,
            status="needs_confirmation",
            spoken_reply=(
                "Je prépare l'export Atlas version 3. Rien ne sera publié ni chargé "
                "avant la confirmation humaine affichée à l'écran."
            ),
            confirmation_required=True,
            final_human_approval_required=True,
        )

    if _contains_any(normalized, "lance", "demarre", "execute") and _contains_any(
        normalized, "audit", "analyse", "flow scout"
    ):
        return _result(
            clean,
            intent="start_audit",
            route="flow_scout_local",
            operation="run_agent_once",
            status="ready",
            spoken_reply=(
                "Audit local prêt à démarrer. Il analysera le dossier client sans "
                "appel externe et chargera seulement un espace Atlas en attente."
            ),
        )

    if _contains_any(normalized, "statut", "etat", "ou en est", "resume", "synthese"):
        return _result(
            clean,
            intent="get_status",
            route="flow_scout_local",
            operation="summarize_current_run",
            status="ready",
            target_id=target,
            spoken_reply="Je vais lire l'état courant de Flow Scout sans rien modifier.",
        )

    if _contains_any(normalized, "montre", "affiche", "ouvre") and target:
        spoken_reply = (
            "L'agent de règlement autonome est affiché avec ses preuves. Il pourrait "
            "envoyer un paiement sans autorisation humaine. Flow Scout bloque donc "
            "la publication et demande à une personne de décider. Aucune décision "
            "n'a été prise automatiquement. Sa référence technique est AI-002."
            if target == "AI-002"
            else (
                f"{target} est affiché avec ses preuves et ses limites. "
                "Aucune décision n'a été prise automatiquement."
            )
        )
        return _result(
            clean,
            intent="show_object",
            route="flow_scout_local",
            operation="show_object_with_evidence",
            status="ready",
            target_id=target,
            spoken_reply=spoken_reply,
        )

    if _contains_any(normalized, "aide", "commandes", "que peux tu faire"):
        return _result(
            clean,
            intent="help",
            route="voice_session",
            operation="show_voice_help",
            status="ready",
            spoken_reply=(
                "Tu peux dire : lance l'audit, donne-moi le statut, montre l'agent "
                "de règlement autonome, "
                "cherche la preuve avec Dust, explique le risque avec Pipelex, "
                "réponds à la question, ou exporte vers Atlas."
            ),
        )

    return _result(
        clean,
        intent="unknown",
        route="voice_session",
        operation="none",
        status="not_understood",
        target_id=target,
        spoken_reply=(
            "Je n'ai pas compris l'action avec assez de certitude. Je n'exécute rien. "
            "Dis aide pour entendre les commandes disponibles."
        ),
    )


def _result(
    transcript: str,
    *,
    intent: str,
    route: str,
    operation: str,
    status: str,
    spoken_reply: str,
    target_id: str | None = None,
    arguments: dict[str, Any] | None = None,
    confirmation_required: bool = False,
    external_credit_call: bool = False,
    final_human_approval_required: bool = False,
    confirmation_of: dict[str, Any] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": "flow-scout-voice-command-v1",
        "transcript": transcript,
        "transcript_trust": "untrusted_human_declaration",
        "intent": intent,
        "status": status,
        "target_id": target_id,
        "action": {
            "route": route,
            "operation": operation,
            "arguments": arguments or {},
        },
        "gates": {
            "confirmation_required": confirmation_required,
            "external_credit_call": external_credit_call,
            "existing_credits_only": external_credit_call,
            "final_human_approval_required": final_human_approval_required,
            "automatic_blocking_decision_forbidden": True,
        },
        "spoken_reply": spoken_reply,
    }
    if confirmation_of is not None:
        result["confirmation_of"] = confirmation_of
    return result


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def _normalize_keep_ids(value: str) -> str:
    return _normalize(value)


def _contains_any(value: str, *needles: str) -> bool:
    return any(needle in value for needle in needles)


def _extract_target(value: str) -> str | None:
    match = _OBJECT_ID.search(value)
    return match.group(0).upper() if match else None


def _extract_business_target(normalized: str) -> str | None:
    aliases = (
        "agent de reglement autonome",
        "agent de reglement",
        "agent de paiement",
    )
    return "AI-002" if _contains_any(normalized, *aliases) else None


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
