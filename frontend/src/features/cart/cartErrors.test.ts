import { describe, expect, it } from "vitest";
import { cartErrorMessage, cartWarningMessage, insufficientInventoryMessage } from "./cartErrors";

describe("Cart error and warning copy", () => {
  it("maps stable Cart error codes to Chinese copy", () => {
    expect(cartErrorMessage({ code: "cart_version_conflict", message: "server text" })).toBe("购物车已在其他操作中更新，已为你刷新最新状态。");
    expect(cartErrorMessage({ code: "product_inactive", message: "server text" })).toContain("下架");
  });

  it("keeps shortage details without clamping the draft", () => {
    expect(insufficientInventoryMessage({ code: "insufficient_inventory", message: "server text", details: { available_quantity: 2 } })).toBe("当前库存最多可支持 2 件。");
  });

  it("uses backend warning codes", () => {
    expect(cartWarningMessage({ code: "mixed_currency", message: "server text" })).toBe("购物车包含不同币种，暂不计算合计。");
  });
});
