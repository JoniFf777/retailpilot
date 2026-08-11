import { useEffect, useMemo, useState } from "react";
import type { ActionErrorResponse, AddToCartPreview, EditableField, PendingActionTransitionRequest, PendingActionView } from "../../api/contracts";
import { actionErrorMessage } from "./actionErrors";

type UpdatedFields = PendingActionTransitionRequest["updated_fields"];
type LegacyActionInput = { id: string; actionType: "add_to_cart" | "save_preference"; riskClass: "high" | "medium"; preview: string };
type DrawerAction = PendingActionView | LegacyActionInput;

interface ActionDrawerProps { action: DrawerAction; busy: boolean; error: ActionErrorResponse | null; resolution?: { requested_quantity?: number | null; cart_quantity?: number | null; price_changed?: boolean; idempotent_replay?: boolean } | null; onCancel: () => void; onConfirm: (updatedFields?: UpdatedFields) => void; onDismiss?: () => void; }

export function ActionDrawer({ action, busy, error, resolution, onCancel, onConfirm, onDismiss }: ActionDrawerProps) {
  const typed = "pending_action_id" in action;
  const actionId = typed ? action.pending_action_id : action.id;
  const actionType = typed ? action.action_type : action.actionType;
  const riskClass = typed ? action.risk_class : action.riskClass;
  const status = typed ? action.status : "pending";
  const fallbackFields: EditableField[] = actionType === "add_to_cart" ? [{ field_type: "integer", field: "quantity", label: "Quantity", current_value: 1, min_value: 1, max_value: 20, required: true }] : [{ field_type: "enum", field: "preference_type", label: "Preference type", current_value: "other", options: ["budget", "brand", "avoid", "usage", "style", "other"], required: true }, { field_type: "text", field: "preference_value", label: "Preference value", current_value: "", min_length: 1, max_length: 2000, required: true }];
  const fields: EditableField[] = typed ? (action.editable_fields ?? fallbackFields) : fallbackFields;
  const integerField = fields.find((field) => field.field_type === "integer");
  const enumField = fields.find((field) => field.field_type === "enum");
  const textField = fields.find((field) => field.field_type === "text");
  const [quantity, setQuantity] = useState("");
  const [preferenceType, setPreferenceType] = useState("");
  const [preferenceValue, setPreferenceValue] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  useEffect(() => { setQuantity(integerField?.current_value !== undefined ? String(integerField.current_value) : ""); setPreferenceType(enumField?.current_value ?? ""); setPreferenceValue(textField?.current_value ?? ""); setValidationError(null); }, [actionId, integerField?.current_value, enumField?.current_value, textField?.current_value]);
  const terminal = status !== "pending";
  const displayError = validationError ?? (error ? actionErrorMessage(error) : null);
  function submitConfirm() {
    setValidationError(null); if (terminal) return;
    if (integerField) { const parsed = Number(quantity); if (!Number.isInteger(parsed) || parsed < integerField.min_value || parsed > integerField.max_value) { setValidationError(`数量必须是 ${integerField.min_value} 到 ${integerField.max_value} 之间的整数。`); return; } onConfirm({ quantity: parsed }); return; }
    const updated: Record<string, string> = {}; if (enumField && preferenceType !== enumField.current_value) updated.preference_type = preferenceType; if (textField && preferenceValue !== textField.current_value) updated.preference_value = preferenceValue.trim(); if (Object.keys(updated).length === 0) return onConfirm(undefined); if ((updated.preference_type && !updated.preference_value) || (updated.preference_value && !updated.preference_type)) { setValidationError("修改偏好类型时，请同时填写偏好内容。"); return; } onConfirm(updated);
  }
  const preview = useMemo(() => {
    if (!action.preview || typeof action.preview === "string") return <p>{action.preview ?? "待确认操作"}</p>;
    const item = action.preview as AddToCartPreview;
    return <><h3>{item.product_name}</h3>{item.sku_name && <p>{item.sku_name}{item.sku_code ? ` · ${item.sku_code}` : ""}</p>}<p>数量：{item.requested_quantity}</p>{item.unit_money_snapshot && <p>创建时价格：{item.unit_money_snapshot.currency} {item.unit_money_snapshot.amount}</p>}{item.availability_snapshot && <p>创建时库存：{item.availability_snapshot.in_stock ? `可用 ${item.availability_snapshot.available_quantity}` : "当时不可用"}</p>}{item.preview_text && <small>{item.preview_text}</small>}</>;
  }, [action.preview]);
  return <aside className="action-drawer" role="dialog" aria-modal="true" aria-labelledby="action-title"><div className="action-drawer-header"><div><p className="eyebrow">HUMAN CONFIRMATION</p><h2 id="action-title">待确认操作</h2></div><span className={`risk-badge risk-${riskClass}`}>{riskClass === "high" ? "高风险" : "需确认"}</span></div><div className="action-summary"><span className="label">{actionType === "add_to_cart" ? "加入 ShopMind 购物车" : "保存偏好"}</span>{preview}<small>状态：{status} · 版本 {typed ? action.version : 1}</small></div>{actionType === "add_to_cart" && integerField && <label className="field-label" htmlFor="action-quantity">数量<input data-testid="action-quantity" id="action-quantity" inputMode="numeric" min={integerField.min_value} max={integerField.max_value} onChange={(event) => setQuantity(event.target.value)} type="number" value={quantity} disabled={terminal || busy} /><small>范围：{integerField.min_value}–{integerField.max_value}</small></label>}{actionType === "save_preference" && enumField && textField && <div className="action-fields"><label className="field-label" htmlFor="action-preference-type">偏好类型<select id="action-preference-type" value={preferenceType} disabled={terminal || busy} onChange={(event) => setPreferenceType(event.target.value)}>{enumField.options.map((option) => <option key={option} value={option}>{option}</option>)}</select></label><label className="field-label" htmlFor="action-preference-value">偏好内容<input data-testid="action-preference-value" id="action-preference-value" value={preferenceValue} disabled={terminal || busy} onChange={(event) => setPreferenceValue(event.target.value)} minLength={textField.min_length} maxLength={textField.max_length} /></label></div>}{resolution && <div className="action-resolution" role="status">{resolution.idempotent_replay ? "该操作此前已处理，本次没有重复写入。" : resolution.cart_quantity ? `已加入购物车，共 ${resolution.cart_quantity} 件。` : "操作已取消。"}</div>}{displayError && <div className="action-error" role="alert">{displayError}</div>}<div className="action-drawer-actions"><button className="danger-button" data-testid="action-cancel" disabled={busy || terminal} onClick={onCancel} type="button">取消操作</button><button className="primary-button" data-testid="action-confirm" disabled={busy || terminal} onClick={submitConfirm} type="button">{busy ? "提交中…" : "确认执行"}</button>{onDismiss && <button className="text-button" onClick={onDismiss} type="button">关闭</button>}</div><p className="action-safety-note">确认时后端会重新校验价格、库存和权限。</p></aside>;
}
