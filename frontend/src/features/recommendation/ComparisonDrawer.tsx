import { useEffect, useRef, type RefObject } from "react";
import type { RecommendationChoice } from "./recommendationTypes";
import { ProductSpecifications } from "./ProductSpecifications";
import { formatAvailability, formatMoney } from "./recommendationFormatters";

const TH_CELL = "border-b border-border p-3 text-left align-top text-sm text-text-muted";
const TD_CELL = "border-b border-border p-3 align-top text-[0.8rem]";

export function ComparisonDrawer({
  open,
  choices,
  onClose,
  restoreFocus,
}: {
  open: boolean;
  choices: RecommendationChoice[];
  onClose: () => void;
  restoreFocus: RefObject<HTMLButtonElement | null>;
}) {
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
        const controls = dialog
          ? Array.from(
              dialog.querySelectorAll<HTMLElement>(
                "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])",
              ),
            )
          : [];
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (first && last && event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (first && last && !event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open, onClose, restoreFocus]);
  if (!open) return null;
  const definitionByCode = new Map<string, (typeof choices)[number]["specifications"][number]>();
  for (const specification of choices.flatMap((choice) =>
    choice.specifications.filter((item) => item.comparable),
  )) {
    const current = definitionByCode.get(specification.code);
    if (
      !current ||
      specification.display_order < current.display_order ||
      (specification.display_order === current.display_order &&
        `${specification.name}${specification.unit ?? ""}` < `${current.name}${current.unit ?? ""}`)
    )
      definitionByCode.set(specification.code, specification);
  }
  const specificationDefinitions = Array.from(definitionByCode.values()).sort(
    (left, right) =>
      left.display_order - right.display_order || left.code.localeCompare(right.code),
  );
  return (
    <div
      className="fixed inset-0 z-20 flex items-end justify-center p-4 max-[640px]:p-0"
      role="presentation"
      style={{ background: "rgba(15, 23, 42, 0.32)" }}
    >
      <section
        className="max-h-[min(78vh,700px)] w-full max-w-[1080px] overflow-auto rounded-t-lg border border-border bg-surface p-5 shadow-[0_-16px_46px_rgb(15,23,42,0.2)] max-[640px]:max-h-[88vh] max-[640px]:p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="comparison-title"
      >
        <header className="mb-4 flex items-start justify-between">
          <div>
            <span className="text-xs font-extrabold tracking-wide text-brand">当前推荐结果</span>
            <h2 className="mt-1 text-lg" id="comparison-title">
              SKU 对比
            </h2>
          </div>
          <button
            className="cursor-pointer rounded-[0.55rem] border border-border bg-transparent px-2.5 py-2 text-text-muted"
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="关闭对比"
          >
            关闭
          </button>
        </header>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] border-collapse">
            <thead>
              <tr>
                <th className={TH_CELL} scope="col">
                  项目
                </th>
                {choices.map((choice) => (
                  <th
                    className="min-w-[170px] border-b border-border p-3 text-left align-top text-text-primary"
                    key={choice.sku_id}
                    scope="col"
                  >
                    {choice.product_name}
                    <small className="mt-1 block font-normal text-text-subtle">
                      {choice.sku_name}
                    </small>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th className={TH_CELL} scope="row">
                  价格
                </th>
                {choices.map((choice) => (
                  <td className={TD_CELL} key={choice.sku_id}>
                    {formatMoney(choice.money)}
                  </td>
                ))}
              </tr>
              <tr>
                <th className={TH_CELL} scope="row">
                  库存
                </th>
                {choices.map((choice) => (
                  <td className={TD_CELL} key={choice.sku_id}>
                    {formatAvailability(choice.availability)}
                  </td>
                ))}
              </tr>
              <tr>
                <th className={TH_CELL} scope="row">
                  综合匹配
                </th>
                {choices.map((choice) => (
                  <td className={TD_CELL} key={choice.sku_id}>
                    {choice.score === undefined ? "—" : `${choice.score}/100`}
                  </td>
                ))}
              </tr>
              {specificationDefinitions.map((definition) => (
                <tr key={definition.code}>
                  <th className={TH_CELL} scope="row">
                    {definition.name}
                    {definition.unit ? `（${definition.unit}）` : ""}
                  </th>
                  {choices.map((choice) => (
                    <td
                      className={`${TD_CELL} empty:after:text-text-subtle empty:after:content-['—']`}
                      key={choice.sku_id}
                    >
                      <ProductSpecifications
                        compact
                        hideLabel
                        specifications={choice.specifications.filter(
                          (specification) => specification.code === definition.code,
                        )}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
