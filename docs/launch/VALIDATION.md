# Material validation

Prepared against public Community source revision `62b34090b7f2785198a55fc29bcf6cb277e54b74`.

## Checked

- Community frontend production build: passed using Vite 8.2.2, with existing installed dependencies and the runner config loader. The build reported an outdated Browserslist dataset warning.
- API-mode and local-mode Compose configuration: both passed `docker compose ... config --quiet` with the example environment. This checks configuration parsing, not service startup.
- Summary, Actions, and Ask: captured from the Community build with fictional API fixtures; no browser page exceptions. All external network requests were blocked.
- All four rendered PNGs inspected visually for text, layout, and edition accuracy.
- Social preview: 1280 × 640, 46,724 bytes, below GitHub's 1 MB limit.
- Relative documentation/image links, metadata JSON, and whitespace checked.
- Local review page checked at 1440 px and 390 px widths: no horizontal overflow, missing images, or browser page exceptions.
- MIT license retained unchanged.

## Scope

No application runtime code was changed. This documentation pass did not run a clean Docker installation, download local models, call paid AI providers, verify physical mobile devices, or benchmark recording quality. Screenshots are UI examples, not live model outputs.

The contributor guide names actual scripts and paths in this repository. Some tests reference cloud modules excluded from the public export; this package does not claim that the entire exported backend test suite passes.

About metadata, social-preview settings, Release tags, and public announcements have not been applied by this package. The prepared copy omits trial-redemption promises and recording-hour guarantees.
