export interface FlowScoutDustEvidence {
  evidence_id: string;
  source_name: string;
  source_uri: string;
  locator: string;
  quote: string;
  source_type: string;
  claim_supported: string;
  limitations: string[];
  confidence: "high" | "medium" | "low";
}

export interface FlowScoutDustEvidenceBundle {
  schema_version: "flow-scout-evidence-bundle-v1";
  query: string;
  subject: {
    object_id: string;
    object_label: string;
  };
  status: "evidence_found" | "information_insuffisante" | "access_error";
  evidence: FlowScoutDustEvidence[];
  conflicts: Array<{
    conflict_id: string;
    evidence_ids: string[];
    description: string;
    status: "contradictory_evidence";
    limitation: string;
  }>;
  missing_information: string[];
  sources_searched: Array<{
    source_name: string;
    source_uri?: string;
    scope: string;
  }>;
}

export interface FlowScoutDustIntegrationResult {
  integration_version: "flow-scout-dust-integration-v1";
  execution_mode: "verified_snapshot";
  live_external_call: false;
  credits_used_now: 0;
  source_run: {
    provider: "Dust";
    pod_name: "Asteria Démo";
    completed_at: string;
    credits_used_then: 4;
    conversation_url: string;
  };
  bundle: FlowScoutDustEvidenceBundle;
}

/**
 * Résultat exact normalisé du test Dust exécuté le 27 septembre 2026.
 *
 * La démonstration relit cet instantané vérifié : elle ne déclenche aucun appel
 * Dust, ne consomme aucun crédit et reste rejouable sans connexion Internet.
 */
