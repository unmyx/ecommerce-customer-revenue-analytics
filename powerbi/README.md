# Power BI dashboard

The presentation layer for the NovaCart project. The dashboard is **built from generated datasets**;
no value is typed into Power BI by hand.

```
raw schema -> analytical SQL -> Python analytics -> dashboard exports (CSV) -> Power BI
```

## What is in this folder

| File | Purpose |
| --- | --- |
| `README.md` | This build guide |
| `page_specs.md` | Field-by-field specification for the four dashboard pages |
| `measures.dax` | Every DAX measure, written as an aggregation of canonical columns |
| `theme.json` | Power BI theme (colours, typography, card styling) |
| `screenshots/` | Static page previews rendered from the exported data by `python scripts/build_dashboard.py` |

## 1. Generate the data

```bash
docker compose up -d
python scripts/generate_data.py
python scripts/load_raw.py
python scripts/build_analytics_layer.py
python scripts/build_business_analysis.py
python scripts/build_dashboard.py
```

Outputs:

* `outputs/dashboard/csv/` - 18 dashboard datasets plus `data_dictionary.csv` and
  `export_manifest.json` (row counts, columns, SHA-256 checksums);
* `outputs/dashboard/summary/` - the executive summary in Markdown, HTML and Excel;
* `powerbi/screenshots/` - the four page previews.

## 2. Load the data into Power BI

1. **Get Data -> Folder**, pointing at `outputs/dashboard/csv/`.
2. **Combine Files** with `Transform Sample File`: keep the content column, promote headers, keep the
   file name as the table name. (Equally valid: **Get Data -> Text/CSV** once per file, 18 tables.)
3. Rename queries to the dataset names (`fact_orders`, `monthly_revenue`, ...) and set data types from
   `data_dictionary.csv` (`date` -> Date, `int` -> Whole Number, `decimal` -> Decimal Number,
   `boolean` -> True/False, `text` -> Text).
4. **Close & Apply**.

Start with `fact_orders`, `fact_order_lines`, `kpi_summary`, `monthly_revenue`, `daily_revenue` and
`campaign_results`; the remaining tables are small and can be added as each page is built.

## 3. Date table

Modeling -> New table:

```dax
Date =
VAR StartDate = MIN ( fact_orders[order_date] )
VAR EndDate = MAX ( fact_orders[order_date] )
RETURN
ADDCOLUMNS (
    CALENDAR ( StartDate, EndDate ),
    "Year", YEAR ( [Date] ),
    "Quarter", "Q" & QUARTER ( [Date] ),
    "Month", FORMAT ( [Date], "mmm" ),
    "Month Start", EOMONTH ( [Date], -1 ) + 1,
    "Year-Month", FORMAT ( [Date], "yyyy-mm" ),
    "Weekday", FORMAT ( [Date], "ddd" ),
    "Is Weekend", WEEKDAY ( [Date], 2 ) >= 6
)
```

Mark it as the date table (`Date[Date]`) and create these relationships (single direction, no
many-to-many):

| From | To | Cardinality | Active |
| --- | --- | --- | --- |
| `Date[Date]` | `fact_orders[order_date]` | 1 -> many | yes |
| `Date[Date]` | `fact_order_lines[order_date]` | 1 -> many | yes |
| `Date[Date]` | `daily_revenue[order_date]` | 1 -> 1 | yes |
| `Date[Month Start]` | `monthly_revenue[month_start]` | 1 -> 1 | yes |
| `Date[Month Start]` | `cohort_sizes[cohort_month]` | 1 -> many | no |
| `Date[Month Start]` | `cohort_retention[cohort_month]` | 1 -> many | no |

The aggregated tables and the fact tables are alternative views of the same canonical numbers; they
are deliberately not related to each other. A test proves that every aggregate reconciles exactly
with the facts (`tests/test_dashboard_exports.py`).

## 4. Measures and theme

1. Modeling -> New measure: paste the blocks from `measures.dax`. Page 1 uses the `Window ...`
   measures, page 2 the segment and cohort measures, page 4 the campaign measures.
2. View -> Themes -> Browse for themes: select `theme.json`.

## 5. Build the pages

Follow `page_specs.md`. It lists every visual, the exact fields, the slicers and the annotation text
that must appear (the intention-to-treat caveat, the cohort censoring note and the synthetic-data
footer).

## 6. Refresh and publish

* Re-run `python scripts/build_dashboard.py`, then **Refresh** in Power BI Desktop.
* Publish to a workspace and, optionally, pin the executive KPI cards to a dashboard.

## 7. Automated versus manual

| Automated in this repository | Manual in Power BI Desktop |
| --- | --- |
| 18 datasets, data dictionary, export manifest | Folder connector and data types |
| Documented relationships and date table | Creating the relationships in the model view |
| Every DAX measure (`measures.dax`) | Pasting measures and applying the theme |
| Page layout specification (`page_specs.md`) | Placing visuals on the four pages |
| Page previews for the portfolio (`screenshots/`) | Saving the `.pbix` (and publishing) |

The `.pbix` file itself is not committed: Power BI Desktop cannot be driven from the project
environment, so the dashboard is delivered as a fully specified, reproducible build rather than a
binary artefact.

