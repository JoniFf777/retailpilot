import { expect, test } from "@playwright/test";

test("browses categories and reaches canonical PendingAction confirmation", async ({ page }) => {
  await page.goto("/catalog");
  await expect(page.getByRole("heading", { name: "浏览商品" })).toBeVisible();
  await expect(page.getByRole("link", { name: /手机/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /键盘/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /路由器/ })).toBeVisible();

  await page.getByRole("link", { name: /手机/ }).click();
  await expect(page).toHaveURL(/\/catalog\/phone$/);
  await expect(page.locator("article.catalog-product-card").first()).toBeVisible();
  await page.locator("article.catalog-product-card").first().getByRole("link", { name: "查看详情" }).click();
  await expect(page).toHaveURL(/\/catalog\/phone\//);
  await expect(page.getByRole("heading", { name: "结构化规格" })).toBeVisible();

  await page.goto("/catalog");
  await page.getByRole("link", { name: /路由器/ }).click();
  await page.locator("article.catalog-product-card").first().getByRole("link", { name: "查看详情" }).click();
  await expect(page).toHaveURL(/\/catalog\/router\//);
  await expect(page.getByRole("heading", { name: "可选 SKU" })).toBeVisible();
  await page.getByRole("button", { name: "加入购物车" }).first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByTestId("action-confirm").click();
  await expect(page.getByRole("status")).toContainText("已加入购物车");
});
