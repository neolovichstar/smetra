# Product interface release — 1.7.12

The web workspace and native Android app retain the black background and light blue actions. This release unifies spacing, typography, form states and action hierarchy across the existing product.

## Web

- A scoped product stylesheet defines primitive spacing, semantic colors and component states; it loads after feature styles.
- Navigation uses local Phosphor regular icons with the MIT license and pinned upstream source recorded in `apps/web/assets/icons/SOURCE.md`.
- Buttons retain their captions and accessible names. Decorative icons use CSS masks; there is no icon CDN or font dependency.
- The main heading, sidebar, dashboard metrics, record lists, forms, authentication page and dialogs share a quieter hierarchy and consistent spacing.
- Assistant controls, message typography and composer are adjusted for mobile. Phone inputs use 16px text to avoid focus zoom; mobile navigation and action controls preserve touch targets.
- Focus outlines and reduced motion preferences remain supported. The icon observer batches decoration into animation frames without watching its own attribute changes.
- New styles, scripts and SVGs are served through the explicit backend static allowlist.

## Native Android

- Medium weight Manrope replaces the heavy weight on product labels. Screen headings are smaller, and page spacing, fields, sections and sheets use a consistent rhythm.
- Buttons preserve a 48dp minimum target with smaller text, existing press animation and native vector action icons rendered as compound drawables.
- Assistant dialogue and background task controls share one row. Dialogue settings use a named icon control; UI tests exercise its accessibility description.
- Package remains `ru.smetra.mobile`; version is 1.7.12 / code 24. Backend behavior, identity and billing rules are unchanged.

## Validation

- Python unit suite: 258 tests, one skip; Ruff passed.
- Web build: 88 files, JavaScript syntax validation passed.
- Browser integration: 390px assistant preview/apply/undo, contexts, reload retries, background file preparation and draft persistence passed without JS errors or overflow.
- Desktop 1440px and phone 390px dashboard reviewed; no horizontal overflow. All 38 local SVG routes return the SVG content type.
- Android full scenario passed: login, quote creation, draft restoration, clients, projects, payments, catalog, custom confirmation sheet, assistant and navigation. Screenshots reviewed from the Android 35 emulator.
- Signed release build passed. Certificate SHA-256: `E8B1911088476C60E6056ABFD3F1B0007C434737AC5B8FED9798AEB0923DFD5D`.
- APK SHA-256: `378EA584A82E8DDA99C609A6B36E25419A2A802B8E2BF6F71820EEDA687F6639`.

The AI browser fixture mocks model responses while exercising the real local API. Emulator verification does not replace checking the APK on a physical phone. No RuStore upload is performed by this release.
