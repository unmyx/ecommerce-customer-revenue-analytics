# Power BI page specifications

Field-by-field build instructions for the four dashboard pages. Every field name is a column of one
of the exported datasets in `outputs/dashboard/csv/`. Rebuild the exports with
`python scripts/build_dashboard.py`.

## Global conventions

* Apply `powerbi/theme.json` (View -> Themes -> Browse for themes).
* Canvas 1280 x 720 (16:9); page background white, outspace `#F7F9FC`.
* Titles are plain text boxes in sentence case. No decorative shapes or images.
* Footer text box on every page: "Synthetic data - portfolio project. Revenue = recognised net
  merchandise revenue (completed orders)."
* Format revenue as `EUR #,0` (AOV `EUR #,0.00`) and rates to one decimal.

---

## Page 1 - Executive overview

| # | Visual | Type | Fields | Notes |
| --- | --- | --- | --- | --- |
| 1 | Net revenue | Card | `Window Net Revenue` | Fixed 24-month window |
| 2 | Orders | Card | `Window Orders` | |
| 3 | Purchasing customers | Card | `Window Purchasing Customers` | |
| 4 | Average order value | Card | `Window Average Order Value` | |
| 5 | Repeat customer rate | Card | `Window Repeat Customer Rate` | |
| 6 | Revenue per customer | Card | `Window Revenue per Customer` | |
| 7 | Monthly revenue trend | Line chart | Axis `monthly_revenue[month_start]`, values `Monthly Net Revenue` | Markers on, legend off |
| 8 | Orders per month | Column chart | Axis `monthly_revenue[month_start]`, values `Monthly Orders` | |
| 9 | Revenue by category | Bar chart | Axis `category_performance[category]`, values `Category Revenue` | Sort descending, data labels on |
| 10 | Revenue by segment | Bar chart | Axis `customer_segments[rfm_segment]`, values `Segment Revenue` | Exclude the never-purchased row |
| 11 | Revenue by country | Bar chart, top 10 | Axis `country_performance[country_code]`, values `country_performance[revenue]` | Top N = 10 by revenue |
| 12 | Campaign lift | Bar chart | Axis `campaign_results[campaign_id]`, values `campaign_results[absolute_difference]` | Dark = statistically significant |
| 13 | Campaign summary table | Table | `campaign_id`, `treatment_n`, `control_n`, `absolute_difference`, `relative_difference`, `adjusted_p_value`, `statistically_significant` | Sort by absolute lift |

Slicers (one row, top right): `monthly_revenue[year_month]`, `country_performance[country_code]`,
`category_performance[category]`, `customer_segments[rfm_segment]`, `campaign_results[campaign_id]`.

Keep cards 1-6 outside slicer interaction (Format -> Edit interactions -> None) so the executive
header always shows the published window values.

---

## Page 2 - Customer analytics

| # | Visual | Type | Fields | Notes |
| --- | --- | --- | --- | --- |
| 1 | Customers by RFM segment | Bar chart | Axis `customer_segments[rfm_segment]`, values `customer_segments[customers]` | Includes never-purchased |
| 2 | Revenue by RFM segment | Bar chart | Axis `customer_segments[rfm_segment]`, values `Segment Revenue` | Data labels with share |
| 3 | Revenue share by decile | Column chart | Axis `customer_value_deciles[revenue_decile]`, values `customer_value_deciles[revenue_share_pct]` | Decile 1 = lowest spend |
| 4 | Cohort retention heatmap | Matrix | Rows `cohort_retention[cohort_month]`, columns `cohort_retention[month_offset]`, values `cohort_retention[retention_rate]` | Conditional formatting: background colour, min 0, max 1 |
| 5 | Cohort sizes | Column chart | Axis `cohort_sizes[cohort_month]`, values `cohort_sizes[cohort_size]` | |
| 6 | Concentration | Cards | `Top 10% Revenue Share`, `Bottom 50% Revenue Share` | |

Annotation text box under the matrix: "Month 0 is the acquisition month by definition. The 2024-10
cohort is left-censored (customers already active before the window) and should be excluded from
retention benchmarks."

Slicers: `customer_segments[rfm_segment]`, `country_performance[country_code]`,
`cohort_retention[cohort_month]`.

---

## Page 3 - Product analytics

| # | Visual | Type | Fields | Notes |
| --- | --- | --- | --- | --- |
| 1 | Revenue by category | Bar chart | Axis `category_performance[category]`, values `Category Revenue` | |
| 2 | Units by category | Bar chart | Axis `category_performance[category]`, values `Category Units` | |
| 3 | Category table | Table | `category`, `revenue`, `units`, `orders`, `customers`, `average_selling_price`, `revenue_share_pct` | Data bars on revenue |
| 4 | Top 10 products | Bar chart | Axis `product_performance[product_name]`, values `Product Revenue` | Top N = 10 by revenue |
| 5 | Product detail | Table | `product_id`, `product_name`, `category`, `revenue`, `units`, `orders`, `customers`, `average_selling_price` | Sort by revenue |
| 6 | Declining products | Bar chart | Axis `declining_products[product_name]`, values `declining_products[units_change_pct]` | Filter `is_declining = TRUE`, top 10 by absolute change |
| 7 | Decline indicator | Card | `Declining Products Flagged` | Subtitle: "prior units >= 10 and unit change <= -30%" |

Slicers: `category_performance[category]`, `product_performance[brand]`, `monthly_revenue[year_month]`.

---

## Page 4 - Campaign analytics

| # | Visual | Type | Fields | Notes |
| --- | --- | --- | --- | --- |
| 1 | Relative lift | Bar chart | Axis `campaign_results[campaign_id]`, values `campaign_results[relative_difference]` | Dark = significant; constant line at 10% |
| 2 | Lift with 95% CI | Table with data bars, or the preview image | `campaign_id`, `absolute_difference`, `confidence_interval_low`, `confidence_interval_high` | Power BI has no native forest plot |
| 3 | Evidence vs lift | Scatter | X `relative_difference`, Y `adjusted_p_value` (log axis), details `campaign_id` | Constant lines at 10% and 0.05 |
| 4 | Campaign results table | Table | `campaign_id`, `campaign_name`, `treatment_n`, `control_n`, `treatment_mean`, `control_mean`, `absolute_difference`, `relative_difference`, `confidence_interval_low`, `confidence_interval_high`, `p_value`, `adjusted_p_value`, `effect_size`, `effect_size_label`, `statistically_significant`, `practically_significant` | Conditional icon on significance |
| 5 | Interpretation | Card | `Campaign Interpretation` | Updates with the selected campaign |
| 6 | Significance | Cards | `Campaigns Tested`, `Significant Campaigns`, `Practically Significant Campaigns` | |

Slicers: `campaign_results[campaign_id]`, `campaign_results[objective]`, `campaign_results[channel]`.

Required text box: "The dataset simulates randomised campaign assignment. Real client data often
contains confounding, selection bias, targeting effects and non-random exposure, so these estimates
are not automatically transferable."

---

## Page inventory

| Page | Purpose | Primary question |
| --- | --- | --- |
| 1 | Executive overview | How is the business performing and where does revenue come from? |
| 2 | Customer analytics | Who are the customers that matter, and do cohorts return? |
| 3 | Product analytics | Which categories and products drive revenue, and what is declining? |
| 4 | Campaign analytics | Which campaigns created value, and is the evidence strong enough to act on? |

