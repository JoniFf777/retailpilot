import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "./App";

describe("ShopMind shell", () => {
  it("renders the F0 navigation shell", () => {
    render(<MemoryRouter initialEntries={["/"]}><Routes><Route element={<App />} path="/" /></Routes></MemoryRouter>);
    expect(screen.getByRole("link", { name: /ShopMind/ })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
  });
});
