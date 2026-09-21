import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Badge, Button, Card, Empty, Field, Skeleton, Spinner } from ".";

describe("Button", () => {
  it("defaults to type=button so it never submits a form by accident", () => {
    render(<Button>保存</Button>);
    expect(screen.getByRole("button", { name: "保存" })).toHaveAttribute("type", "button");
  });

  it("passes className, data-testid and aria attributes through", () => {
    render(
      <Button aria-label="确认" className="cart-checkout-button" data-testid="action-confirm">
        ok
      </Button>,
    );
    const button = screen.getByTestId("action-confirm");
    expect(button).toHaveClass("cart-checkout-button");
    expect(button).toHaveAccessibleName("确认");
  });

  it("blocks clicks and marks itself busy while loading", () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        提交
      </Button>,
    );
    const button = screen.getByRole("button", { name: /提交/ });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("fires onClick when enabled", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>提交</Button>);
    fireEvent.click(screen.getByRole("button", { name: "提交" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe("Card", () => {
  it("renders the requested element so semantic contracts such as <article> hold", () => {
    render(
      <Card as="article" className="recommendation-card" data-testid="card">
        内容
      </Card>,
    );
    const card = screen.getByTestId("card");
    expect(card.tagName).toBe("ARTICLE");
    expect(card).toHaveClass("recommendation-card");
  });
});

describe("Field", () => {
  it("associates the label with the control", () => {
    render(
      <Field htmlFor="goal" label="目标">
        <input id="goal" />
      </Field>,
    );
    expect(screen.getByLabelText("目标")).toBeInTheDocument();
  });

  it("shows the error as an alert and hides the hint while an error exists", () => {
    const { rerender } = render(
      <Field hint="至少 5 个字" htmlFor="goal" label="目标">
        <input id="goal" />
      </Field>,
    );
    expect(screen.getByText("至少 5 个字")).toBeInTheDocument();
    rerender(
      <Field error="不能为空" hint="至少 5 个字" htmlFor="goal" label="目标">
        <input id="goal" />
      </Field>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("不能为空");
    expect(screen.queryByText("至少 5 个字")).not.toBeInTheDocument();
  });
});

describe("Empty", () => {
  it("renders title, description and action", () => {
    render(
      <Empty
        action={<button type="button">新建</button>}
        description="先创建一个"
        title="还没有任务"
      />,
    );
    expect(screen.getByText("还没有任务")).toBeInTheDocument();
    expect(screen.getByText("先创建一个")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建" })).toBeInTheDocument();
  });
});

describe("Badge, Spinner and Skeleton", () => {
  it("renders badge text", () => {
    render(<Badge tone="agent-rag">RAG</Badge>);
    expect(screen.getByText("RAG")).toBeInTheDocument();
  });

  it("gives the spinner an accessible name", () => {
    render(<Spinner label="正在保存" />);
    expect(screen.getByRole("img", { name: "正在保存" })).toBeInTheDocument();
  });

  it("hides the skeleton from assistive technology", () => {
    render(<Skeleton data-testid="skeleton" />);
    expect(screen.getByTestId("skeleton")).toHaveAttribute("aria-hidden", "true");
  });
});
