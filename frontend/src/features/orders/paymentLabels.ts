import type { PaymentAttemptView } from "../../api/contracts";

export const PAYMENT_STATUS_LABELS: Record<PaymentAttemptView["status"], string> = {
  processing: "支付处理中",
  unknown: "支付结果暂未确认",
  provider_succeeded: "支付方已确认成功",
  failed: "支付失败",
  succeeded: "支付成功",
};
