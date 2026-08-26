"""Pydantic contracts for structured Catalog reads."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from app.schemas.recommendation import AvailabilityView, Money


class CatalogAttributeDefinition(BaseModel):
    """Public metadata used to render catalog specifications consistently."""

    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    scope: str
    data_type: str
    unit: str | None = None
    comparable: bool = False
    display_order: int = 0


class CatalogSkuCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_id: UUID
    product_code: str
    legacy_product_id: str | None = None
    product_name: str
    brand: str
    sku_id: UUID
    sku_code: str
    sku_name: str
    money_amount: Decimal
    currency: str
    product_attributes: dict[str, object] = Field(default_factory=dict)
    variant_attributes: dict[str, object] = Field(default_factory=dict)
    attribute_definitions: list[CatalogAttributeDefinition] = Field(default_factory=list)
    available_quantity: int

    @property
    def attributes(self) -> dict[str, object]:
        return {**self.product_attributes, **self.variant_attributes}


IdentifierNamespace = Literal["sku_code", "legacy_product_id", "product_code"]


class CatalogIdentifierResolution(BaseModel):
    """Machine-readable result of collision-safe legacy identifier lookup."""

    model_config = ConfigDict(frozen=True)

    status: Literal["resolved", "not_found", "ambiguous"]
    code: Literal[
        "catalog_not_found",
        "catalog_identifier_ambiguous",
        "sku_ambiguous",
    ] | None = None
    product_id: UUID | None = None
    sku_id: UUID | None = None
    matched_namespaces: tuple[IdentifierNamespace, ...] = ()
    target_count: int = Field(default=0, ge=0)


CatalogBrowseValue = StrictStr | StrictInt | StrictBool | list[StrictStr]
CatalogBrowseValueType = Literal["number", "string", "enum", "boolean", "string_list"]


class CatalogSpecificationView(BaseModel):
    """Registry-labelled Catalog fact safe for generic browser rendering."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: StrictStr
    label: StrictStr
    value: CatalogBrowseValue
    value_type: CatalogBrowseValueType
    unit: StrictStr | None = None
    display_order: StrictInt = 0
    comparable: StrictBool = False
    format_hint: StrictStr | None = None


class CatalogCategoryView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: StrictStr
    display_name: StrictStr
    product_count: StrictInt = Field(ge=0)
    available_product_count: StrictInt = Field(ge=0)


class CatalogSkuView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sku_id: UUID
    sku_code: StrictStr
    sku_name: StrictStr
    money: Money
    availability: AvailabilityView
    variant_specifications: list[CatalogSpecificationView] = Field(default_factory=list)


class CatalogProductSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_id: UUID
    product_code: StrictStr
    brand: StrictStr
    name: StrictStr
    category: CatalogCategoryView
    specifications: list[CatalogSpecificationView] = Field(default_factory=list)
    skus: list[CatalogSkuView] = Field(min_length=1)


class CatalogProductDetail(CatalogProductSummary):
    description: StrictStr | None = None


class CatalogCategoryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[CatalogCategoryView] = Field(default_factory=list)


class CatalogProductListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: CatalogCategoryView
    items: list[CatalogProductSummary] = Field(default_factory=list)
    total: StrictInt = Field(ge=0)
    limit: StrictInt = Field(ge=1, le=100)
    offset: StrictInt = Field(ge=0)


class CatalogErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Literal[
        "unsupported_category",
        "catalog_not_found",
        "catalog_unavailable",
        "catalog_data_invalid",
    ]
    message: StrictStr
