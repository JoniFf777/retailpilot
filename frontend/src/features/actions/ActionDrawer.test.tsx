import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ActionDrawer } from "./ActionDrawer";

const addAction = { id: "pending-add-1", actionType: "add_to_cart" as const, riskClass: "high" as const, preview: "加入 1 件 TECH-KEY-010" };

describe("HITL action drawer", () => {
  it("sends the exact add-to-cart edit schema", () => {
    const onConfirm = vi.fn();
    render(<ActionDrawer action={addAction} busy={false} error={null} onCancel={vi.fn()} onConfirm={onConfirm} />);
    fireEvent.change(screen.getByTestId("action-quantity"), { target: { value: "2" } });
    fireEvent.click(screen.getByTestId("action-confirm"));
    expect(onConfirm).toHaveBeenCalledWith({ quantity: 2 });
  });

  it("rejects an incomplete preference edit before network submission", () => {
    const onConfirm = vi.fn();
    render(<ActionDrawer action={{ ...addAction, actionType: "save_preference", riskClass: "medium" }} busy={false} error={null} onCancel={vi.fn()} onConfirm={onConfirm} />);
    fireEvent.change(screen.getByLabelText("偏好类型"), { target: { value: "brand" } });
    fireEvent.click(screen.getByTestId("action-confirm"));
    expect(screen.getByRole("alert")).toHaveTextContent("同时填写偏好内容");
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
