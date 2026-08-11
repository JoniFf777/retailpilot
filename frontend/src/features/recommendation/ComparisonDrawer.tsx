import { useEffect, useRef, type RefObject } from "react";
import type { RecommendationChoice } from "./recommendationTypes";
import { ProductSpecifications } from "./ProductSpecifications";
import { formatAvailability, formatMoney } from "./recommendationFormatters";

export function ComparisonDrawer({ open, choices, onClose, restoreFocus }: { open: boolean; choices: RecommendationChoice[]; onClose: () => void; restoreFocus: RefObject<HTMLButtonElement | null> }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const previousOpenRef = useRef(false);
  useEffect(() => {
    if (!open) {
      if (previousOpenRef.current) {
        previousOpenRef.current = false;
        restoreFocus.current?.focus();
      }
      return;
    }
    previousOpenRef.current = true;
    closeRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "Tab") {
        const dialog = closeRef.current?.closest("[role=dialog]");
        const controls = dialog ? Array.from(dialog.querySelectorAll<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])")) : [];
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (first && last && event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (first && last && !event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open, onClose, restoreFocus]);
  if (!open) return null;
  const definitionByCode = new Map<string, typeof choices[number]["specifications"][number]>();
  for (const specification of choices.flatMap((choice) => choice.specifications.filter((item) => item.comparable))) {
    const current = definitionByCode.get(specification.code);
    if (!current || specification.display_order < current.display_order || (specification.display_order === current.display_order && `${specification.name}${specification.unit ?? ""}` < `${current.name}${current.unit ?? ""}`)) definitionByCode.set(specification.code, specification);
  }
  const specificationDefinitions = Array.from(definitionByCode.values()).sort((left, right) => left.display_order - right.display_order || left.code.localeCompare(right.code));
  return <div className="comparison-backdrop" role="presentation"><section className="comparison-drawer" role="dialog" aria-modal="true" aria-labelledby="comparison-title"><header><div><span>当前推荐结果</span><h2 id="comparison-title">SKU 对比</h2></div><button ref={closeRef} type="button" onClick={onClose} aria-label="关闭对比">关闭</button></header><div className="comparison-scroll"><table><thead><tr><th scope="col">项目</th>{choices.map((choice) => <th key={choice.sku_id} scope="col">{choice.product_name}<small>{choice.sku_name}</small></th>)}</tr></thead><tbody><tr><th scope="row">价格</th>{choices.map((choice) => <td key={choice.sku_id}>{formatMoney(choice.money)}</td>)}</tr><tr><th scope="row">库存</th>{choices.map((choice) => <td key={choice.sku_id}>{formatAvailability(choice.availability)}</td>)}</tr><tr><th scope="row">综合匹配</th>{choices.map((choice) => <td key={choice.sku_id}>{choice.score === undefined ? "—" : `${choice.score}/100`}</td>)}</tr>{specificationDefinitions.map((definition) => <tr key={definition.code}><th scope="row">{definition.name}{definition.unit ? `（${definition.unit}）` : ""}</th>{choices.map((choice) => <td key={choice.sku_id}><ProductSpecifications compact specifications={choice.specifications.filter((specification) => specification.code === definition.code)} /></td>)}</tr>)}</tbody></table></div></section></div>;
}
