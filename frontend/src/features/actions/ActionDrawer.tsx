import { useEffect, useMemo, useState } from "react";
import type {
  ActionErrorResponse,
  AddToCartPreview,
  EditableField,
  PendingActionTransitionRequest,
  PendingActionView,
} from "../../api/contracts";
import { Drawer } from "../../components/overlay";
import { Badge, Button } from "../../components/primitives";
import { FIELD_LABEL } from "../../components/textPatterns";
import { actionErrorMessage } from "./actionErrors";

type UpdatedFields = PendingActionTransitionRequest["updated_fields"];
type LegacyActionInput = {
  id: string;
  actionType: "add_to_cart" | "save_preference";
  riskClass: "high" | "medium";
  preview: string;
};
type DrawerAction = PendingActionView | LegacyActionInput;

interface ActionDrawerProps {
  action: DrawerAction;
  busy: boolean;
  error: ActionErrorResponse | null;
  resolution?: {
    requested_quantity?: number | null;
    cart_quantity?: number | null;
    price_changed?: boolean;
    idempotent_replay?: boolean;
  } | null;
  onCancel: () => void;
  onConfirm: (updatedFields?: UpdatedFields) => void;
  onDismiss?: () => void;
}

const FIELD_INPUT =
  "rounded-sm border border-border-strong bg-surface px-3 py-2.5 text-sm text-text-primary normal-case tracking-normal";

