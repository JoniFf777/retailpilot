export const catalogCategoriesQueryKey = ["shopmind-catalog", "categories"] as const;
export const catalogProductsQueryKey = (category: string) => ["shopmind-catalog", "products", category] as const;
export const catalogProductQueryKey = (productCode: string) => ["shopmind-catalog", "product", productCode] as const;
