"""Safe, read-only Catalog browse projections."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.recommendation.categories import (
    CategoryDefinition,
    CategoryRegistry,
    default_category_registry,
)
from app.repositories.catalog import catalog_product_counts, list_catalog_product_rows
from app.schemas.catalog import (
    CatalogCategoryListResponse,
    CatalogCategoryView,
    CatalogErrorResponse,
    CatalogProductDetail,
    CatalogProductListResponse,
    CatalogProductSummary,
    CatalogSkuView,
    CatalogSpecificationView,
)
from app.schemas.recommendation import AvailabilityView, Money


router = APIRouter()


class CatalogReadError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _error_response(error: CatalogReadError) -> JSONResponse:
    body = CatalogErrorResponse(code=error.code, message=error.message)
    return JSONResponse(
        status_code=error.status_code, content=body.model_dump(mode="json")
    )


def _resolve_category(registry: CategoryRegistry, value: str) -> str:
    code = registry.resolve_code_or_alias(value)
    if code is None:
        raise CatalogReadError(
            "unsupported_category",
            "This Catalog category is not supported.",
            status.HTTP_404_NOT_FOUND,
        )
    return code


def _category_view(
    definition: CategoryDefinition,
    counts: dict[str, tuple[int, int]],
) -> CatalogCategoryView:
    product_count, available_product_count = counts.get(definition.code, (0, 0))
    return CatalogCategoryView(
        code=definition.code,
        display_name=definition.display_name,
        product_count=product_count,
        available_product_count=available_product_count,
    )


def _availability(sku, inventory) -> AvailabilityView:
    if inventory is None:
        return AvailabilityView(
            sale_status=sku.sale_status,
            available_quantity=0,
            in_stock=False,
            reason_code="inventory_missing",
        )
    available = max(0, inventory.on_hand_quantity - inventory.reserved_quantity)
    return AvailabilityView(
        sale_status=sku.sale_status,
        available_quantity=available,
        in_stock=available > 0,
        reason_code=None if available > 0 else "out_of_stock",
    )


def _number_value(value: Any) -> int | str:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("number specification has an invalid value")
    decimal_value = Decimal(str(value))
    if decimal_value == decimal_value.to_integral_value():
        return int(decimal_value)
    return format(decimal_value, "f")


def _specification_value(attribute, value: Any) -> tuple[Any, str]:
    if attribute.type == "number":
        return _number_value(value), "number"
    if attribute.type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("boolean specification has an invalid value")
        return value, "boolean"
    if attribute.type == "string":
        if not isinstance(value, str):
            raise ValueError("string specification has an invalid value")
        return value, "string"
    if attribute.multi_valued:
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ValueError("multi-valued enum specification has an invalid value")
        return [attribute.canonicalize_enum(item) for item in value], "string_list"
    return attribute.canonicalize_enum(value), "enum"


def _specifications(
    registry: CategoryRegistry,
    category_code: str,
    product_attributes: dict[str, Any],
    variant_attributes: dict[str, Any] | None = None,
    *,
    only_variant: bool = False,
) -> list[CatalogSpecificationView]:
    definition = registry.schema_for(category_code)
    merged = {**product_attributes, **(variant_attributes or {})}
    issues = registry.validate_catalog_attributes(
        category_code, merged, path="catalog.attributes"
    )
    if issues:
        raise CatalogReadError(
            "catalog_data_invalid",
            "Catalog data could not be displayed safely.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    output: list[CatalogSpecificationView] = []
    for key in definition.display_fields:
        attribute = definition.attribute_for(key)
        if attribute is None:
            continue
        catalog_key = attribute.canonical_catalog_key
        if catalog_key not in merged:
            continue
        if only_variant and catalog_key not in (variant_attributes or {}):
            continue
        value, value_type = _specification_value(attribute, merged[catalog_key])
        output.append(
            CatalogSpecificationView(
                key=key,
                label=attribute.label,
                value=value,
                value_type=value_type,
                unit=attribute.unit,
                display_order=attribute.display_order,
                comparable=attribute.comparable,
                format_hint=attribute.format_hint,
            )
        )
    return output


def _sku_view(
    registry: CategoryRegistry, category_code: str, product, sku, inventory
) -> CatalogSkuView:
    return CatalogSkuView(
        sku_id=sku.id,
        sku_code=sku.sku_code,
        sku_name=sku.name,
        money=Money(
            amount=format(Decimal(sku.money_amount).quantize(Decimal("0.01")), ".2f"),
            currency=sku.currency,
        ),
        availability=_availability(sku, inventory),
        variant_specifications=_specifications(
            registry,
            category_code,
            product.attributes_json,
            sku.variant_attributes_json,
            only_variant=True,
        ),
    )


def _group_rows(rows):
    groups: dict[str, dict[str, Any]] = {}
    for product, sku, inventory in rows:
        group = groups.setdefault(
            product.product_code, {"product": product, "rows": []}
        )
        group["rows"].append((sku, inventory))
    return list(groups.values())


def _summary(registry: CategoryRegistry, counts, group) -> CatalogProductSummary:
    product = group["product"]
    category_code = product.category.code
    definition = registry.schema_for(category_code)
    skus = [
        _sku_view(registry, category_code, product, sku, inventory)
        for sku, inventory in group["rows"]
    ]
    return CatalogProductSummary(
        product_id=product.id,
        product_code=product.product_code,
        brand=product.brand,
        name=product.name,
        category=_category_view(definition, counts),
        specifications=_specifications(
            registry, category_code, product.attributes_json
        ),
        skus=skus,
    )


@router.get("/catalog/categories", response_model=CatalogCategoryListResponse)
async def list_catalog_categories(
    session: Session = Depends(get_db_session),
) -> CatalogCategoryListResponse | JSONResponse:
    try:
        registry = default_category_registry()
        counts = catalog_product_counts(session)
        return CatalogCategoryListResponse(
            items=[
                _category_view(definition, counts)
                for definition in registry.supported_categories()
            ]
        )
    except CatalogReadError as exc:
        return _error_response(exc)
    except Exception:
        return _error_response(
            CatalogReadError(
                "catalog_unavailable",
                "Catalog is temporarily unavailable.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        )


@router.get(
    "/catalog/products",
    response_model=CatalogProductListResponse,
    responses={
        404: {"model": CatalogErrorResponse},
        503: {"model": CatalogErrorResponse},
    },
)
async def list_catalog_products(
    category: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> CatalogProductListResponse | JSONResponse:
    try:
        registry = default_category_registry()
        category_code = _resolve_category(registry, category)
        counts = catalog_product_counts(session)
        groups = _group_rows(
            list_catalog_product_rows(session, category_code=category_code)
        )
        definition = registry.schema_for(category_code)
        category_view = _category_view(definition, counts)
        items = [
            _summary(registry, counts, group)
            for group in groups[offset : offset + limit]
        ]
        return CatalogProductListResponse(
            category=category_view,
            items=items,
            total=len(groups),
            limit=limit,
            offset=offset,
        )
    except CatalogReadError as exc:
        return _error_response(exc)
    except Exception:
        return _error_response(
            CatalogReadError(
                "catalog_unavailable",
                "Catalog is temporarily unavailable.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        )


@router.get(
    "/catalog/products/{product_code}",
    response_model=CatalogProductDetail,
    responses={
        404: {"model": CatalogErrorResponse},
        503: {"model": CatalogErrorResponse},
    },
)
async def get_catalog_product(
    product_code: str, session: Session = Depends(get_db_session)
) -> CatalogProductDetail | JSONResponse:
    try:
        registry = default_category_registry()
        groups = _group_rows(
            list_catalog_product_rows(session, product_code=product_code)
        )
        if not groups:
            raise CatalogReadError(
                "catalog_not_found",
                "Catalog product was not found.",
                status.HTTP_404_NOT_FOUND,
            )
        counts = catalog_product_counts(session)
        summary = _summary(registry, counts, groups[0])
        return CatalogProductDetail(
            **summary.model_dump(), description=groups[0]["product"].description
        )
    except CatalogReadError as exc:
        return _error_response(exc)
    except Exception:
        return _error_response(
            CatalogReadError(
                "catalog_unavailable",
                "Catalog is temporarily unavailable.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        )
