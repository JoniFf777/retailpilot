import { describe, expect, it } from "vitest";
import { validateCartQuantity } from "./quantity";

describe("Cart quantity validation", () => {
  it.each([["1", true], ["20", true], ["0", false], ["21", false], ["1.5", false], ["abc", false], ["", false]])("validates %s", (value, valid) => {
    expect(validateCartQuantity(value).valid).toBe(valid);
  });
});
