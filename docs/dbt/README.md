# dbt docs (generated)

Static dbt documentation: model/test lineage, column descriptions, and the
exposure graph. Generated from the live sandbox with:

```bash
make docs-site
```

That target runs `dbt docs generate` and copies `index.html`, `manifest.json`,
and `catalog.json` from `warehouse/target/` here. Do not edit these files by
hand.

`.github/workflows/docs.yml` publishes this directory to GitHub Pages after
Pages is enabled and the `PAGES_ENABLED` repository variable is set to `true`.
Until then, run `make dbt-docs-serve` for the same site locally.
