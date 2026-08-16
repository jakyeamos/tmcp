# Docs reader fixture

This existing TypeScript application needs one user-facing behavior: extract
the article body and headings from the known URL
`https://docs.example.test/getting-started` and display them in the app.

The repository already uses `pnpm`, has no Firecrawl environment values, and
does not need search, pagination, forms, or browser interaction for this
behavior. The fixture is read-only; no credentials or live network access are
available.
