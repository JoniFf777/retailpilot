export interface paths {
    "/api/cart": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Cart */
        get: operations["read_cart_api_cart_get"];
        put?: never;
        post?: never;
        /** Remove All Cart Items */
        delete: operations["remove_all_cart_items_api_cart_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/cart/items/{cart_item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Remove Cart Item */
        delete: operations["remove_cart_item_api_cart_items__cart_item_id__delete"];
        options?: never;
        head?: never;
        /** Patch Cart Item */
        patch: operations["patch_cart_item_api_cart_items__cart_item_id__patch"];
        trace?: never;
    };
    "/api/chat": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Chat */
        post: operations["chat_api_chat_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/chat/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm Chat */
        post: operations["confirm_chat_api_chat_confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/chat/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Chat Stream */
        post: operations["chat_stream_api_chat_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/checkout/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Checkout Preview */
        post: operations["create_checkout_preview_api_checkout_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health Check */
        get: operations["health_check_api_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/health/governance-audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Governance Audit Health Check */
        get: operations["governance_audit_health_check_api_health_governance_audit_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/health/outbox": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Outbox Health Check */
        get: operations["outbox_health_check_api_health_outbox_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/health/postgres": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Postgres Health Check */
        get: operations["postgres_health_check_api_health_postgres_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/health/preflight": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Production Preflight Health Check */
        get: operations["production_preflight_health_check_api_health_preflight_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/health/readiness": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Deployment Readiness Health Check */
        get: operations["deployment_readiness_health_check_api_health_readiness_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/health/service-metrics": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Service Metrics Health Check */
        get: operations["service_metrics_health_check_api_health_service_metrics_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/orders": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Orders Endpoint */
        get: operations["list_orders_endpoint_api_orders_get"];
        put?: never;
        /** Create Order Endpoint */
        post: operations["create_order_endpoint_api_orders_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/orders/{order_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Order Endpoint */
        get: operations["get_order_endpoint_api_orders__order_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/orders/{order_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Order Endpoint */
        post: operations["cancel_order_endpoint_api_orders__order_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/orders/{order_id}/payments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Payments Endpoint */
        get: operations["list_payments_endpoint_api_orders__order_id__payments_get"];
        put?: never;
        /** Create Payment Endpoint */
        post: operations["create_payment_endpoint_api_orders__order_id__payments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/owner-data/delete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Delete Owner Data */
        post: operations["delete_owner_data_api_owner_data_delete_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/owner-data/inspect": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Inspect Owner Data */
        post: operations["inspect_owner_data_api_owner_data_inspect_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/owner-data/memory/correct": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Correct Owner Memory */
        post: operations["correct_owner_memory_api_owner_data_memory_correct_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/owner-data/memory/delete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Delete Owner Memory */
        post: operations["delete_owner_memory_api_owner_data_memory_delete_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/owner-data/runs/inspect": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Inspect Owner Run */
        post: operations["inspect_owner_run_api_owner_data_runs_inspect_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/pending-actions/{pending_action_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Pending Action */
        get: operations["read_pending_action_api_pending_actions__pending_action_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/pending-actions/{pending_action_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Pending Action Endpoint */
        post: operations["cancel_pending_action_endpoint_api_pending_actions__pending_action_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/pending-actions/{pending_action_id}/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm Pending Action Endpoint */
        post: operations["confirm_pending_action_endpoint_api_pending_actions__pending_action_id__confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/pending-actions/add-to-cart": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Pending Action */
        post: operations["create_pending_action_api_pending_actions_add_to_cart_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** ActionErrorResponse */
        ActionErrorResponse: {
            /**
             * Code
             * @enum {string}
             */
            code: "pending_action_not_found" | "recommendation_not_found" | "sku_not_in_recommendation" | "invalid_quantity" | "invalid_updated_fields" | "version_conflict" | "action_resolution_conflict" | "action_expired" | "catalog_not_found" | "catalog_identifier_ambiguous" | "sku_ambiguous" | "catalog_identity_changed" | "product_inactive" | "sku_inactive" | "insufficient_inventory" | "cart_quantity_limit" | "unsupported_action_schema" | "invalid_action_payload" | "expected_version_required";
            details?: components["schemas"]["PendingActionErrorDetails"];
            /**
             * Idempotent Replay
             * @default false
             */
            idempotent_replay: boolean;
            /** Message */
            message: string;
        };
        /** AddToCartPendingActionRequest */
        AddToCartPendingActionRequest: {
            /**
             * Quantity
             * @default 1
             */
            quantity: number;
            /**
             * Sku Id
             * Format: uuid
             */
            sku_id: string;
            /** Source Run Id */
            source_run_id: string;
            /** Thread Id */
            thread_id: string;
            /** User Id */
            user_id?: string | null;
        };
        /** AddToCartPreview */
        AddToCartPreview: {
            availability_snapshot?: components["schemas"]["AvailabilityView"] | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "catalog_sku" | "legacy_product";
            /** Legacy Product Id */
            legacy_product_id?: string | null;
            /** Preview Text */
            preview_text?: string | null;
            /** Product Code */
            product_code?: string | null;
            /** Product Id */
            product_id?: string | null;
            /** Product Name */
            product_name: string;
            /** Requested Quantity */
            requested_quantity: number;
            /** Sku Code */
            sku_code?: string | null;
            /** Sku Id */
            sku_id?: string | null;
            /** Sku Name */
            sku_name?: string | null;
            subtotal_money_snapshot?: components["schemas"]["Money"] | null;
            unit_money_snapshot?: components["schemas"]["Money"] | null;
        };
        /** AlternativeSkuView */
        AlternativeSkuView: {
            availability: components["schemas"]["AvailabilityView"];
            /** Differing Specifications */
            differing_specifications?: components["schemas"]["ProductSpecificationView"][];
            money: components["schemas"]["Money"];
            /** Sku Code */
            sku_code: string;
            /**
             * Sku Id
             * Format: uuid
             */
            sku_id: string;
            /** Sku Name */
            sku_name: string;
        };
        /** AvailabilityView */
        AvailabilityView: {
            /** Available Quantity */
            available_quantity: number;
            /** In Stock */
            in_stock: boolean;
            /** Reason Code */
            reason_code?: string | null;
            /**
             * Sale Status
             * @enum {string}
             */
            sale_status: "draft" | "active" | "inactive";
        };
        /** CancelOrderResponse */
        CancelOrderResponse: {
            /** Idempotent Replay */
            idempotent_replay: boolean;
            order: components["schemas"]["OrderView"];
        };
        /** CartErrorDetails */
        CartErrorDetails: {
            /** Available Quantity */
            available_quantity?: number | null;
            /** Current Quantity */
            current_quantity?: number | null;
            /** Current Version */
            current_version?: number | null;
            /** Max Quantity */
            max_quantity?: number | null;
            /** Requested Quantity */
            requested_quantity?: number | null;
        };
        /** CartErrorResponse */
        CartErrorResponse: {
            /**
             * Code
             * @enum {string}
             */
            code: "cart_item_not_found" | "cart_version_conflict" | "invalid_quantity" | "cart_quantity_limit" | "insufficient_inventory" | "product_inactive" | "sku_inactive" | "catalog_not_found" | "inventory_missing";
            details?: components["schemas"]["CartErrorDetails"];
            /** Message */
            message: string;
        };
        /** CartItemView */
        CartItemView: {
            availability: components["schemas"]["AvailabilityView"];
            /**
             * Cart Item Id
             * Format: uuid
             */
            cart_item_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Effective Sale Status
             * @enum {string}
             */
            effective_sale_status: "draft" | "active" | "inactive";
            /** Product Code */
            product_code: string;
            /**
             * Product Id
             * Format: uuid
             */
            product_id: string;
            /** Product Name */
            product_name: string;
            /**
             * Product Sale Status
             * @enum {string}
             */
            product_sale_status: "draft" | "active" | "inactive";
            /** Quantity */
            quantity: number;
            /** Sku Code */
            sku_code: string;
            /**
             * Sku Id
             * Format: uuid
             */
            sku_id: string;
            /** Sku Name */
            sku_name: string;
            /**
             * Sku Sale Status
             * @enum {string}
             */
            sku_sale_status: "draft" | "active" | "inactive";
            subtotal_money: components["schemas"]["Money"];
            unit_money: components["schemas"]["Money"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Version */
            version: number;
        };
        /** CartMutationResponse */
        CartMutationResponse: {
            cart: components["schemas"]["CartResponse"];
            item: components["schemas"]["CartItemView"];
        };
        /** CartResponse */
        CartResponse: {
            /** Currency */
            currency?: string | null;
            /**
             * Item Count
             * @default 0
             */
            item_count: number;
            /** Items */
            items?: components["schemas"]["CartItemView"][];
            subtotal?: components["schemas"]["Money"] | null;
            /**
             * Total Quantity
             * @default 0
             */
            total_quantity: number;
            /** Warnings */
            warnings?: components["schemas"]["CartWarning"][];
        };
        /** CartWarning */
        CartWarning: {
            /** Cart Item Id */
            cart_item_id?: string | null;
            /**
             * Code
             * @enum {string}
             */
            code: "mixed_currency" | "product_inactive" | "sku_inactive" | "out_of_stock" | "insufficient_inventory" | "inventory_missing";
            /** Message */
            message: string;
            /** Sku Id */
            sku_id?: string | null;
        };
        /** ChatRequest */
        ChatRequest: {
            /**
             * Include Debug
             * @description Return optional debug metadata for evaluation and troubleshooting.
             * @default false
             */
            include_debug: boolean;
            /**
             * Message
             * @description User message sent to the chat API. V3 write handoff supports explicit product IDs such as TECH-KEY-010 and same-thread candidate selection such as 1.
             */
            message: string;
            /**
             * Thread Id
             * @description Optional conversation/thread identifier. Recommended for same-thread candidate selection context.
             */
            thread_id?: string | null;
            /**
             * User Id
             * @description Optional user identifier. Required when a write handoff creates or confirms a pending action.
             */
            user_id?: string | null;
        };
        /** ChatResponse */
        ChatResponse: {
            /**
             * Answer
             * @description Assistant answer returned by the backend.
             */
            answer: string;
            /**
             * Authoritative Run Id
             * @description Winner Run identity for an in-progress idempotency recovery response.
             */
            authoritative_run_id?: string | null;
            /**
             * Debug
             * @description Optional structured debug metadata when requested. V3 handoff debug may include multi_agent_handoff, write_handoff_debug, candidate_context events, and confirmation events.
             */
            debug?: {
                [key: string]: unknown;
            } | null;
            /**
             * Pending Action Id
             * @description Pending action identifier when user confirmation is required.
             */
            pending_action_id?: string | null;
            /** @description Stable public projection error for a corrupt persisted recommendation; run state is unchanged. */
            projection_error?: components["schemas"]["ProjectionError"] | null;
            /** @description Structured catalog recommendation when the Recommendation Gate handled the request. */
            recommendation?: components["schemas"]["RecommendationResult"] | null;
            /** @description Stable source run identifier for creating a recommendation-backed action. */
            recommendation_context?: components["schemas"]["RecommendationContextView"] | null;
            /**
             * Retry State
             * @description Machine-readable transport/retry state. In-progress is recoverable and is not terminal failure.
             * @default none
             * @enum {string}
             */
            retry_state: "none" | "in_progress" | "terminal";
            /**
             * Run Id
             * @description Opaque persisted run identifier returned only when include_debug=true.
             */
            run_id?: string | null;
            /**
             * Runtime Error Code
             * @description Machine-readable runtime error code when a retry/recovery state is present.
             */
            runtime_error_code?: string | null;
            /**
             * Status
             * @description Chat processing status. Stable public values are completed, confirmation_required, cancelled, and failed.
             * @default completed
             * @enum {string}
             */
            status: "completed" | "confirmation_required" | "cancelled" | "failed";
            /**
             * Thread Id
             * @description Conversation/thread identifier echoed back to the caller when provided.
             */
            thread_id?: string | null;
            /**
             * Tool Calls
             * @description Names of tools called by the ShopMind Agent, for example prepare_add_to_cart, confirm_add_to_cart, or cancel_pending_action.
             */
            tool_calls?: string[];
            /**
             * Trace Id
             * @description Opaque trace identifier returned only when include_debug=true.
             */
            trace_id?: string | null;
            /**
             * User Id
             * @description User identifier echoed back to the caller when provided.
             */
            user_id?: string | null;
        };
        /** CheckoutErrorDetails */
        CheckoutErrorDetails: {
            /** Available Quantity */
            available_quantity?: number | null;
            /** Requested Quantity */
            requested_quantity?: number | null;
        };
        /** CheckoutErrorResponse */
        CheckoutErrorResponse: {
            /**
             * Code
             * @constant
             */
            code: "checkout_unavailable";
            details?: components["schemas"]["CheckoutErrorDetails"];
            /** Message */
            message: string;
        };
        /** CheckoutPreview */
        CheckoutPreview: {
            /** Can Create Order */
            can_create_order: boolean;
            /** Checkout Token */
            checkout_token?: string | null;
            /** Currency */
            currency?: string | null;
            /** Expires At */
            expires_at?: string | null;
            /**
             * Item Count
             * @default 0
             */
            item_count: number;
            /** Items */
            items?: components["schemas"]["CheckoutPreviewItem"][];
            /**
             * Revalidation Required
             * @default true
             */
            revalidation_required: boolean;
            subtotal?: components["schemas"]["Money"] | null;
            /**
             * Total Quantity
             * @default 0
             */
            total_quantity: number;
            /** Warnings */
            warnings?: components["schemas"]["CheckoutWarning"][];
        };
        /** CheckoutPreviewItem */
        CheckoutPreviewItem: {
            availability: components["schemas"]["AvailabilityView"];
            /**
             * Cart Item Id
             * Format: uuid
             */
            cart_item_id: string;
            /** Product Name */
            product_name: string;
            /** Quantity */
            quantity: number;
            /**
             * Sku Id
             * Format: uuid
             */
            sku_id: string;
            /** Sku Name */
            sku_name: string;
            subtotal_money: components["schemas"]["Money"];
            unit_money: components["schemas"]["Money"];
            /** Version */
            version: number;
        };
        /** CheckoutPreviewRequest */
        CheckoutPreviewRequest: Record<string, never>;
        /** CheckoutWarning */
        CheckoutWarning: {
            /** Cart Item Id */
            cart_item_id?: string | null;
            /**
             * Code
             * @enum {string}
             */
            code: "cart_empty" | "mixed_currency" | "product_inactive" | "sku_inactive" | "inventory_missing" | "out_of_stock" | "insufficient_inventory";
            /** Message */
            message: string;
            /** Sku Id */
            sku_id?: string | null;
        };
        /** ConfirmChatRequest */
        ConfirmChatRequest: {
            /**
             * Confirmed
             * @description Whether the user confirmed the pending action.
             */
            confirmed: boolean;
            /**
             * Expected Version
             * @description Client-held PendingAction version. Required when confirming or cancelling a canonical SKU add-to-cart action.
             */
            expected_version?: number | null;
            /**
             * Include Debug
             * @description Return optional debug metadata for evaluation and troubleshooting.
             * @default false
             */
            include_debug: boolean;
            /**
             * Pending Action Id
             * @description Pending action identifier to confirm or cancel.
             */
            pending_action_id: string;
            /**
             * Thread Id
             * @description Optional conversation/thread identifier echoed back to the caller.
             */
            thread_id?: string | null;
            /**
             * Updated Arguments
             * @description Optional server-validated edits applied atomically before confirmation. Editable fields depend on the persisted action type.
             */
            updated_arguments?: {
                [key: string]: unknown;
            } | null;
            /**
             * User Id
             * @description User identifier for the pending action.
             */
            user_id: string;
        };
        /** CreateOrderRequest */
        CreateOrderRequest: {
            /** Checkout Token */
            checkout_token: string;
        };
        /** CreateOrderResponse */
        CreateOrderResponse: {
            /** Idempotent Replay */
            idempotent_replay: boolean;
            order: components["schemas"]["OrderView"];
        };
        /** EnumEditableField */
        EnumEditableField: {
            /** Current Value */
            current_value: string;
            /**
             * Field
             * @constant
             */
            field: "preference_type";
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            field_type: "enum";
            /** Label */
            label: string;
            /** Options */
            options: string[];
            /**
             * Required
             * @default true
             */
            required: boolean;
        };
        /**
         * EventVisibility
         * @enum {string}
         */
        EventVisibility: "client" | "internal" | "audit";
        /** EvidenceView */
        EvidenceView: {
            /** Field */
            field: string;
            /** Ref */
            ref?: string | null;
            /** Source */
            source: string;
            /** Type */
            type: string;
            /** Value */
            value: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** IntegerEditableField */
        IntegerEditableField: {
            /** Current Value */
            current_value: number;
            /**
             * Field
             * @constant
             */
            field: "quantity";
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            field_type: "integer";
            /** Label */
            label: string;
            /**
             * Max Value
             * @default 20
             */
            max_value: number;
            /**
             * Min Value
             * @default 1
             */
            min_value: number;
            /**
             * Required
             * @default true
             */
            required: boolean;
        };
        /** LaptopConstraints */
        LaptopConstraints: {
            /** Budget Currency */
            budget_currency?: string | null;
            /** Budget Max */
            budget_max?: string | null;
            /** Cpu Tier Min */
            cpu_tier_min?: string | null;
            /** Gpu Tier Min */
            gpu_tier_min?: string | null;
            /** Memory Min Gb */
            memory_min_gb?: number | null;
            /** Primary Use Cases */
            primary_use_cases?: string[];
            /** Screen Inches */
            screen_inches?: string | null;
            /** Secondary Use Cases */
            secondary_use_cases?: string[];
            /** Storage Min Gb */
            storage_min_gb?: number | null;
            /** Weight Max Kg */
            weight_max_kg?: string | null;
        };
        /**
         * MemoryKind
         * @enum {string}
         */
        MemoryKind: "working" | "episodic" | "long_term" | "operational";
        /**
         * MemoryScope
         * @enum {string}
         */
        MemoryScope: "thread" | "user" | "operational";
        /** Money */
        Money: {
            /** Amount */
            amount: string;
            /** Currency */
            currency: string;
        };
        /** OrderErrorDetails */
        OrderErrorDetails: {
            /** Available Quantity */
            available_quantity?: number | null;
            /** Reason */
            reason?: string | null;
            /** Requested Quantity */
            requested_quantity?: number | null;
            /** Reservation Count */
            reservation_count?: number | null;
        };
        /** OrderErrorResponse */
        OrderErrorResponse: {
            /**
             * Code
             * @enum {string}
             */
            code: "checkout_invalid" | "checkout_expired" | "checkout_unavailable" | "cart_changed" | "mixed_currency" | "product_inactive" | "sku_inactive" | "inventory_missing" | "insufficient_inventory" | "price_changed" | "idempotency_conflict" | "order_not_found" | "reservation_inconsistent" | "order_not_cancellable" | "payment_in_progress" | "payment_state_inconsistent" | "order_expired" | "idempotency_key_invalid" | "cursor_invalid";
            details?: components["schemas"]["OrderErrorDetails"];
            /**
             * Idempotent Replay
             * @default false
             */
            idempotent_replay: boolean;
            /** Message */
            message: string;
        };
        /** OrderItemView */
        OrderItemView: {
            /**
             * Item Id
             * Format: uuid
             */
            item_id: string;
            /** Product Code */
            product_code: string;
            /** Product Name */
            product_name: string;
            /** Quantity */
            quantity: number;
            /** Sku Code */
            sku_code: string;
            /**
             * Sku Id
             * Format: uuid
             */
            sku_id: string;
            /** Sku Name */
            sku_name: string;
            subtotal_money: components["schemas"]["Money"];
            unit_money: components["schemas"]["Money"];
        };
        /** OrderListResponse */
        OrderListResponse: {
            /** Items */
            items: components["schemas"]["OrderView"][];
            /** Next Cursor */
            next_cursor?: string | null;
        };
        /** OrderView */
        OrderView: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Currency */
            currency: string;
            /** Expires At */
            expires_at?: string | null;
            /** Items */
            items: components["schemas"]["OrderItemView"][];
            /**
             * Order Id
             * Format: uuid
             */
            order_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending_payment" | "cancelled" | "paid" | "expired";
            subtotal: components["schemas"]["Money"];
            total: components["schemas"]["Money"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Version */
            version: number;
        };
        /** OwnerDataCounts */
        OwnerDataCounts: {
            /** Agent Run Events */
            agent_run_events: number;
            /** Agent Runs */
            agent_runs: number;
            /** Candidate Contexts */
            candidate_contexts: number;
            /** Cart Items */
            cart_items: number;
            /** Conversation Messages */
            conversation_messages: number;
            /** Conversation Summaries */
            conversation_summaries: number;
            /** Conversation Threads */
            conversation_threads: number;
            /** Idempotency Records */
            idempotency_records: number;
            /** Memory Records */
            memory_records: number;
            /** Pending Actions */
            pending_actions: number;
            /** Preferences */
            preferences: number;
        };
        /** OwnerDataDeletion */
        OwnerDataDeletion: {
            counts: components["schemas"]["OwnerDataCounts"];
            /**
             * Deletion Request Id
             * Format: uuid
             */
            deletion_request_id: string;
            /** Records Affected */
            records_affected: number;
            /**
             * Status
             * @enum {string}
             */
            status: "deleted" | "already_deleted";
        };
        /** OwnerDataDeletionRequest */
        OwnerDataDeletionRequest: {
            /**
             * Confirmed
             * @constant
             */
            confirmed: true;
            /**
             * Deletion Request Id
             * Format: uuid
             */
            deletion_request_id: string;
            /** User Id */
            user_id: string;
        };
        /** OwnerDataInspectRequest */
        OwnerDataInspectRequest: {
            /**
             * Memory Limit
             * @default 50
             */
            memory_limit: number;
            /** User Id */
            user_id: string;
        };
        /** OwnerDataSnapshot */
        OwnerDataSnapshot: {
            counts: components["schemas"]["OwnerDataCounts"];
            /** Memories */
            memories: components["schemas"]["OwnerMemoryRecord"][];
            /** Memory Limit */
            memory_limit: number;
            /** Memory Truncated */
            memory_truncated: boolean;
            /** Total Records */
            total_records: number;
        };
        /** OwnerMemoryCorrection */
        OwnerMemoryCorrection: {
            memory: components["schemas"]["OwnerMemoryRecord"];
            /**
             * Status
             * @default corrected
             * @constant
             */
            status: "corrected";
        };
        /** OwnerMemoryCorrectionRequest */
        OwnerMemoryCorrectionRequest: {
            /** Content */
            content: string;
            /** Memory Id */
            memory_id: string;
            /** User Id */
            user_id: string;
        };
        /** OwnerMemoryDeletion */
        OwnerMemoryDeletion: {
            /** Memory Id */
            memory_id: string;
            /**
             * Status
             * @default deleted
             * @constant
             */
            status: "deleted";
        };
        /** OwnerMemoryDeletionRequest */
        OwnerMemoryDeletionRequest: {
            /** Memory Id */
            memory_id: string;
            /** User Id */
            user_id: string;
        };
        /** OwnerMemoryRecord */
        OwnerMemoryRecord: {
            /** Confidence */
            confidence?: number | null;
            /** Content */
            content: string;
            /** Content Json */
            content_json?: {
                [key: string]: unknown;
            };
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Deleted At */
            deleted_at?: string | null;
            /** Expires At */
            expires_at?: string | null;
            kind: components["schemas"]["MemoryKind"];
            /** Memory Id */
            memory_id: string;
            /** Priority */
            priority: number;
            scope: components["schemas"]["MemoryScope"];
            /**
             * Status
             * @enum {string}
             */
            status: "active" | "superseded" | "deleted";
            /** Thread Id */
            thread_id?: string | null;
            /** Token Count */
            token_count: number;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * OwnerRunEventSummary
         * @description Client-visible event metadata with no arbitrary event payload.
         */
        OwnerRunEventSummary: {
            /** Agent Name */
            agent_name?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Event Type */
            event_type: string;
            /** Sequence */
            sequence: number;
            visibility: components["schemas"]["EventVisibility"];
        };
        /**
         * OwnerRunInspection
         * @description Exact-owner run projection safe for the reference client.
         */
        OwnerRunInspection: {
            /** Client Event Count */
            client_event_count: number;
            /** Completed At */
            completed_at?: string | null;
            /** Event Limit */
            event_limit: number;
            /** Events */
            events: components["schemas"]["OwnerRunEventSummary"][];
            /** Events Truncated */
            events_truncated: boolean;
            mode: components["schemas"]["RunMode"];
            operation: components["schemas"]["RunOperation"];
            /** Pending Action Id */
            pending_action_id?: string | null;
            /** Run Id */
            run_id: string;
            /**
             * Schema Version
             * @default shopmind.owner-run-inspection.v1
             * @constant
             */
            schema_version: "shopmind.owner-run-inspection.v1";
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            status: components["schemas"]["RunStatus"];
            /** Thread Id */
            thread_id: string;
            /** Trace Id */
            trace_id: string;
            usage: components["schemas"]["RunUsage"];
        };
        /** OwnerRunInspectRequest */
        OwnerRunInspectRequest: {
            /**
             * Event Limit
             * @default 50
             */
            event_limit: number;
            /** Run Id */
            run_id?: string | null;
            /** Trace Id */
            trace_id?: string | null;
            /** User Id */
            user_id: string;
        };
        /** PaymentAttemptListResponse */
        PaymentAttemptListResponse: {
            /** Items */
            items: components["schemas"]["PaymentAttemptView"][];
        };
        /** PaymentAttemptRequest */
        PaymentAttemptRequest: {
            /** Payment Method Ref */
            payment_method_ref: string;
            /**
             * Provider
             * @default mock
             * @constant
             */
            provider: "mock";
        };
        /** PaymentAttemptResponse */
        PaymentAttemptResponse: {
            /**
             * Idempotent Replay
             * @default false
             */
            idempotent_replay: boolean;
            order: components["schemas"]["OrderView"];
            payment_attempt: components["schemas"]["PaymentAttemptView"];
        };
        /** PaymentAttemptView */
        PaymentAttemptView: {
            amount: components["schemas"]["Money"];
            /**
             * Attempt Id
             * Format: uuid
             */
            attempt_id: string;
            /** Completed At */
            completed_at?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Failure Code */
            failure_code?: string | null;
            /**
             * Order Id
             * Format: uuid
             */
            order_id: string;
            /**
             * Provider
             * @constant
             */
            provider: "mock";
            /** Provider Result At */
            provider_result_at?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "processing" | "unknown" | "provider_succeeded" | "failed" | "succeeded";
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** PaymentErrorDetails */
        PaymentErrorDetails: {
            /** Reason */
            reason?: string | null;
        };
        /** PaymentErrorResponse */
        PaymentErrorResponse: {
            /**
             * Code
             * @enum {string}
             */
            code: "idempotency_key_invalid" | "idempotency_conflict" | "order_not_found" | "order_not_payable" | "order_already_paid" | "payment_in_progress" | "payment_declined" | "payment_provider_unavailable" | "payment_finalization_pending" | "order_expired" | "payment_state_inconsistent";
            details?: components["schemas"]["PaymentErrorDetails"];
            /**
             * Idempotent Replay
             * @default false
             */
            idempotent_replay: boolean;
            /** Message */
            message: string;
        };
        /** PendingActionCancelRequest */
        PendingActionCancelRequest: {
            /** Expected Version */
            expected_version: number;
            /** Thread Id */
            thread_id: string;
            /** User Id */
            user_id?: string | null;
        };
        /** PendingActionErrorDetails */
        PendingActionErrorDetails: {
            /** Action Status */
            action_status?: ("pending" | "confirmed" | "cancelled" | "expired" | "failed") | null;
            /** Available Quantity */
            available_quantity?: number | null;
            /** Current Quantity */
            current_quantity?: number | null;
            /** Current Version */
            current_version?: number | null;
            /** Matched Namespace Count */
            matched_namespace_count?: number | null;
            /** Max Quantity */
            max_quantity?: number | null;
            /** Target Count */
            target_count?: number | null;
        };
        /** PendingActionTransitionRequest */
        PendingActionTransitionRequest: {
            /** Expected Version */
            expected_version: number;
            /** Thread Id */
            thread_id: string;
            updated_fields?: components["schemas"]["QuantityEditFields"] | null;
            /** User Id */
            user_id?: string | null;
        };
        /** PendingActionTransitionResponse */
        PendingActionTransitionResponse: {
            cart_item?: components["schemas"]["CartItemView"] | null;
            /** Cart Quantity */
            cart_quantity?: number | null;
            current_money?: components["schemas"]["Money"] | null;
            /**
             * Idempotent Replay
             * @default false
             */
            idempotent_replay: boolean;
            pending_action: components["schemas"]["PendingActionView"];
            /**
             * Price Changed
             * @default false
             */
            price_changed: boolean;
            /** Requested Quantity */
            requested_quantity?: number | null;
            snapshot_money?: components["schemas"]["Money"] | null;
        };
        /** PendingActionView */
        PendingActionView: {
            /**
             * Action Type
             * @enum {string}
             */
            action_type: "add_to_cart" | "save_preference";
            /**
             * Cancel Label
             * @default Cancel
             */
            cancel_label: string;
            /**
             * Confirm Label
             * @default Confirm
             */
            confirm_label: string;
            /** Editable Fields */
            editable_fields?: (components["schemas"]["IntegerEditableField"] | components["schemas"]["EnumEditableField"] | components["schemas"]["TextEditableField"])[];
            /** Expires At */
            expires_at: string | null;
            /** Pending Action Id */
            pending_action_id: string;
            /** Preview */
            preview?: components["schemas"]["AddToCartPreview"] | string | null;
            /**
             * Risk Class
             * @enum {string}
             */
            risk_class: "low" | "medium" | "high";
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "confirmed" | "cancelled" | "expired" | "failed";
            /** Version */
            version: number;
        };
        /** ProductSpecificationView */
        ProductSpecificationView: {
            /** Code */
            code: string;
            /**
             * Comparable
             * @default false
             */
            comparable: boolean;
            /**
             * Display Order
             * @default 0
             */
            display_order: number;
            /** Name */
            name: string;
            /** Unit */
            unit?: string | null;
            /** Value */
            value: string | number | boolean | string[];
            /**
             * Value Type
             * @enum {string}
             */
            value_type: "string" | "integer" | "decimal" | "boolean" | "string_list";
        };
        /**
         * ProjectionError
         * @description Safe public projection failure for a completed persisted run.
         */
        ProjectionError: {
            /**
             * Code
             * @constant
             */
            code: "recommendation_projection_corrupt";
            /** Message */
            message: string;
        };
        /** QuantityEditFields */
        QuantityEditFields: {
            /** Quantity */
            quantity?: number | null;
        };
        /** Recommendation */
        Recommendation: {
            /** Alternative Skus */
            alternative_skus?: components["schemas"]["AlternativeSkuView"][];
            availability: components["schemas"]["AvailabilityView"];
            /** Category */
            category?: ("laptop" | "monitor" | "unknown") | null;
            /** Evidence */
            evidence?: components["schemas"]["EvidenceView"][];
            /** Matched Hard Constraints */
            matched_hard_constraints?: string[];
            /** Matched Soft Preferences */
            matched_soft_preferences?: string[];
            money: components["schemas"]["Money"];
            /**
             * Product Id
             * Format: uuid
             */
            product_id: string;
            /** Product Name */
            product_name: string;
            /** Reason */
            reason: string;
            /** Score */
            score: number;
            /** Score Breakdown */
            score_breakdown: components["schemas"]["ScoreBreakdownItem"][];
            /**
             * Sku Id
             * Format: uuid
             */
            sku_id: string;
            /** Sku Name */
            sku_name: string;
            /** Soft Tradeoffs */
            soft_tradeoffs?: string[];
            /** Specifications */
            specifications: components["schemas"]["ProductSpecificationView"][];
            /** Unmatched Soft Constraints */
            unmatched_soft_constraints?: string[];
        };
        /** RecommendationContextView */
        RecommendationContextView: {
            /** Source Run Id */
            source_run_id: string;
        };
        /**
         * RecommendationRequest
         * @description Shared request envelope with bounded category-owned attributes.
         */
        RecommendationRequest: {
            /**
             * Availability Required
             * @default true
             */
            availability_required: boolean;
            /** Budget Currency */
            budget_currency?: string | null;
            /** Budget Max */
            budget_max?: string | null;
            /**
             * Category
             * @enum {string}
             */
            category: "laptop" | "monitor" | "unknown";
            /** Category Attributes */
            category_attributes?: {
                [key: string]: unknown;
            };
            /** Generic Preferences */
            generic_preferences?: string[];
        };
        /** RecommendationResult */
        RecommendationResult: {
            /** Category */
            category?: ("laptop" | "monitor" | "unknown") | null;
            /** Category Attributes */
            category_attributes?: {
                [key: string]: unknown;
            };
            /** Clarification Question */
            clarification_question?: string | null;
            /** Error Code */
            error_code?: string | null;
            /** Missing Fields */
            missing_fields?: string[];
            /** No Match Reason */
            no_match_reason?: string | null;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "recommended" | "no_match" | "clarification_required";
            /** Ranking Policy Version */
            ranking_policy_version: string;
            recommendation_request?: components["schemas"]["RecommendationRequest"] | null;
            /** Recommendations */
            recommendations?: components["schemas"]["Recommendation"][];
            /** Request Summary */
            request_summary: string;
            /**
             * Schema Version
             * @default shopmind.recommendation.v1
             * @constant
             */
            schema_version: "shopmind.recommendation.v1";
            structured_constraints: components["schemas"]["LaptopConstraints"];
        };
        /**
         * RunMode
         * @enum {string}
         */
        RunMode: "single" | "multi";
        /**
         * RunOperation
         * @enum {string}
         */
        RunOperation: "chat" | "confirm_pending_action";
        /**
         * RunStatus
         * @enum {string}
         */
        RunStatus: "started" | "completed" | "confirmation_required" | "cancelled" | "failed";
        /** RunUsage */
        RunUsage: {
            /** Cost Usd */
            cost_usd?: number | null;
            /** Input Tokens */
            input_tokens?: number | null;
            /** Output Tokens */
            output_tokens?: number | null;
            /**
             * Step Count
             * @default 0
             */
            step_count: number;
            /**
             * Tool Call Count
             * @default 0
             */
            tool_call_count: number;
            /** Total Tokens */
            total_tokens?: number | null;
        };
        /** ScoreBreakdownItem */
        ScoreBreakdownItem: {
            /** Code */
            code: string;
            /** Max Points */
            max_points: number;
            /** Name */
            name: string;
            /** Points */
            points: number;
            /** Reason */
            reason: string;
        };
        /** TextEditableField */
        TextEditableField: {
            /** Current Value */
            current_value: string;
            /**
             * Field
             * @constant
             */
            field: "preference_value";
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            field_type: "text";
            /** Label */
            label: string;
            /**
             * Max Length
             * @default 2000
             */
            max_length: number;
            /**
             * Min Length
             * @default 1
             */
            min_length: number;
            /**
             * Required
             * @default true
             */
            required: boolean;
        };
        /** UpdateCartItemRequest */
        UpdateCartItemRequest: {
            /** Expected Version */
            expected_version: number;
            /** Quantity */
            quantity: number;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    read_cart_api_cart_get: {
        parameters: {
            query?: {
                user_id?: string | null;
            };
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CartResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    remove_all_cart_items_api_cart_delete: {
        parameters: {
            query?: never;
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    remove_cart_item_api_cart_items__cart_item_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path: {
                cart_item_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_cart_item_api_cart_items__cart_item_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path: {
                cart_item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateCartItemRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CartMutationResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CartErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CartErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    chat_api_chat_post: {
        parameters: {
            query?: never;
            header?: {
                "Idempotency-Key"?: string | null;
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChatRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChatResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    confirm_chat_api_chat_confirm_post: {
        parameters: {
            query?: never;
            header?: {
                "Idempotency-Key"?: string | null;
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConfirmChatRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChatResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    chat_stream_api_chat_stream_post: {
        parameters: {
            query?: never;
            header?: {
                "Idempotency-Key"?: string | null;
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChatRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_checkout_preview_api_checkout_preview_post: {
        parameters: {
            query?: {
                user_id?: string | null;
            };
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CheckoutPreviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CheckoutPreview"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CheckoutErrorResponse"];
                };
            };
        };
    };
    health_check_api_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    governance_audit_health_check_api_health_governance_audit_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    outbox_health_check_api_health_outbox_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    postgres_health_check_api_health_postgres_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    production_preflight_health_check_api_health_preflight_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    deployment_readiness_health_check_api_health_readiness_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    service_metrics_health_check_api_health_service_metrics_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    list_orders_endpoint_api_orders_get: {
        parameters: {
            query?: {
                cursor?: string | null;
                limit?: number;
                user_id?: string | null;
            };
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderListResponse"];
                };
            };
            /** @description Request validation or typed request-domain error. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"] | components["schemas"]["OrderErrorResponse"];
                };
            };
        };
    };
    create_order_endpoint_api_orders_post: {
        parameters: {
            query?: {
                user_id?: string | null;
            };
            header: {
                "Idempotency-Key": string;
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateOrderRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreateOrderResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderErrorResponse"];
                };
            };
            /** @description Gone */
            410: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderErrorResponse"];
                };
            };
            /** @description Request validation or typed request-domain error. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"] | components["schemas"]["OrderErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderErrorResponse"];
                };
            };
        };
    };
    get_order_endpoint_api_orders__order_id__get: {
        parameters: {
            query?: {
                user_id?: string | null;
            };
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path: {
                order_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderView"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_order_endpoint_api_orders__order_id__cancel_post: {
        parameters: {
            query?: {
                user_id?: string | null;
            };
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path: {
                order_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CancelOrderResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderErrorResponse"];
                };
            };
            /** @description Gone */
            410: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderErrorResponse"];
                };
            };
        };
    };
    list_payments_endpoint_api_orders__order_id__payments_get: {
        parameters: {
            query?: {
                user_id?: string | null;
            };
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path: {
                order_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaymentAttemptListResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaymentErrorResponse"];
                };
            };
            /** @description Request validation. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_payment_endpoint_api_orders__order_id__payments_post: {
        parameters: {
            query?: {
                user_id?: string | null;
            };
            header: {
                "Idempotency-Key": string;
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path: {
                order_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PaymentAttemptRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaymentAttemptResponse"];
                };
            };
            /** @description Accepted */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaymentAttemptResponse"];
                };
            };
            /** @description Payment Required */
            402: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaymentErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaymentErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaymentErrorResponse"];
                };
            };
            /** @description Request validation or typed payment-domain error. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"] | components["schemas"]["PaymentErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaymentErrorResponse"];
                };
            };
        };
    };
    delete_owner_data_api_owner_data_delete_post: {
        parameters: {
            query?: never;
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OwnerDataDeletionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OwnerDataDeletion"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    inspect_owner_data_api_owner_data_inspect_post: {
        parameters: {
            query?: never;
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OwnerDataInspectRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OwnerDataSnapshot"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    correct_owner_memory_api_owner_data_memory_correct_post: {
        parameters: {
            query?: never;
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OwnerMemoryCorrectionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OwnerMemoryCorrection"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_owner_memory_api_owner_data_memory_delete_post: {
        parameters: {
            query?: never;
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OwnerMemoryDeletionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OwnerMemoryDeletion"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    inspect_owner_run_api_owner_data_runs_inspect_post: {
        parameters: {
            query?: never;
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OwnerRunInspectRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OwnerRunInspection"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_pending_action_api_pending_actions__pending_action_id__get: {
        parameters: {
            query: {
                thread_id: string;
                user_id?: string | null;
            };
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path: {
                pending_action_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PendingActionView"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionErrorResponse"];
                };
            };
            /** @description Gone */
            410: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_pending_action_endpoint_api_pending_actions__pending_action_id__cancel_post: {
        parameters: {
            query?: never;
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path: {
                pending_action_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PendingActionCancelRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PendingActionTransitionResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionErrorResponse"];
                };
            };
            /** @description Gone */
            410: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    confirm_pending_action_endpoint_api_pending_actions__pending_action_id__confirm_post: {
        parameters: {
            query?: never;
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path: {
                pending_action_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PendingActionTransitionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PendingActionTransitionResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionErrorResponse"];
                };
            };
            /** @description Gone */
            410: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_pending_action_api_pending_actions_add_to_cart_post: {
        parameters: {
            query?: never;
            header?: {
                "X-ShopMind-Authenticated-User"?: string | null;
                "X-ShopMind-Identity-Nonce"?: string | null;
                "X-ShopMind-Identity-Signature"?: string | null;
                "X-ShopMind-Identity-Timestamp"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AddToCartPendingActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PendingActionView"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionErrorResponse"];
                };
            };
            /** @description Gone */
            410: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
