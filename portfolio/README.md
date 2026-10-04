# Portfolio assets

Curated, publish-ready material generated from the project's canonical results. Nothing here is
hand-edited: `python scripts/build_portfolio.py` regenerates every image and sample file, and
`assets_manifest.json` records their checksums.

| Asset | What it shows |
| --- | --- |
| `screenshots/01_architecture.png` | The six-layer platform, from synthetic generation to Power BI |
| `screenshots/02_executive_dashboard.png` | Executive page: KPIs, revenue and order trends, category/segment/country mix, campaign lift |
| `screenshots/03_revenue_analysis.png` | Monthly revenue trend, category mix and top-10 country mix |
| `screenshots/04_rfm_segmentation.png` | Segment sizes, revenue by segment and customer value deciles |
| `screenshots/05_cohort_heatmap.png` | Monthly cohort retention heatmap |
| `screenshots/06_campaign_statistics.png` | Campaign lift and 95% confidence intervals |

`sample_outputs/` contains small copies of the real generated files so a reviewer can inspect
results without running the pipeline: the KPI snapshot, monthly revenue, RFM segment summary,
campaign results, declining products, the executive summary and the end-to-end reconciliation.

The case study narrative is in [case-study.md](case-study.md).

Regenerate:

```bash
python scripts/build_dashboard.py     # datasets, executive summary, page previews
python scripts/build_portfolio.py     # portfolio images and samples
```

The images are rendered with Matplotlib from the same data the dashboard uses, so they stay
consistent with the Power BI build specification in `powerbi/`.

