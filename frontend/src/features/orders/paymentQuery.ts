export const paymentAttemptsQueryKey = (identity: string, orderId: string) => ["shopmind-payments", identity, orderId] as const;
