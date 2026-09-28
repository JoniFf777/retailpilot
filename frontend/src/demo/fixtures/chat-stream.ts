import type {
  CatalogSpecificationView,
  ChatResponse,
  ProductSpecificationView,
  Recommendation,
  RecommendationResult,
} from "../../api/contracts";
import { DEMO_PRODUCTS, findDemoProductByCode } from "./catalog";

/** Chat scenario data, keyed to the same SKUs `fixtures/catalog.ts` seeds, so a demo
 *  session's chat answers, the catalog browse pages, and the cart/checkout/orders that
 *  follow all agree on the same product names, prices, and IDs. */

/** `Recommendation.specifications` is `ProductSpecificationView[]` (code/name/"integer"),
 *  a different shape than the catalog's own `CatalogSkuView.variant_specifications`
 *  (key/label/"number") that `comparison_fields` below reuses directly — same facts,
 *  two label conventions, because they're independent generated schemas. */
function toProductSpecifications(specs: CatalogSpecificationView[]): ProductSpecificationView[] {
  return specs.map((spec) => ({
    code: spec.key,
    name: spec.label,
    value: spec.value,
    value_type:
      spec.value_type === "number"
        ? "decimal"
        : spec.value_type === "enum"
          ? "string"
          : spec.value_type,
    unit: spec.unit,
    comparable: spec.comparable,
    display_order: spec.display_order,
  }));
}

function recommendationOf(
  product: (typeof DEMO_PRODUCTS)["laptop"][number],
  score: number,
  reason: string,
  opts: {
    matchedHard?: string[];
    matchedSoft?: string[];
    tradeoffs?: string[];
    degraded?: boolean;
  } = {},
): Recommendation {
  const sku = product.skus[0]!;
  return {
    product_id: product.product_id,
    product_name: product.name,
    sku_id: sku.sku_id,
    sku_name: sku.sku_name,
    money: sku.money,
    availability: sku.availability,
    category_display_name: product.category.display_name,
    score,
    reason,
    score_breakdown: [
      {
        code: "budget",
        name: "预算匹配",
        points: Math.round(score * 0.4),
        max_points: 40,
        reason: "命中预算区间",
      },
      {
        code: "spec",
        name: "配置匹配",
        points: Math.round(score * 0.6),
        max_points: 60,
        reason: "满足关键配置要求",
      },
    ],
    specifications: toProductSpecifications(sku.variant_specifications ?? []),
    comparison_fields: sku.variant_specifications ?? [],
    matched_hard_constraints: opts.matchedHard ?? ["availability"],
    matched_soft_preferences: opts.matchedSoft ?? [],
    soft_tradeoffs: opts.tradeoffs ?? [],
    unmatched_soft_constraints: [],
    alternative_skus: [],
    evidence: opts.degraded
      ? []
      : [
          {
            source: "policy",
            type: "citation",
            field: "warranty",
            value: "两年保修，7 天无理由退货",
            ref: "P-1",
          },
        ],
  };
}

function baseResult(overrides: Partial<RecommendationResult>): RecommendationResult {
  return {
    schema_version: "shopmind.recommendation.v1",
    outcome: "recommended",
    ranking_policy_version: "demo-v1",
    request_summary: "演示请求",
    category: null,
    category_display_name: null,
    structured_constraints: {},
    evidence_status: "available",
    recommendations: [],
    ...overrides,
  };
}

/** 正常：预算充足的开发本查询，返回 3 款笔记本，带软偏好命中比例可演示。 */
export function normalLaptopRecommendation(): RecommendationResult {
  const [proA, bizB, gameC] = DEMO_PRODUCTS.laptop;
  return baseResult({
    category: "laptop",
    category_display_name: "笔记本电脑",
    request_summary: "预算 12000 元以内，适合开发和出差的轻薄笔记本",
    constraint_fields: [
      {
        key: "weight",
        label: "重量至多",
        value: 1.5,
        value_type: "number",
        unit: "kg",
        comparable: true,
        display_order: 1,
      },
    ],
    recognized_constraints: {
      weight: { operator: "lte", polarity: "include", role: "soft", value: 1.5 },
    },
    recommendations: [
      recommendationOf(proA!, 92, "内存和存储都满足开发需求，机身最轻，适合出差携带", {
        matchedSoft: ["weight"],
      }),
      recommendationOf(bizB!, 86, "预算内性价比最高，续航和做工适合日常办公", {
        matchedSoft: ["weight"],
      }),
      recommendationOf(gameC!, 79, "性能最强但偏重，长时间携带不够轻便", {
        tradeoffs: ["机身较重，超出你偏好的重量上限"],
      }),
    ],
  });
}

