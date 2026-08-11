import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { ChatResponse, Money, RecommendationResult } from "./contracts";

describe("generated OpenAPI contract", () => {
  it("contains the recommendation and safe projection-error fields", () => {
    const response: Pick<ChatResponse, "recommendation" | "projection_error"> = { recommendation: null, projection_error: { code: "recommendation_projection_corrupt", message: "safe" } };
    expect(response.projection_error?.code).toBe("recommendation_projection_corrupt");
  });

  it("keeps Money amounts as strings and models all recommendation outcomes", () => {
    const money: Money = { amount: "5999.00", currency: "CNY" };
    const outcomes: RecommendationResult["outcome"][] = ["recommended", "no_match", "clarification_required"];
    expect(typeof money.amount).toBe("string");
    expect(outcomes).toHaveLength(3);
  });

  it("retains the backend maximum of three and contains no explicit any", () => {
    const openapi = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../openapi.json"), "utf8")) as { components: { schemas: { RecommendationResult: { properties: { recommendations: { maxItems: number } } } } } };
    const generated = readFileSync(resolve(import.meta.dirname, "openapi.generated.ts"), "utf8");
    expect(openapi.components.schemas.RecommendationResult.properties.recommendations.maxItems).toBe(3);
    expect(generated).not.toMatch(/\bany\b/);
  });

  it("exports stable literal status, projection error, and sale status enums", () => {
    const openapi = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../openapi.json"), "utf8")) as { components: { schemas: Record<string, { properties?: Record<string, { enum?: string[]; type?: string }> }> } };
    expect(openapi.components.schemas.ChatResponse.properties?.status?.enum).toEqual(["completed", "confirmation_required", "cancelled", "failed"]);
    const projectionCode = openapi.components.schemas.ProjectionError.properties?.code;
    expect(projectionCode?.enum ?? (projectionCode as { const?: string } | undefined)?.const).toBe("recommendation_projection_corrupt");
    expect(openapi.components.schemas.AvailabilityView.properties?.sale_status?.enum).toEqual(["draft", "active", "inactive"]);
    expect(openapi.components.schemas.Money.properties?.amount?.type).toBe("string");
  });

  it("contains the Phase 5A Payment endpoints and status enums", () => {
    const openapi = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../openapi.json"), "utf8")) as { paths: Record<string, unknown>; components: { schemas: Record<string, { properties?: Record<string, { enum?: string[] }> }> } };
    expect(openapi.paths["/api/orders/{order_id}/payments"]).toBeDefined();
    expect(openapi.components.schemas.OrderView.properties?.status?.enum).toEqual(["pending_payment", "cancelled", "paid"]);
    expect(openapi.components.schemas.PaymentAttemptView.properties?.status?.enum).toEqual(["processing", "unknown", "provider_succeeded", "failed", "succeeded"]);
  });

  it("keeps generated JSON and TypeScript paths aligned with current commerce", () => {
    const openapi = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../openapi.json"), "utf8")) as { paths: Record<string, unknown> };
    const generated = readFileSync(resolve(import.meta.dirname, "openapi.generated.ts"), "utf8");
    const requiredPaths = [
      "/api/cart",
      "/api/checkout/preview",
      "/api/health/outbox",
      "/api/orders",
      "/api/orders/{order_id}/payments",
      "/api/pending-actions/add-to-cart",
    ];

    for (const path of requiredPaths) {
      expect(openapi.paths[path]).toBeDefined();
      expect(generated).toContain(`"${path}":`);
    }
  });
});