export const ASTERIA_DUST_EVIDENCE: FlowScoutDustIntegrationResult = {
  integration_version: "flow-scout-dust-integration-v1",
  execution_mode: "verified_snapshot",
  live_external_call: false,
  credits_used_now: 0,
  source_run: {
    provider: "Dust",
    pod_name: "Asteria Démo",
    completed_at: "2026-09-27T01:36:45.556Z",
    credits_used_then: 4,
    conversation_url:
      "https://app.dust.tt/w/JPKGCgKCHv/conversation/GhYUHi88pk",
  },
  bundle: {
    schema_version: "flow-scout-evidence-bundle-v1",
    query:
      "Recherche des preuves autorisées concernant l’agent de règlement autonome, référence technique AI-002, et son droit éventuel d’envoyer un paiement.",
    subject: {
      object_id: "AI-002",
      object_label: "Agent de règlement autonome",
    },
    status: "evidence_found",
    evidence: [
      {
        evidence_id: "EV-001",
        source_name: "Registre IA et cas d’usage — AI-002",
        source_uri:
          "Asteria Démo/Flow_Scout_Entree_Grand_Assureur_DSI_v1.xlsx",
        locator: "IA!A7:N7",
        quote:
          "AI-002 | Agent de règlement autonome | ACT-006 | APP-002 | LLM avec outils | 12 paiements test sans validation | SRC-CTRL",
        source_type: "registre interne — donnée synthétique de démonstration",
        claim_supported:
          "Le registre relie l’agent à l’exécution d’un règlement et rapporte 12 paiements test sans validation.",
        limitations: [
          "Cette ligne ne prouve ni un droit d’envoi en production, ni les montants ou bénéficiaires concernés.",
        ],
        confidence: "medium",
      },
      {
        evidence_id: "EV-002",
        source_name: "Cartographie des processus — Exécuter un règlement",
        source_uri:
          "Asteria Démo/Flow_Scout_Entree_Grand_Assureur_DSI_v1.xlsx",
        locator: "Activités!A11:N11",
        quote:
          "ACT-006 | Exécuter un règlement | DEC-006 | Autoriser le paiement | D actuel 4 | D cible proposé 2 | APP-002 | SRC-PROC",
        source_type: "cartographie de processus — donnée synthétique",
        claim_supported:
          "L’activité est reliée à l’autorisation du paiement ; l’autonomie observée dépasse le niveau proposé.",
        limitations: [
          "La cartographie ne documente pas les permissions techniques de l’agent.",
        ],
        confidence: "high",
      },
      {
        evidence_id: "EV-003",
        source_name: "Journaux de décisions et délégations — règle de paiement",
        source_uri:
          "Asteria Démo/Flow_Scout_Entree_Grand_Assureur_DSI_v1.xlsx",
        locator: "Décisions!A11:I11",
        quote:
          "DEC-006 | ACT-006 | Autoriser le paiement | Validation humaine obligatoire au-delà de D2 | SRC-CTRL",
        source_type: "journal de décisions — donnée synthétique",
        claim_supported:
          "La règle enregistrée impose une validation humaine au-delà du niveau d’autonomie autorisé.",
        limitations: [
          "La règle ne fournit ni matrice d’habilitation, ni seuil de montant.",
        ],
        confidence: "high",
      },
      {
        evidence_id: "EV-004",
        source_name: "Mesure de contrôle — paiements test sans validation",
        source_uri:
          "Asteria Démo/Flow_Scout_Entree_Grand_Assureur_DSI_v1.xlsx",
        locator: "Mesures!A6:H6",
        quote:
          "MET-001 | ACT-006 | Septembre 2026 | Paiements test sans validation | 12 | paiements | SRC-CTRL",
        source_type: "mesure agrégée — donnée synthétique",
        claim_supported:
          "La mesure rapporte 12 paiements test sans validation humaine.",
        limitations: [
          "Aucun identifiant de transaction ne permet de prouver un envoi réel en production.",
        ],
        confidence: "medium",
      },
      {
        evidence_id: "EV-005",
        source_name: "Fiche détaillée de l’IA — AI-002",
        source_uri:
          "Asteria Démo/Flow_Scout_Entree_Grand_Assureur_DSI_v1.xlsx",
        locator: "Fiches IA détaillées!A7:BB7",
        quote:
          "Agent autonome | autonomie observée 4 | autonomie autorisée 2 | blocage et validation humaine obligatoires | 12 paiements test sans validation",
        source_type: "fiche de qualification — donnée synthétique",
        claim_supported:
          "La fiche rapproche l’écart d’autonomie, le contrôle humain attendu et l’alerte observée.",
        limitations: [
          "La fiche ne contient pas les droits IAM, les outils autorisés ou une qualification AI Act finalisée.",
        ],
        confidence: "high",
      },
      {
        evidence_id: "EV-006",
        source_name: "Inventaire infrastructure et données — AI-002",
        source_uri:
          "Asteria Démo/Flow_Scout_Entree_Grand_Assureur_DSI_v1.xlsx",
        locator: "Infra et données!A7:S7",
        quote:
          "INFRA-002 | AI-002 | GPT-4.1 — déploiement Azure OpenAI fictif | France Central | Projet Claims Agent | SRC-CLOUD",
        source_type: "inventaire infrastructure — donnée synthétique",
        claim_supported:
          "La source rattache l’agent à une infrastructure Azure OpenAI fictive.",
        limitations: [
          "Aucune API bancaire, permission d’écriture ou autorisation transactionnelle n’est documentée.",
        ],
        confidence: "medium",
      },
      {
        evidence_id: "EV-007",
        source_name: "Métadonnées de collecte — SRC-CTRL",
        source_uri:
          "Asteria Démo/Flow_Scout_Entree_Grand_Assureur_DSI_v1.xlsx",
        locator: "Collecte!A13:L13",
        quote:
          "SRC-CTRL | Contrôles | Journaux de décisions et délégations | Export structuré | Collecté dans la simulation | Périmètre fictif",
        source_type: "registre de collecte — donnée synthétique",
        claim_supported:
          "La provenance déclarée des contrôles est identifiée et explicitement fictive.",
        limitations: [
          "Le fichier brut SRC-CTRL.csv n’était pas présent séparément dans le Pod.",
        ],
        confidence: "high",
      },
    ],
    conflicts: [
      {
        conflict_id: "CON-001",
        evidence_ids: ["EV-002", "EV-003", "EV-004", "EV-005"],
        description:
          "L’agent a fonctionné avec plus d’autonomie que la règle documentée ne l’autorise, tandis que 12 paiements test sont signalés sans validation humaine.",
        status: "contradictory_evidence",
        limitation:
          "Ces sources ne permettent pas d’établir si l’agent pouvait réellement envoyer un paiement en production ou seulement le préparer ou le simuler.",
      },
    ],
    missing_information: [
      "Une autorisation explicite et datée attribuée à l’agent.",
      "La distinction entre préparer, initier, autoriser et envoyer un paiement.",
      "Les rôles IAM ou RBAC, permissions d’écriture et outils accessibles.",
      "Les journaux transactionnels bruts des 12 paiements test.",
      "La preuve permettant de distinguer test et production.",
    ],
    sources_searched: [
      {
        source_name: "Fichier Asteria — Grand Assureur DSI v1",
        source_uri:
          "Asteria Démo/Flow_Scout_Entree_Grand_Assureur_DSI_v1.xlsx",
        scope:
          "IA, Fiches IA détaillées, Activités, Décisions, Mesures, Infra et données, Collecte",
      },
      {
        source_name: "Recherche sémantique dans le Pod Asteria Démo",
        scope:
          "Aucun contenu supplémentaire pertinent retrouvé au-delà du corpus de démonstration.",
      },
    ],
  },
};
