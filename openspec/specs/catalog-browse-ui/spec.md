# catalog-browse-ui Specification

## Purpose

This capability makes the server-owned Catalog discoverable through a small, safe, schema-driven browse experience while preserving canonical SKU commerce and existing recommendation contracts.

## Requirements

### Requirement: Catalog categories SHALL be discoverable from the supported registry

The Catalog browse API and first-party UI SHALL expose every currently supported category from the server-owned category registry, including its canonical code, display name, product count, and available-product count when the Catalog is readable. The client SHALL NOT maintain a second supported-category list.

#### Scenario: User opens the Catalog
- **WHEN** the user opens the Catalog entry or `/catalog`
- **THEN** the UI SHALL request and render registry-backed categories in deterministic order, with a usable loading, empty, or safe error state

#### Scenario: A future category is registered
- **WHEN** a new supported category is added to the registry and has valid Catalog data
- **THEN** the category SHALL appear through the same response and shared UI without a category-specific React branch

### Requirement: Product lists SHALL expose canonical Catalog facts

The read-only Catalog product-list response SHALL be backed by active Catalog Product/SKU/Inventory records and SHALL expose deterministic product ordering, product identity, category metadata, one or more canonical SKU views, price/currency, availability, and generic schema-driven specifications. Price, stock, and specifications SHALL NOT be sourced from RAG or presentation text.

#### Scenario: User browses one category
- **WHEN** the user selects a supported category
- **THEN** the UI SHALL render the active products in stable order with product name, price, stock status, SKU/variant identity, and three-to-six declared specifications when available

#### Scenario: Out-of-stock SKU is present
- **WHEN** an active product has a SKU with no available inventory
- **THEN** the response SHALL retain the product/SKU with `in_stock=false` and the UI SHALL show it as unavailable and prevent its add-to-cart action

#### Scenario: Unsupported category is requested
- **WHEN** a caller requests a category code or alias not accepted by the registry
- **THEN** the API SHALL return a stable 404-style typed error without internal exception details or cross-category data

### Requirement: Product detail SHALL be generic and identity-safe

The read-only product-detail response SHALL identify the canonical Product, category, and canonical SKU variants, and SHALL expose price, availability, description/evidence fields only when already safe for public Catalog reads, and all declared structured specifications with labels, units, display order, and type metadata. A request for a missing or inactive product SHALL fail safely.

#### Scenario: User opens product detail
- **WHEN** the user opens a valid product route
- **THEN** the UI SHALL show product identity, category display name, price, availability, SKU identity, and generic structured specifications

#### Scenario: Product is missing or inactive
- **WHEN** a product code does not resolve to an active Catalog product
- **THEN** the API SHALL return a typed not-found response and the UI SHALL render a generic not-found/error state without exposing filesystem document paths

### Requirement: Specifications SHALL be rendered from registry metadata

The browse projection SHALL pair Catalog attribute values with the matching registry definition and SHALL preserve declared label, unit, display order, comparable/type metadata, and safe formatting hints. Shared client components SHALL iterate the returned specification collection; category names and attribute names SHALL NOT control rendering branches.

#### Scenario: Different categories use different schemas
- **WHEN** a user browses Phone, Keyboard, or Router products
- **THEN** the same list/detail specification renderer SHALL display each category's declared fields without category-specific components or conditions

#### Scenario: Unknown or malformed Catalog attribute is encountered
- **WHEN** a value is not declared or does not validate against the category definition
- **THEN** the server SHALL fail closed for that projection or omit only the invalid field according to the existing safe Catalog error policy, and SHALL never label it using guessed business semantics

### Requirement: Browse add-to-cart SHALL preserve the existing HITL boundary

The browse UI SHALL submit a canonical SKU to the existing PendingAction confirmation lifecycle or a narrow preparation adapter that delegates to the same canonical confirmation service. Browse actions SHALL carry owner/thread scope and action version, SHALL not directly mutate Cart, and SHALL invalidate/refetch the canonical Cart after confirmation.

#### Scenario: User requests a sellable SKU
- **WHEN** the user selects Add to cart for an in-stock canonical SKU
- **THEN** the system SHALL create a PendingAction and show the existing confirmation UI before any Cart mutation

#### Scenario: User confirms a browse action
- **WHEN** the owner confirms the live action with its current expected version
- **THEN** the canonical SKU Cart SHALL be updated through the existing transaction boundary and the browse UI SHALL show the refreshed Cart state

#### Scenario: User cancels or confirmation is stale
- **WHEN** the user cancels, loses ownership, uses a stale version, or the SKU becomes unavailable
- **THEN** the system SHALL return the existing typed non-success and SHALL leave the canonical Cart unchanged

### Requirement: Catalog read failures SHALL be safe and deterministic

Catalog endpoints SHALL be read-only, preserve deterministic ordering, and map unsupported category, missing product, unavailable dependency, and malformed server failures to bounded public errors. The API SHALL not expose tracebacks, database URLs, filesystem paths, or secrets.

#### Scenario: Catalog dependency fails
- **WHEN** a Catalog read raises an unexpected backend failure
- **THEN** the caller SHALL receive a stable safe error response and no internal exception detail

#### Scenario: Repeated identical read
- **WHEN** the same Catalog snapshot is queried with the same category and bounds
- **THEN** the response ordering and facts SHALL be identical unless the underlying Catalog has changed

### Requirement: Browse shall preserve existing shopping contracts

Adding the browse capability SHALL not change recommendation ranking/category resolution, RAG candidate authority, Cart/Checkout/Order semantics, Chat retry/idempotency, or existing PendingAction ownership and replay behavior. The browse capability SHALL remain compatible with registry additions using existing generic response contracts.

#### Scenario: Existing recommendation and Chat flow remains available
- **WHEN** a user returns to the decision workspace after browsing
- **THEN** existing recommendation, Chat, and recommendation-to-HITL behavior SHALL continue to use their current contracts

#### Scenario: Browse confirmation enters formal commerce
- **WHEN** a browse-created action is confirmed
- **THEN** the resulting canonical SKU SHALL be readable by the existing Cart and Checkout flows without any legacy Cart fallback or direct Agent write
