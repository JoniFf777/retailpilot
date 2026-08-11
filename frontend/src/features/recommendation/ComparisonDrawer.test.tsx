import { fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { describe, expect, it } from "vitest";
import type { RecommendationChoice } from "./recommendationTypes";
import { ComparisonDrawer } from "./ComparisonDrawer";

const choices: RecommendationChoice[] = [
  { sku_id: "sku-a", product_name: "A", sku_name: "A", money: { amount: "1.00", currency: "CNY" }, availability: { sale_status: "active", available_quantity: 2, in_stock: true }, specifications: [] },
  { sku_id: "sku-b", product_name: "B", sku_name: "B", money: { amount: "2.00", currency: "CNY" }, availability: { sale_status: "active", available_quantity: 2, in_stock: true }, specifications: [] },
];

function Fixture() {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  return <><input aria-label="输入焦点" /><button ref={triggerRef} type="button" onClick={() => setOpen(true)}>打开对比</button><ComparisonDrawer open={open} choices={choices} onClose={() => setOpen(false)} restoreFocus={triggerRef} /></>;
}

function SortFixture() {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const sortedChoices: RecommendationChoice[] = [
    { ...choices[0]!, specifications: [
      { code: "z", name: "Z 规格", value: "z", value_type: "string", comparable: true, display_order: 2 },
      { code: "a", name: "A 规格", value: "a", value_type: "string", comparable: true, display_order: 1 },
      { code: "hidden", name: "隐藏", value: true, value_type: "boolean", comparable: false, display_order: 0 },
    ] },
    { ...choices[1]!, specifications: [
      { code: "z", name: "Z 规格（另一数组顺序）", value: "z2", value_type: "string", comparable: true, display_order: 2 },
      { code: "a", name: "A 规格", value: "a2", value_type: "string", comparable: true, display_order: 1 },
    ] },
  ];
  return <><button ref={triggerRef} type="button">触发</button><ComparisonDrawer open choices={sortedChoices} onClose={() => undefined} restoreFocus={triggerRef} /></>;
}

describe("ComparisonDrawer focus lifecycle", () => {
  it("does not steal focus on initial closed mount", () => {
    render(<Fixture />);
    const input = screen.getByLabelText("输入焦点");
    input.focus();
    expect(document.activeElement).toBe(input);
  });

  it("focuses close on open and restores focus after Escape", () => {
    render(<Fixture />);
    const trigger = screen.getByRole("button", { name: "打开对比" });
    fireEvent.click(trigger);
    expect(screen.getByRole("button", { name: "关闭对比" })).toHaveFocus();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(trigger).toHaveFocus();
  });

  it("restores focus after clicking close", () => {
    render(<Fixture />);
    const trigger = screen.getByRole("button", { name: "打开对比" });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "关闭对比" }));
    expect(trigger).toHaveFocus();
  });

  it("sorts comparable specification rows by display order then code", () => {
    render(<SortFixture />);
    const rows = screen.getAllByRole("row").map((row) => row.querySelector("th")?.textContent);
    expect(rows).toEqual(["项目", "价格", "库存", "综合匹配", "A 规格", "Z 规格"]);
    expect(screen.queryByText("隐藏")).not.toBeInTheDocument();
  });
});