/** 证据降级：同样的推荐结果，但文档检索通道降级，用于演示 evidence_status 的界面处理。 */
export function degradedEvidenceRecommendation(): RecommendationResult {
  const [proA, bizB] = DEMO_PRODUCTS.laptop;
  return baseResult({
    category: "laptop",
    category_display_name: "笔记本电脑",
    request_summary: "开发用笔记本，需要引用保修和退货政策",
    evidence_status: "degraded",
    policy_evidence: [
      {
        source: "policy",
        type: "citation",
        field: "return_policy",
        section: "退货",
        value: "退货期限为七天",
        document_version: "2026.09",
      },
    ],
    recommendations: [
      recommendationOf(proA!, 90, "配置满足开发需求", { degraded: true }),
      recommendationOf(bizB!, 84, "预算内性价比最高", { degraded: true }),
    ],
  });
}

/** 显示器场景，复用同一套推荐结构，换一个分类。 */
export function monitorRecommendation(): RecommendationResult {
  const [mon4k, monUltrawide] = DEMO_PRODUCTS.monitor;
  return baseResult({
    category: "monitor",
    category_display_name: "显示器",
    request_summary: "适合办公和轻度设计工作的显示器",
    recommendations: [
      recommendationOf(mon4k!, 88, "4K 分辨率适合文档和设计工作", {
        matchedHard: ["availability"],
      }),
      recommendationOf(monUltrawide!, 81, "带鱼屏适合多窗口办公，但对桌面空间要求更高", {
        tradeoffs: ["尺寸较大，占用更多桌面空间"],
      }),
    ],
  });
}

/** 预算冲突：没有命中任何候选商品。 */
export function noMatchRecommendation(): RecommendationResult {
  return baseResult({
    outcome: "no_match",
    request_summary: "预算 1000 元以内的笔记本",
    no_match_reason: "当前目录下没有 1000 元以内、且满足基础配置要求的笔记本。",
    recommendations: [],
  });
}

/** 需要澄清：请求太模糊，无法判断品类或关键约束。 */
export function clarificationRecommendation(): RecommendationResult {
  return baseResult({
    outcome: "clarification_required",
    request_summary: "推荐点东西",
    clarification_question: "方便说说主要用途和预算范围吗？比如开发、办公，或者显示器。",
    missing_fields: ["用途", "预算"],
    recommendations: [],
  });
}

/** 直接按商品编码回答价格（不走推荐卡片），对应 ChatPage 自带的 "TECH-LAP-001 多少钱？" 快捷问题。 */
export function skuLookupAnswer(productCode: string): string | null {
  const product = findDemoProductByCode(productCode);
  if (!product) return null;
  const sku = product.skus[0]!;
  return `${product.name}（${sku.sku_name}）目前售价 ${sku.money.currency} ${sku.money.amount} 元，${sku.availability.in_stock ? `库存 ${sku.availability.available_quantity} 件` : "暂时缺货"}。`;
}

export function chatAnswerFor(result: RecommendationResult): string {
  if (result.outcome === "no_match") return "抱歉，暂时没有符合条件的商品。";
  if (result.outcome === "clarification_required") return "还需要补充一点信息才能推荐。";
  return `为你整理了 ${result.recommendations?.length ?? 0} 款候选，可以直接选择或继续对比。`;
}

export function buildChatResponse(
  result: RecommendationResult,
  threadId: string,
  runId: string,
): ChatResponse {
  return {
    answer: chatAnswerFor(result),
    status: "completed",
    retry_state: "none",
    thread_id: threadId,
    tool_calls: [],
    pending_action_id: null,
    projection_error: null,
    recommendation: result,
    recommendation_context: result.outcome === "recommended" ? { source_run_id: runId } : null,
  };
}
