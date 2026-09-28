# Shared components

Presentational building blocks with no business semantics. Feature code composes them; they never import from `src/features` or `src/api`.

```text
components/
├── cn.ts          class-name joiner
└── primitives/    Button Badge Card Field Skeleton Empty Spinner
```

Planned next: `overlay/` (Drawer, Dialog, Toast), `data/` (KeyValue, StatusDot, Timeline, JsonViewer, CopyButton), `layout/` (PageHeader, Section, SplitPane).

Rules:

- Styling is Tailwind utilities on top of the tokens in `src/styles/theme.css`.
- Tailwind's Preflight is loaded (since P4.5), so a bare `border`/`border-t`/etc. is enough — no need for the old `border border-solid` pairing.
- Every prop that a test or a stable selector may need (`className`, `data-testid`, `aria-*`) is passed through to the DOM element.
