"""Pydantic contracts for structured Catalog reads."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
