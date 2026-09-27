/**
 * Browser-facing aliases for the generated OpenAPI contract.
 *
 * Keep this file declarative: OpenAPI owns HTTP request/response shapes, while
 * `sseTypes.ts` owns the intentionally separate streaming envelope.
 */
import type { components, operations } from "./openapi.generated";

export type AlternativeSkuView = components["schemas"]["AlternativeSkuView"];
export type AvailabilityView = components["schemas"]["AvailabilityView"];
export type CategoryAttributeConstraint = components["schemas"]["CategoryAttributeConstraint"];
export type ChatRequest = components["schemas"]["ChatRequest"];
export type ChatResponse = components["schemas"]["ChatResponse"];
export type ComparisonField = components["schemas"]["ComparisonField"];
export type ConfirmChatRequest = components["schemas"]["ConfirmChatRequest"];
export type EvidenceView = components["schemas"]["EvidenceView"];
export type LaptopConstraints = components["schemas"]["LaptopConstraints"];
export type Money = components["schemas"]["Money"];
export type ProductSpecificationView = components["schemas"]["ProductSpecificationView"];
export type ProjectionError = components["schemas"]["ProjectionError"];
export type Recommendation = components["schemas"]["Recommendation"];
export type RecommendationRequest = components["schemas"]["RecommendationRequest"];
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
export type PendingActionTransitionRequest =
  components["schemas"]["PendingActionTransitionRequest"];
export type PendingActionCancelRequest = components["schemas"]["PendingActionCancelRequest"];
export type PendingActionTransitionResponse =
  components["schemas"]["PendingActionTransitionResponse"];
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

export type HealthResponse =
  operations["health_check_api_health_get"]["responses"][200]["content"]["application/json"];
export type ReadinessResponse =
  operations["deployment_readiness_health_check_api_health_readiness_get"]["responses"][200]["content"]["application/json"];
export type CatalogCategoryView = components["schemas"]["CatalogCategoryView"];
export type CatalogCategoryListResponse = components["schemas"]["CatalogCategoryListResponse"];
export type CatalogSpecificationView = components["schemas"]["CatalogSpecificationView"];
export type CatalogSkuView = components["schemas"]["CatalogSkuView"];
export type CatalogProductSummary = components["schemas"]["CatalogProductSummary"];
export type CatalogProductDetail = components["schemas"]["CatalogProductDetail"];
export type CatalogProductListResponse = components["schemas"]["CatalogProductListResponse"];
export type CatalogErrorResponse = components["schemas"]["CatalogErrorResponse"];
export type CatalogBrowseAddToCartPendingActionRequest =
  components["schemas"]["CatalogBrowseAddToCartPendingActionRequest"];

export type TaskKind = components["schemas"]["TaskSnapshot"]["kind"];
export type TaskStatus = components["schemas"]["TaskSnapshot"]["status"];
export type ShoppingTaskListItem = components["schemas"]["TaskListItemView"];
export type ShoppingTaskListResponse = components["schemas"]["TaskListResponse"];
export type ShoppingTaskSnapshot = components["schemas"]["TaskSnapshot"];
export type TaskStepView = components["schemas"]["TaskStepView"];
export type StepStatus = TaskStepView["status"];
export type PlanProposal = components["schemas"]["PlanProposal"];
export type PlanStep = components["schemas"]["PlanStep"];
export type TaskArtifactView = components["schemas"]["TaskArtifactView"];
export type TaskOutputView = components["schemas"]["TaskOutputView"];
export type TaskBundleProposalView = components["schemas"]["TaskBundleProposalView"];
export type TaskBundleOptionView = components["schemas"]["TaskBundleOptionView"];
export type TaskBundleItemView = components["schemas"]["TaskBundleItemView"];
export type VerificationReport = components["schemas"]["VerificationReport"];
export type VerificationIssue = components["schemas"]["VerificationIssue"];
export type ShoppingTaskCreateResult = components["schemas"]["TaskCreateResult"];
export type ShoppingTaskCommandResult = components["schemas"]["TaskCommandResult"];
export type ShoppingTaskActionPreviewResult = components["schemas"]["TaskActionPreviewResult"];
export type ShoppingTaskActionResolution = components["schemas"]["TaskActionResolution"];
