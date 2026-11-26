import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TermNote } from "./TermNote";

describe("术语注解", () => {
  it("悬停与聚焦均不展开，点击才在页面内显示解释", () => {
    render(<TermNote term="residual">残差</TermNote>);
    const label = screen.getByText("残差");
    const trigger = screen.getByRole("button", { name: "查看残差的解释" });
    const explanation = screen.getByText(/基金区间收益减去已知持仓贡献合计/);

    fireEvent.mouseEnter(label);
    fireEvent.focus(trigger);
    expect(explanation).not.toBeVisible();
    expect(trigger).toHaveClass("cursor-pointer");
    expect(trigger).not.toHaveClass("cursor-help");

    fireEvent.click(label);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(explanation).toBeVisible();
    expect(trigger.parentElement).toContainElement(explanation);

    fireEvent(trigger, new MouseEvent("pointerout", { bubbles: true, relatedTarget: explanation }));
    expect(explanation).toBeVisible();
    fireEvent(explanation, new MouseEvent("pointerout", { bubbles: true, relatedTarget: document.body }));
    expect(explanation).not.toBeVisible();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("再次点击、Escape 或点击外部都能收起", () => {
    render(<TermNote term="contribution">贡献</TermNote>);
    const trigger = screen.getByRole("button", { name: "查看贡献的解释" });
    const explanation = screen.getByText(/披露权重 × 个股区间收益/);

    fireEvent.click(trigger);
    expect(trigger).toHaveAccessibleDescription(explanation.textContent ?? "");
    fireEvent.click(trigger);
    expect(explanation).not.toBeVisible();

    fireEvent.click(trigger);
    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(explanation).not.toBeVisible();

    fireEvent.click(trigger);
    fireEvent.pointerDown(document.body);
    expect(explanation).not.toBeVisible();
  });
});
