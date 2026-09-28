/**
 * Small cross-feature typographic conventions shared by page-level components
 * (eyebrow labels, page/section heading rows, muted lede copy, loading/empty
 * placeholders, inline error banners). Kept as plain class strings rather than
 * components: every caller already owns its own heading levels and layout, so
 * a wrapper component would just be a pass-through.
 */
export const EYEBROW =
  "m-0 mb-[0.7rem] text-[0.68rem] font-extrabold uppercase tracking-[0.16em] text-brand";

export const PAGE_HEADING = "flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between";

export const PAGE_LEDE = "mt-4 max-w-[760px] text-base leading-[1.75] text-text-muted";

export const SECTION_HEADING =
  "flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:justify-between";

export const LOADING_PANEL =
  "rounded-md border border-dashed border-border-strong bg-white/76 p-5 text-center text-text-muted";

export const ERROR_STATE =
  "flex flex-wrap items-center justify-between gap-4 rounded-md border border-solid border-[#f1d5d4] bg-danger-soft p-3.5 text-danger";

export const TEXT_BUTTON =
  "inline-flex min-h-10 cursor-pointer items-center justify-center rounded-md border-0 bg-transparent px-2 text-sm font-bold text-brand-strong hover:text-brand disabled:cursor-not-allowed disabled:opacity-50";

/**
 * Match `components/primitives/Button`'s generated classes exactly, for the rare spot
 * that needs a native `<button ref>` (focus management — Button isn't forwardRef) or a
 * `<Link>` styled as a button (Button has no `as` prop). Also doubles as a byte-size
 * lever: one definition here costs far less in the compiled JS bundle than the same long
 * utility string repeated as a className literal at every call site.
 */
const BUTTON_BASE =
  "inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded-md border border-solid px-4 text-sm font-semibold transition-colors duration-150 ease-standard disabled:cursor-not-allowed disabled:opacity-55";
export const BUTTON_PRIMARY = `${BUTTON_BASE} border-brand bg-brand text-white hover:border-brand-strong hover:bg-brand-strong`;
export const BUTTON_SECONDARY = `${BUTTON_BASE} border-border-strong bg-surface text-text-primary hover:bg-surface-soft`;
export const BUTTON_DANGER = `${BUTTON_BASE} border-danger bg-danger text-white hover:opacity-90`;

export const STAT_CARD =
  "grid gap-1 rounded-sm border border-solid border-border bg-surface-soft p-3";

export const FIELD_LABEL =
  "grid gap-1.5 text-xs font-extrabold tracking-wide text-text-muted uppercase";

/** A product/order line: name + meta on the left, quantity/price stacked on the right. */
export const LINE_ITEM_ROW =
  "flex items-center justify-between gap-4 border-t border-solid border-border pt-4 first:border-t-0 first:pt-0";

/** The small uppercase brand-colored tag above a card/section heading (not the page-level EYEBROW). */
export const BRAND_TAG = "text-xs font-extrabold uppercase tracking-wide text-brand";

/** A brand-tinted callout box (structured constraints, policy evidence, composer hints). */
export const INFO_BOX =
  "grid gap-2 rounded-md border border-solid border-[#c9e9dd] bg-brand-soft p-4";
