/**
 * Mirrors the backend's internal `TaskEvidenceResult`/`CitationProjection` shape
 * (app/shopping_tasks/evidence.py) so demo artifact payloads look like the real thing.
 * Not part of the generated API types: evidence never crosses the wire as its own
 * schema today, it only ever lands inside a `TaskArtifactView.payload` blob.
 */
export type DemoCitation = {
  citation_id: string;
  source_path: string | null;
  evidence_type: string;
  source_version: string | null;
  status: string;
  channel_attribution: string[];
  product_ids: string[];
  sku_codes: string[];
};

export type DemoEvidencePayload = {
  status: "ok" | "degraded" | "empty" | "unavailable" | "timeout" | "disabled";
  citations: DemoCitation[];
  channel_statuses: Record<string, string>;
  supplemental_used: boolean;
};

function citation(
  overrides: Partial<DemoCitation> & Pick<DemoCitation, "citation_id">,
): DemoCitation {
  return {
    source_path: null,
    evidence_type: "compatibility_note",
    source_version: "1",
    status: "active",
    channel_attribution: ["lexical"],
    product_ids: [],
    sku_codes: [],
    ...overrides,
  };
}

export function okEvidence(skuCodes: string[]): DemoEvidencePayload {
  return {
    status: "ok",
    citations: skuCodes.map((sku, index) =>
      citation({
        citation_id: `evi-${sku.toLowerCase()}`,
        evidence_type: "spec_sheet",
        sku_codes: [sku],
        channel_attribution: index === 0 ? ["lexical", "vector"] : ["lexical"],
      }),
    ),
    channel_statuses: { "lexical:0": "ok", "vector:0": "ok" },
    supplemental_used: false,
  };
}

export function degradedEvidence(skuCodes: string[]): DemoEvidencePayload {
  return {
    status: "degraded",
    citations: skuCodes.map((sku) =>
      citation({
        citation_id: `evi-${sku.toLowerCase()}-fallback`,
        evidence_type: "catalog_spec_fallback",
        sku_codes: [sku],
        status: "fallback",
        channel_attribution: ["lexical"],
      }),
    ),
    channel_statuses: { "lexical:0": "ok", "vector:0": "timeout" },
    supplemental_used: true,
  };
}
