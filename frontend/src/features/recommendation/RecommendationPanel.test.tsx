import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RecommendationResult } from "../../api/contracts";
import { RecommendationPanel } from "./RecommendationPanel";
import { alternativeChoice } from "./recommendationTypes";
import { formatBudget } from "./recommendationFormatters";

const result: RecommendationResult = {
  schema_version: "shopmind.recommendation.v1", ranking_policy_version: "v1", request_summary: "开发笔记本", outcome: "recommended",
  structured_constraints: { memory_min_gb: 16, primary_use_cases: ["java_development"] },
  recommendations: [
    { product_id: "product-1", sku_id: "sku-1", product_name: "轻薄本 A", sku_name: "16G / 512G", money: { amount: "5999.00", currency: "CNY" }, availability: { sale_status: "active", in_stock: true, available_quantity: 9 }, score: 91, reason: "满足开发和轻便要求", score_breakdown: [{ code: "memory", name: "内存", points: 30, max_points: 30, reason: "16GB" }], specifications: [{ code: "memory", name: "内存", value: 16, value_type: "integer", unit: "GB", display_order: 1, comparable: true }] },
    { product_id: "product-2", sku_id: "sku-2", product_name: "轻薄本 B", sku_name: "16G / 1T", money: { amount: "6999.00", currency: "CNY" }, availability: { sale_status: "active", in_stock: true, available_quantity: 2 }, score: 88, reason: "更大存储", score_breakdown: [], specifications: [{ code: "memory", name: "内存", value: 16, value_type: "integer", unit: "GB", display_order: 1, comparable: true }] },
  ],
};

describe("RecommendationPanel", () => {
  it("only enables SKU selection with the message recommendation context", () => {
    const onSelectSku = vi.fn();
    const view = render(<RecommendationPanel recommendation={result} recommendationContext={{ source_run_id: "run-1" }} onSelectSku={onSelectSku} onFillPrompt={() => undefined} />);
    fireEvent.click(screen.getAllByRole("button", { name: "选择此商品" })[0]!);
    expect(onSelectSku).toHaveBeenCalledWith("sku-1", { source_run_id: "run-1" });
    view.rerender(<RecommendationPanel recommendation={result} onFillPrompt={() => undefined} />);
    expect(screen.getAllByRole("button", { name: "选择此商品" })[0]).toBeDisabled();
  });

  it("renders structured cards, display-only money, and an accessible comparison", () => {
    render(<RecommendationPanel recommendation={result} onFillPrompt={() => undefined} />);
    expect(screen.getByText("¥5,999.00")).toBeInTheDocument();
    expect(screen.queryByText("满足硬约束", { exact: false })).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "加入对比" })[0]!);
    fireEvent.click(screen.getByRole("button", { name: "加入对比" }));
    fireEvent.click(screen.getByRole("button", { name: "对比已选（2）" }));
    expect(screen.getByRole("dialog", { name: "SKU 对比" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not infer cards for a no-match response and fills without sending", () => {
    const fill = (prompt: string) => { expect(prompt).toContain("调整"); };
    render(<RecommendationPanel recommendation={{ ...result, outcome: "no_match", recommendations: [], no_match_reason: "预算过低" }} onFillPrompt={fill} />);
    expect(screen.getByText("暂时没有符合条件的商品")).toBeInTheDocument();
    expect(screen.queryByText("轻薄本 A")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "调整需求" }));
  });

  it("renders clarification without cards and supports alternatives without new ranking", () => {
    const clarificationFill = (prompt: string) => expect(prompt).toContain("补充");
    render(<RecommendationPanel recommendation={{ ...result, outcome: "clarification_required", recommendations: [], missing_fields: ["用途"], clarification_question: "请补充主要用途" }} onFillPrompt={clarificationFill} />);
    expect(screen.getByText("请补充主要用途")).toBeInTheDocument();
    expect(screen.queryByText("推荐 1")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "补充信息" }));
  });

  it("formats budgets without exchange-rate arithmetic and merges alternative specs", () => {
    expect(formatBudget("6000", "CNY")).toBe("¥6,000.00");
    expect(formatBudget("6000", "XYZ")).toBe("6,000.00 XYZ");
    const merged = alternativeChoice(result.recommendations![0]!, { sku_id: "alt-1", sku_code: "ALT-1", sku_name: "替代 SKU", money: { amount: "6099.00", currency: "CNY" }, availability: { sale_status: "active", available_quantity: 1, in_stock: true }, differing_specifications: [{ code: "memory", name: "内存", value: 32, value_type: "integer", unit: "GB", display_order: 1, comparable: true }] });
    expect(merged.specifications.find((specification) => specification.code === "memory")?.value).toBe(32);
  });

  it("shows projection error as fixed public Chinese copy", () => {
    render(<RecommendationPanel projectionError={{ code: "recommendation_projection_corrupt", message: "backend secret detail" }} onFillPrompt={() => undefined} />);
    expect(screen.getByText("结构化推荐暂时无法显示，你仍可以查看文字回答或重新发起请求。")).toBeInTheDocument();
    expect(screen.queryByText("backend secret detail")).not.toBeInTheDocument();
  });

  it("supports three main SKUs plus one alternative and rejects a fifth", () => {
    const first = result.recommendations![0]!;
    const alternativeA = { sku_id: "alt-a", sku_code: "ALT-A", sku_name: "替代 A", money: { amount: "6199.00", currency: "CNY" }, availability: { sale_status: "active" as const, available_quantity: 2, in_stock: true }, differing_specifications: [] };
    const alternativeB = { ...alternativeA, sku_id: "alt-b", sku_code: "ALT-B", sku_name: "替代 B" };
    const three = { ...result, recommendations: [
      { ...first, alternative_skus: [alternativeA, alternativeB] },
      { ...result.recommendations![1]!, sku_id: "sku-2" },
      { ...first, sku_id: "sku-3", product_id: "product-3", product_name: "轻薄本 C", alternative_skus: [] },
    ] };
    render(<RecommendationPanel recommendation={three} onFillPrompt={() => undefined} />);
    const card = screen.getByRole("article", { name: "推荐 1：轻薄本 A" });
    fireEvent.click(within(card).getAllByRole("button", { name: "加入对比" }).at(-1)!);
    fireEvent.click(within(card).getAllByRole("button", { name: "加入对比" })[0]!);
    fireEvent.click(within(screen.getByRole("article", { name: "推荐 2：轻薄本 B" })).getByRole("button", { name: "加入对比" }));
    fireEvent.click(within(screen.getByRole("article", { name: "推荐 3：轻薄本 C" })).getByRole("button", { name: "加入对比" }));
    expect(screen.getByRole("button", { name: "对比已选（4）" })).toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "加入对比" }));
    expect(screen.getByRole("alert")).toHaveTextContent("最多比较 4 项");
  });
});