export function ActionDrawer({
  action,
  busy,
  error,
  resolution,
  onCancel,
  onConfirm,
  onDismiss,
}: ActionDrawerProps) {
  const typed = "pending_action_id" in action;
  const actionId = typed ? action.pending_action_id : action.id;
  const actionType = typed ? action.action_type : action.actionType;
  const riskClass = typed ? action.risk_class : action.riskClass;
  const status = typed ? action.status : "pending";
  const fallbackFields: EditableField[] =
    actionType === "add_to_cart"
      ? [
          {
            field_type: "integer",
            field: "quantity",
            label: "Quantity",
            current_value: 1,
            min_value: 1,
            max_value: 20,
            required: true,
          },
        ]
      : [
          {
            field_type: "enum",
            field: "preference_type",
            label: "Preference type",
            current_value: "other",
            options: ["budget", "brand", "avoid", "usage", "style", "other"],
            required: true,
          },
          {
            field_type: "text",
            field: "preference_value",
            label: "Preference value",
            current_value: "",
            min_length: 1,
            max_length: 2000,
            required: true,
          },
        ];
  const fields: EditableField[] = typed
    ? (action.editable_fields ?? fallbackFields)
    : fallbackFields;
  const integerField = fields.find((field) => field.field_type === "integer");
  const enumField = fields.find((field) => field.field_type === "enum");
  const textField = fields.find((field) => field.field_type === "text");
  const [quantity, setQuantity] = useState("");
  const [preferenceType, setPreferenceType] = useState("");
  const [preferenceValue, setPreferenceValue] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  useEffect(() => {
    setQuantity(
      integerField?.current_value !== undefined ? String(integerField.current_value) : "",
    );
    setPreferenceType(enumField?.current_value ?? "");
    setPreferenceValue(textField?.current_value ?? "");
    setValidationError(null);
  }, [actionId, integerField?.current_value, enumField?.current_value, textField?.current_value]);
  const terminal = status !== "pending";
  const displayError = validationError ?? (error ? actionErrorMessage(error) : null);
  function submitConfirm() {
    setValidationError(null);
    if (terminal) return;
    if (integerField) {
      const parsed = Number(quantity);
      if (
        !Number.isInteger(parsed) ||
        parsed < integerField.min_value ||
        parsed > integerField.max_value
      ) {
        setValidationError(
          `数量必须是 ${integerField.min_value} 到 ${integerField.max_value} 之间的整数。`,
        );
        return;
      }
      onConfirm({ quantity: parsed });
      return;
    }
    const updated: Record<string, string> = {};
    if (enumField && preferenceType !== enumField.current_value)
      updated.preference_type = preferenceType;
    if (textField && preferenceValue !== textField.current_value)
      updated.preference_value = preferenceValue.trim();
    if (Object.keys(updated).length === 0) return onConfirm(undefined);
    if (
      (updated.preference_type && !updated.preference_value) ||
      (updated.preference_value && !updated.preference_type)
    ) {
      setValidationError("修改偏好类型时，请同时填写偏好内容。");
      return;
    }
    onConfirm(updated);
  }
  const preview = useMemo(() => {
    if (!action.preview || typeof action.preview === "string")
      return <p>{action.preview ?? "待确认操作"}</p>;
    const item = action.preview as AddToCartPreview;
    return (
      <>
        <h3 className="m-0 text-base">{item.product_name}</h3>
        {item.sku_name && (
          <p className="m-0 mt-1 text-sm">
            {item.sku_name}
            {item.sku_code ? ` · ${item.sku_code}` : ""}
          </p>
        )}
        <p className="m-0 mt-1 text-sm">数量：{item.requested_quantity}</p>
        {item.unit_money_snapshot && (
          <p className="m-0 mt-1 text-sm">
            创建时价格：{item.unit_money_snapshot.currency} {item.unit_money_snapshot.amount}
          </p>
        )}
        {item.availability_snapshot && (
          <p className="m-0 mt-1 text-sm">
            创建时库存：
            {item.availability_snapshot.in_stock
              ? `可用 ${item.availability_snapshot.available_quantity}`
              : "当时不可用"}
          </p>
        )}
        {item.preview_text && <small className="text-text-subtle">{item.preview_text}</small>}
      </>
    );
  }, [action.preview]);
  return (
    <Drawer
      as="aside"
      backdrop={false}
      className="grid gap-4 border-t border-warning/25 bg-warning-soft p-5.5"
      labelledBy="action-title"
      onClose={onDismiss}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="m-0 mb-[0.7rem] text-[0.68rem] font-extrabold tracking-[0.16em] text-brand uppercase">
            HUMAN CONFIRMATION
          </p>
          <h2 className="m-0 text-xl" id="action-title">
            待确认操作
          </h2>
        </div>
        <Badge tone={riskClass === "high" ? "danger" : "warning"}>
          {riskClass === "high" ? "高风险" : "需确认"}
        </Badge>
      </div>
      <div className="grid gap-2.5 rounded-md border border-border bg-surface-soft p-3.5">
        <span className="text-xs font-extrabold tracking-wide text-text-muted uppercase">
          {actionType === "add_to_cart" ? "加入 RetailPilot 购物车" : "保存偏好"}
        </span>
        {preview}
        <small className="text-xs text-text-subtle">
          状态：{status} · 版本 {typed ? action.version : 1}
        </small>
      </div>
      {actionType === "add_to_cart" && integerField && (
        <label className={FIELD_LABEL} htmlFor="action-quantity">
          数量
          <input
            className={FIELD_INPUT}
            data-testid="action-quantity"
            id="action-quantity"
            inputMode="numeric"
            min={integerField.min_value}
            max={integerField.max_value}
            onChange={(event) => setQuantity(event.target.value)}
            type="number"
            value={quantity}
            disabled={terminal || busy}
          />
          <small className="tracking-normal text-text-subtle normal-case">
            范围：{integerField.min_value}–{integerField.max_value}
          </small>
        </label>
      )}
      {actionType === "save_preference" && enumField && textField && (
        <div className="grid gap-3.5">
          <label className={FIELD_LABEL} htmlFor="action-preference-type">
            偏好类型
            <select
              className={FIELD_INPUT}
              id="action-preference-type"
              value={preferenceType}
              disabled={terminal || busy}
              onChange={(event) => setPreferenceType(event.target.value)}
            >
              {enumField.options.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className={FIELD_LABEL} htmlFor="action-preference-value">
            偏好内容
            <input
              className={FIELD_INPUT}
              data-testid="action-preference-value"
              id="action-preference-value"
              value={preferenceValue}
              disabled={terminal || busy}
              onChange={(event) => setPreferenceValue(event.target.value)}
              minLength={textField.min_length}
              maxLength={textField.max_length}
            />
          </label>
        </div>
      )}
      {resolution && (
        <div className="rounded-md border border-border bg-surface-soft p-3 text-sm" role="status">
          {resolution.idempotent_replay
            ? "该操作此前已处理，本次没有重复写入。"
            : resolution.cart_quantity
              ? `已加入购物车，共 ${resolution.cart_quantity} 件。`
              : "操作已取消。"}
        </div>
      )}
      {displayError && (
        <div
          className="rounded-md border border-danger/25 bg-danger-soft p-3 text-sm text-danger"
          role="alert"
        >
          {displayError}
        </div>
      )}
      <div className="flex flex-wrap gap-2.5">
        <Button
          data-testid="action-cancel"
          disabled={busy || terminal}
          onClick={onCancel}
          variant="danger"
        >
          取消操作
        </Button>
        <Button data-testid="action-confirm" disabled={busy || terminal} onClick={submitConfirm}>
          {busy ? "提交中…" : "确认执行"}
        </Button>
        {onDismiss && (
          <Button onClick={onDismiss} variant="ghost">
            关闭
          </Button>
        )}
      </div>
      <p className="m-0 text-xs text-text-subtle">确认时后端会重新校验价格、库存和权限。</p>
    </Drawer>
  );
}
