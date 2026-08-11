export const ordersQueryKey = (identity: string) => ["shopmind-orders", identity] as const;
export const orderQueryKey = (identity: string, orderId: string) => ["shopmind-order", identity, orderId] as const;
