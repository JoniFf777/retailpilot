import type {
  CatalogCategoryView,
  CatalogProductDetail,
  CatalogProductSummary,
  CatalogSkuView,
} from "../../api/contracts";

/** A small, self-consistent catalog: 2 categories, 5 products, 1 SKU each. Referenced by
 *  chat's recommendation fixtures too (src/demo/fixtures/chat-stream.ts), so a demo
 *  session's chat answers, catalog browse pages, and cart/checkout/orders all agree on
 *  the same product names, prices, and IDs — one source of truth, not three. */

function money(amount: string): { amount: string; currency: string } {
  return { amount, currency: "CNY" };
}

const LAPTOP_CATEGORY: CatalogCategoryView = {
  code: "laptop",
  display_name: "笔记本电脑",
  product_count: 3,
  available_product_count: 3,
};

const MONITOR_CATEGORY: CatalogCategoryView = {
  code: "monitor",
  display_name: "显示器",
  product_count: 2,
  available_product_count: 2,
};

export const DEMO_CATEGORIES: CatalogCategoryView[] = [LAPTOP_CATEGORY, MONITOR_CATEGORY];

function laptopSku(
  skuId: string,
  skuCode: string,
  amount: string,
  memoryGb: number,
  storageGb: number,
  weightKg: number,
  availableQuantity = 12,
): CatalogSkuView {
  return {
    sku_id: skuId,
    sku_code: skuCode,
    sku_name: `${memoryGb}GB/${storageGb}GB`,
    money: money(amount),
    availability: {
      sale_status: "active",
      in_stock: availableQuantity > 0,
      available_quantity: availableQuantity,
    },
    variant_specifications: [
      {
        key: "memory",
        label: "内存",
        value: memoryGb,
        value_type: "number",
        unit: "GB",
        comparable: true,
        display_order: 1,
      },
      {
        key: "storage",
        label: "存储",
        value: storageGb,
        value_type: "number",
        unit: "GB",
        comparable: true,
        display_order: 2,
      },
      {
        key: "weight",
        label: "重量",
        value: weightKg,
        value_type: "number",
        unit: "kg",
        comparable: true,
        display_order: 3,
      },
    ],
  };
}

export const DEMO_PRODUCTS: Record<"laptop" | "monitor", CatalogProductSummary[]> = {
  laptop: [
    {
      product_id: "00000000-0000-4000-c000-000000000001",
      product_code: "TECH-LAP-001",
      name: "轻薄本 Pro 14",
      brand: "RetailPilot Select",
      category: LAPTOP_CATEGORY,
      specifications: [],
      skus: [
        laptopSku(
          "00000000-0000-4000-c000-000000000101",
          "TECH-LAP-001-A",
          "8999.00",
          16,
          512,
          1.2,
        ),
      ],
    },
    {
      product_id: "00000000-0000-4000-c000-000000000002",
      product_code: "TECH-LAP-002",
      name: "商务本 X1",
      brand: "Vantage",
      category: LAPTOP_CATEGORY,
      specifications: [],
      skus: [
        laptopSku(
          "00000000-0000-4000-c000-000000000201",
          "TECH-LAP-002-A",
          "6499.00",
          16,
          512,
          1.4,
        ),
      ],
    },
    {
      product_id: "00000000-0000-4000-c000-000000000003",
      product_code: "TECH-LAP-003",
      name: "游戏本 G5",
      brand: "Vantage",
      category: LAPTOP_CATEGORY,
      specifications: [],
      skus: [
        laptopSku(
          "00000000-0000-4000-c000-000000000301",
          "TECH-LAP-003-A",
          "10999.00",
          32,
          1024,
          2.4,
          3,
        ),
      ],
    },
  ],
  monitor: [
    {
      product_id: "00000000-0000-4000-c000-000000000004",
      product_code: "TECH-MON-001",
      name: "27 英寸 4K 显示器",
      brand: "RetailPilot Select",
      category: MONITOR_CATEGORY,
      specifications: [],
      skus: [
        {
          sku_id: "00000000-0000-4000-c000-000000000401",
          sku_code: "TECH-MON-001-A",
          sku_name: "27 英寸 / 4K",
          money: money("2399.00"),
          availability: { sale_status: "active", in_stock: true, available_quantity: 20 },
          variant_specifications: [
            {
              key: "size",
              label: "尺寸",
              value: 27,
              value_type: "number",
              unit: "英寸",
              comparable: true,
              display_order: 1,
            },
            {
              key: "resolution",
              label: "分辨率",
              value: "3840x2160",
              value_type: "string",
              comparable: true,
              display_order: 2,
            },
          ],
        },
      ],
    },
    {
      product_id: "00000000-0000-4000-c000-000000000005",
      product_code: "TECH-MON-002",
      name: "34 英寸带鱼屏",
      brand: "Vantage",
      category: MONITOR_CATEGORY,
      specifications: [],
      skus: [
        {
          sku_id: "00000000-0000-4000-c000-000000000501",
          sku_code: "TECH-MON-002-A",
          sku_name: "34 英寸 / 带鱼屏",
          money: money("3699.00"),
          availability: { sale_status: "active", in_stock: true, available_quantity: 6 },
          variant_specifications: [
            {
              key: "size",
              label: "尺寸",
              value: 34,
              value_type: "number",
              unit: "英寸",
              comparable: true,
              display_order: 1,
            },
            {
              key: "resolution",
              label: "分辨率",
              value: "3440x1440",
              value_type: "string",
              comparable: true,
              display_order: 2,
            },
          ],
        },
      ],
    },
  ],
};

export const ALL_DEMO_PRODUCTS: CatalogProductSummary[] = [
  ...DEMO_PRODUCTS.laptop,
  ...DEMO_PRODUCTS.monitor,
];

export function demoProductDetail(product: CatalogProductSummary): CatalogProductDetail {
  return {
    product_id: product.product_id,
    product_code: product.product_code,
    name: product.name,
    brand: product.brand,
    category: product.category,
    description: `${product.name}，${product.category.display_name}分类下的演示商品。`,
    specifications: product.skus[0]?.variant_specifications ?? [],
    skus: product.skus,
  };
}

export function findDemoSkuByCode(
  skuCode: string,
): { product: CatalogProductSummary; sku: CatalogSkuView } | null {
  for (const product of ALL_DEMO_PRODUCTS) {
    const sku = product.skus.find((candidate) => candidate.sku_code === skuCode);
    if (sku) return { product, sku };
  }
  return null;
}

export function findDemoSkuById(
  skuId: string,
): { product: CatalogProductSummary; sku: CatalogSkuView } | null {
  for (const product of ALL_DEMO_PRODUCTS) {
    const sku = product.skus.find((candidate) => candidate.sku_id === skuId);
    if (sku) return { product, sku };
  }
  return null;
}

export function findDemoProductByCode(productCode: string): CatalogProductSummary | null {
  return ALL_DEMO_PRODUCTS.find((product) => product.product_code === productCode) ?? null;
}
