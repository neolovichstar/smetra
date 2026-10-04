# Conversational web workspace

The web cabinet now uses a conversational layout: a quiet charcoal canvas, compact dark navigation and a central request composer. This changes the web interface only.

- Dashboard content has a dedicated wrapper. The request composer takes visual priority; the four work metrics remain available in a compact row.
- Empty attention, work and deadline sections collapse; populated sections retain their actions and records.
- The request field, attachment picker and draft action share a single rounded composer. The original accessible labels, file limits and submission handlers remain intact. Selecting an attachment shows its name using text content.
- Sidebar dividers, decorative accents and the workspace eyebrow are removed. Search remains an accessible icon control and all product sections remain available.
- Other cabinet pages share the charcoal background, subdued controls and typography. The assistant uses softer message bubbles and a rounded composer.
- Authentication and public customer pages retain their existing styles.

Validation: web build and JavaScript syntax checks passed; 1440px and 390px screenshots reviewed without horizontal overflow. Existing browser integration passed registration, client, catalog, estimate editor preview/undo, quote approval, project, payment, PDF and public intake. Assistant integration passed streaming preview/apply/undo, conversation contexts, reload retries, background file preparation and draft persistence. Model responses in local QA are mocked; the real local API handles all product operations.
