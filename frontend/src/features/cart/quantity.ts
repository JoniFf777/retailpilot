export const MIN_CART_QUANTITY = 1;
export const MAX_CART_QUANTITY = 20;

export type QuantityValidation = { valid: true; quantity: number } | { valid: false; message: string };

export function validateCartQuantity(value: string): QuantityValidation {
  if (!/^\d+$/.test(value)) return { valid: false, message: "请输入 1 到 20 之间的整数。" };
  const quantity = Number(value);
  if (!Number.isInteger(quantity) || quantity < MIN_CART_QUANTITY || quantity > MAX_CART_QUANTITY) {
    return { valid: false, message: "请输入 1 到 20 之间的整数。" };
  }
  return { valid: true, quantity };
}
