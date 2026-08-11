/**
 * Browser-facing aliases for the generated OpenAPI contract.
 *
 * Keep this file declarative: OpenAPI owns HTTP request/response shapes, while
 * `sseTypes.ts` owns the intentionally separate streaming envelope.
 */
import type { components, operations } from "./openapi.generated";

export type AlternativeSkuView = components["schemas"]["AlternativeSkuView"];
export type AvailabilityView = components["schemas"]["AvailabilityView"];
export type ChatRequest = components["schemas"]["ChatRequest"];
export type ChatResponse = components["schemas"]["ChatResponse"];
export type ConfirmChatRequest = components["schemas"]["ConfirmChatRequest"];
export type EvidenceView = components["schemas"]["EvidenceView"];
export type LaptopConstraints = components["schemas"]["LaptopConstraints"];
export type Money = components["schemas"]["Money"];
export type ProductSpecificationView = components["schemas"]["ProductSpecificationView"];
export type ProjectionError = components["schemas"]["ProjectionError"];
export type Recommendation = components["schemas"]["Recommendation"];
export type RecommendationResult = components["schemas"]["RecommendationResult"];
export type ScoreBreakdownItem = components["schemas"]["ScoreBreakdownItem"];
export type RecommendationContextView = components["schemas"]["RecommendationContextView"];
export type PendingActionView = components["schemas"]["PendingActionView"];
export type AddToCartPreview = components["schemas"]["AddToCartPreview"];
export type IntegerEditableField = components["schemas"]["IntegerEditableField"];
export type EnumEditableField = components["schemas"]["EnumEditableField"];
export type TextEditableField = components["schemas"]["TextEditableField"];
export type EditableField = IntegerEditableField | EnumEditableField | TextEditableField;
export type AddToCartPendingActionRequest = components["schemas"]["AddToCartPendingActionRequest"];
export type PendingActionTransitionRequest = components["schemas"]["PendingActionTransitionRequest"];
export type PendingActionCancelRequest = components["schemas"]["PendingActionCancelRequest"];
export type PendingActionTransitionResponse = components["schemas"]["PendingActionTransitionResponse"];
export type PendingActionErrorDetails = components["schemas"]["PendingActionErrorDetails"];
export type ActionErrorResponse = components["schemas"]["ActionErrorResponse"];
export type CartItemView = components["schemas"]["CartItemView"];
export type CartResponse = components["schemas"]["CartResponse"];
export type CartWarning = components["schemas"]["CartWarning"];
export type CartWarningCode = CartWarning["code"];
export type UpdateCartItemRequest = components["schemas"]["UpdateCartItemRequest"];
export type CartMutationResponse = components["schemas"]["CartMutationResponse"];
export type CartErrorResponse = components["schemas"]["CartErrorResponse"];
export type CartErrorDetails = components["schemas"]["CartErrorDetails"];
export type CartErrorCode = CartErrorResponse["code"];
export type ActionErrorCode = ActionErrorResponse["code"];
export type CheckoutPreview = components["schemas"]["CheckoutPreview"];
export type CheckoutPreviewItem = components["schemas"]["CheckoutPreviewItem"];
export type CheckoutWarning = components["schemas"]["CheckoutWarning"];
export type CheckoutErrorResponse = components["schemas"]["CheckoutErrorResponse"];
export type CreateOrderRequest = components["schemas"]["CreateOrderRequest"];
export type CreateOrderResponse = components["schemas"]["CreateOrderResponse"];
export type OrderView = components["schemas"]["OrderView"];
export type OrderItemView = components["schemas"]["OrderItemView"];
export type OrderListResponse = components["schemas"]["OrderListResponse"];
export type CancelOrderResponse = components["schemas"]["CancelOrderResponse"];
export type OrderErrorResponse = components["schemas"]["OrderErrorResponse"];
export type OrderErrorCode = OrderErrorResponse["code"];
export type PaymentAttemptRequest = components["schemas"]["PaymentAttemptRequest"];
export type PaymentAttemptResponse = components["schemas"]["PaymentAttemptResponse"];
export type PaymentAttemptListResponse = components["schemas"]["PaymentAttemptListResponse"];
export type PaymentAttemptView = components["schemas"]["PaymentAttemptView"];
export type PaymentAttemptStatus = PaymentAttemptView["status"];
export type PaymentErrorResponse = components["schemas"]["PaymentErrorResponse"];
export type PaymentErrorCode = PaymentErrorResponse["code"];

export type OwnerDataCounts = components["schemas"]["OwnerDataCounts"];
export type OwnerDataSnapshot = components["schemas"]["OwnerDataSnapshot"];
export type OwnerMemoryRecord = components["schemas"]["OwnerMemoryRecord"];
export type OwnerMemoryCorrection = components["schemas"]["OwnerMemoryCorrection"];
export type OwnerMemoryDeletion = components["schemas"]["OwnerMemoryDeletion"];
export type OwnerDataDeletion = components["schemas"]["OwnerDataDeletion"];
export type OwnerRunInspection = components["schemas"]["OwnerRunInspection"];
export type OwnerRunEventSummary = components["schemas"]["OwnerRunEventSummary"];
export type RunUsage = components["schemas"]["RunUsage"];
export type MemoryKind = components["schemas"]["MemoryKind"];
export type MemoryScope = components["schemas"]["MemoryScope"];
export type RunOperation = components["schemas"]["RunOperation"];
export type RunMode = components["schemas"]["RunMode"];
export type RunStatus = components["schemas"]["RunStatus"];
export type ApiErrorBody = components["schemas"]["HTTPValidationError"];

export type HealthResponse = operations["health_check_api_health_get"]["responses"][200]["content"]["application/json"];
export type ReadinessResponse = operations["deployment_readiness_health_check_api_health_readiness_get"]["responses"][200]["content"]["application/json"];
