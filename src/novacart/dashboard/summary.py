"""Executive summary generation (Milestone 5, part D).

The summary is generated from the canonical analytical outputs; every number in
the prose is injected from a computed value, so the document cannot drift from
the data and no result is fabricated.

Outputs
    * ``executive_summary.md``  - Markdown for the repository / review
    * ``executive_summary.html`` - self-contained HTML (print/PDF ready)
    * ``executive_summary.xlsx`` - workbook with KPI, recommendation and data sheets
      (optional: skipped with a message when XlsxWriter is unavailable)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from html import escape
from pathlib import Path

import pandas as pd

from novacart.analytics.common import (
    format_compact_currency,
    format_count,
    format_currency,
    format_percent,
)
from novacart.analytics.report import BusinessAnalysis
from novacart.dashboard.exports import DASHBOARD_DIR

logger = logging.getLogger(__name__)

SUMMARY_DIR_NAME = "summary"
RECENT_WINDOW_MONTHS = 12


@dataclass(frozen=True)
class ExecutiveSummary:
    """Generated summary plus the measured values it quotes."""

    metrics: dict[str, object]
    recommendations: tuple[str, ...]
    markdown: str
    html: str


def _revenue_trend(monthly: pd.DataFrame) -> dict[str, object]:
    frame = monthly.sort_values("month_start").reset_index(drop=True)
    if len(frame) >= 2 * RECENT_WINDOW_MONTHS:
        recent = frame.tail(RECENT_WINDOW_MONTHS)
        previous = frame.iloc[-2 * RECENT_WINDOW_MONTHS : -RECENT_WINDOW_MONTHS]
        comparison_label = f"the preceding {RECENT_WINDOW_MONTHS} months"
    else:
        midpoint = max(1, len(frame) // 2)
        previous = frame.iloc[:midpoint]
        recent = frame.iloc[midpoint:]
        comparison_label = "the first half of the window"

    recent_revenue = float(recent["revenue"].sum())
    previous_revenue = float(previous["revenue"].sum())
    growth = (
        (recent_revenue - previous_revenue) / previous_revenue if previous_revenue else float("nan")
    )
    peak = frame.loc[frame["revenue"].idxmax()]

    return {
        "recent_months": len(recent),
        "recent_revenue": recent_revenue,
        "previous_revenue": previous_revenue,
        "comparison_label": comparison_label,
        "growth_pct": growth,
        "peak_month": str(peak["year_month"]),
        "peak_month_revenue": float(peak["revenue"]),
        "first_month": str(frame.iloc[0]["year_month"]),
        "first_month_revenue": float(frame.iloc[0]["revenue"]),
        "last_month": str(frame.iloc[-1]["year_month"]),
        "last_month_revenue": float(frame.iloc[-1]["revenue"]),
        "last_month_revenue_mom_pct": float(frame.iloc[-1]["revenue_mom_pct"])
        if pd.notna(frame.iloc[-1]["revenue_mom_pct"])
        else float("nan"),
    }


def _customer_findings(analysis: BusinessAnalysis) -> dict[str, object]:
    segments = analysis.rfm_segments
    champions = segments.loc[segments["rfm_segment"] == "Champions"]
    at_risk = segments.loc[segments["rfm_segment"] == "At Risk"]
    never = segments.loc[segments["rfm_segment"] == "Never Purchased"]

    concentration = analysis.concentration.iloc[0] if not analysis.concentration.empty else None
    retention = analysis.cohorts.retention
    clean = retention.loc[retention["cohort_index"] > 0]
    median_month_one = clean.loc[clean["month_offset"] == 1, "retention_rate"].median()
    first_cohort = retention.loc[
        (retention["cohort_index"] == 0) & (retention["month_offset"] == 1), "retention_rate"
    ]

    return {
        "champions_customers": int(champions["customers"].iloc[0]) if not champions.empty else 0,
        "champions_revenue": float(champions["revenue"].iloc[0]) if not champions.empty else 0.0,
        "champions_revenue_share": float(champions["revenue_share_pct"].iloc[0])
        if not champions.empty
        else 0.0,
        "champions_customer_share": float(champions["customer_share_pct"].iloc[0])
        if not champions.empty
        else 0.0,
        "at_risk_customers": int(at_risk["customers"].iloc[0]) if not at_risk.empty else 0,
        "at_risk_revenue": float(at_risk["revenue"].iloc[0]) if not at_risk.empty else 0.0,
        "never_purchased_customers": int(never["customers"].iloc[0]) if not never.empty else 0,
        "never_purchased_share": float(never["customer_share_pct"].iloc[0])
        if not never.empty
        else 0.0,
        "top_10pct_revenue_share": float(concentration["top_10pct_revenue_share_pct"])
        if concentration is not None
        else float("nan"),
        "bottom_50pct_revenue_share": float(concentration["bottom_50pct_revenue_share_pct"])
        if concentration is not None
        else float("nan"),
        "cohort_count": len(analysis.cohorts.sizes),
        "median_month_one_retention": float(median_month_one)
        if pd.notna(median_month_one)
        else float("nan"),
        "first_cohort_month_one_retention": float(first_cohort.iloc[0])
        if not first_cohort.empty
        else float("nan"),
    }


def _product_findings(analysis: BusinessAnalysis) -> dict[str, object]:
    categories = analysis.categories.sort_values("revenue", ascending=False)
    products = analysis.products
    top_product = products.sort_values("revenue", ascending=False).iloc[0]

    declining = analysis.declining_products
    flagged = declining.loc[declining["is_declining"]].sort_values("units_change")

    return {
        "top_category": str(categories.iloc[0]["category"]),
        "top_category_revenue": float(categories.iloc[0]["revenue"]),
        "top_category_share": float(categories.iloc[0]["revenue_share_pct"]),
        "second_category": str(categories.iloc[1]["category"]) if len(categories) > 1 else "",
        "second_category_share": float(categories.iloc[1]["revenue_share_pct"])
        if len(categories) > 1
        else float("nan"),
        "top_product": str(top_product["product_name"]),
        "top_product_revenue": float(top_product["revenue"]),
        "declining_compared": len(declining),
        "declining_flagged": len(flagged),
        "worst_declining_product": str(flagged.iloc[0]["product_name"]) if not flagged.empty else "",
        "worst_declining_units_pct": float(flagged.iloc[0]["units_change_pct"])
        if not flagged.empty
        else float("nan"),
    }


def _campaign_findings(analysis: BusinessAnalysis) -> dict[str, object]:
    statistics = analysis.campaign_statistics
    significant = statistics.loc[statistics["statistically_significant"]].sort_values(
        "absolute_difference", ascending=False
    )
    practical_only = statistics.loc[
        statistics["practically_significant"] & ~statistics["statistically_significant"]
    ]
    no_effect = statistics.loc[
        ~statistics["statistically_significant"] & ~statistics["practically_significant"]
    ]
    best = significant.iloc[0] if not significant.empty else None

    return {
        "campaigns_tested": len(statistics),
        "significant_campaigns": len(significant),
        "practical_campaigns": int(statistics["practically_significant"].sum()),
        "inconclusive_campaigns": len(practical_only),
        "no_detectable_effect_campaigns": len(no_effect),
        "best_campaign_id": str(best["campaign_id"]) if best is not None else "",
        "best_campaign_name": str(best["campaign_name"]) if best is not None else "",
        "best_campaign_absolute": float(best["absolute_difference"]) if best is not None else float("nan"),
        "best_campaign_relative": float(best["relative_difference"]) if best is not None else float("nan"),
        "best_campaign_ci_low": float(best["confidence_interval_low"]) if best is not None else float("nan"),
        "best_campaign_ci_high": float(best["confidence_interval_high"]) if best is not None else float("nan"),
        "top_campaigns": [
            {
                "campaign_id": str(row.campaign_id),
                "relative_difference": float(row.relative_difference),
                "absolute_difference": float(row.absolute_difference),
                "adjusted_p_value": float(row.adjusted_p_value),
            }
            for row in significant.head(3).itertuples()
        ],
    }


def _recommendations(metrics: dict[str, object]) -> tuple[str, ...]:
    revenue = metrics["revenue"]
    customers = metrics["customers"]
    products = metrics["products"]
    campaigns = metrics["campaigns"]
    kpis = metrics["kpis"]

    growth = float(revenue["growth_pct"])
    trend_direction = "grown" if growth >= 0 else "declined"
    recommendations = [
        (
            f"Keep the growth engine running: revenue across the last "
            f"{revenue['recent_months']} months was {format_compact_currency(revenue['recent_revenue'])}, "
            f"{format_percent(abs(growth))} {'higher' if growth >= 0 else 'lower'} than "
            f"{revenue['comparison_label']} "
            f"({format_compact_currency(revenue['previous_revenue'])}). Revenue has {trend_direction} "
            f"over the comparison period; the {revenue['peak_month']} peak "
            f"({format_compact_currency(revenue['peak_month_revenue'])}) confirms the seasonal "
            "concentration, so plan inventory, staffing and paid media around it."
        ),
        (
            f"Protect the {format_count(customers['champions_customers'])} Champions: they are "
            f"{format_percent(customers['champions_customer_share'] / 100)} of registered customers "
            f"but {format_percent(customers['champions_revenue_share'] / 100)} of revenue "
            f"({format_compact_currency(customers['champions_revenue'])}). Any retention or service "
            "regression in this group is a direct revenue event, so give them priority support, "
            "early access and a named owner of their experience."
        ),
        (
            f"Win back the {format_count(customers['at_risk_customers'])} At Risk customers "
            f"({format_compact_currency(customers['at_risk_revenue'])} of historical revenue): they "
            "were frequent buyers who have gone quiet, which makes them the highest-probability "
            "reactivation target. Measure the win-back campaign against a holdout group, as this "
            "analysis does for acquisition campaigns."
        ),
        (
            f"Scale what is proven and stop paying for noise: {campaigns['significant_campaigns']} of "
            f"{campaigns['campaigns_tested']} campaigns show a statistically significant lift at a 5% "
            f"false-discovery rate"
            + (
                f", led by {campaigns['best_campaign_id']} "
                f"({format_percent(campaigns['best_campaign_relative'])} / "
                f"{format_currency(campaigns['best_campaign_absolute'])} per assigned customer, "
                f"95% CI {format_currency(campaigns['best_campaign_ci_low'])} to "
                f"{format_currency(campaigns['best_campaign_ci_high'])})"
                if campaigns["best_campaign_id"]
                else ""
            )
            + f", while {campaigns['no_detectable_effect_campaigns']} show no detectable difference "
            "and can be paused or redesigned. Reallocate that budget to the proven creatives and "
            "audiences first."
        ),
        (
            f"Treat {campaigns['inconclusive_campaigns']} campaigns as undecided rather than "
            "successful: their point estimates clear the practical thresholds but their confidence "
            "intervals cross zero. Re-run them with a larger holdout or a longer window before "
            "committing budget."
        ),
        (
            f"Defend the product portfolio: {products['top_category']} is the largest category at "
            f"{format_percent(products['top_category_share'] / 100)} of revenue and "
            f"{products['top_product']} is the single largest product "
            f"({format_compact_currency(products['top_product_revenue'])}). At the same time "
            f"{products['declining_flagged']} products met the decline rule"
            + (
                f", the steepest being {products['worst_declining_product']} "
                f"({format_percent(products['worst_declining_units_pct'])})"
                if products["worst_declining_product"]
                else ""
            )
            + "; review pricing, stock cover and whether to replace them."
        ),
        (
            f"Keep the measurement standard: the window contains "
            f"{format_count(int(kpis['registered_customers']))} registered customers of whom "
            f"{format_count(int(kpis['unique_customers']))} purchased, and "
            f"{format_percent(customers['top_10pct_revenue_share'] / 100)} of revenue comes from the "
            "top 10% of buyers. Continue using randomised holdouts and pre-registered tests so "
            "campaign decisions stay evidence-based."
        ),
    ]
    return tuple(recommendations)


def build_executive_summary(analysis: BusinessAnalysis) -> ExecutiveSummary:
    """Generate the executive summary from canonical analytical outputs."""
    kpis = analysis.kpis.iloc[0]
    metrics: dict[str, object] = {
        "kpis": {column: kpis[column] for column in analysis.kpis.columns},
        "revenue": _revenue_trend(analysis.monthly),
        "customers": _customer_findings(analysis),
        "products": _product_findings(analysis),
        "campaigns": _campaign_findings(analysis),
    }
    recommendations = _recommendations(metrics)
    markdown = _render_markdown(metrics, recommendations)
    html = _render_html(metrics, recommendations)
    return ExecutiveSummary(
        metrics=metrics, recommendations=recommendations, markdown=markdown, html=html
    )


def _kpi_rows(metrics: dict[str, object]) -> list[tuple[str, str]]:
    kpis = metrics["kpis"]
    return [
        ("Analysis window", f"{kpis['period_start']} to {kpis['period_end']}"),
        ("Total net revenue", format_compact_currency(kpis["total_revenue"])),
        ("Orders (completed)", format_count(kpis["total_orders"])),
        ("Units sold", format_count(kpis["total_units"])),
        ("Purchasing customers", format_count(kpis["unique_customers"])),
        ("Registered customers", format_count(kpis["registered_customers"])),
        ("Average order value", format_currency(kpis["average_order_value"])),
        ("Revenue per purchasing customer", format_currency(kpis["revenue_per_customer"])),
        (
            "Revenue per registered customer",
            format_currency(kpis["revenue_per_registered_customer"]),
        ),
        ("Repeat customer rate", format_percent(kpis["repeat_customer_rate"])),
    ]


def _render_markdown(metrics: dict[str, object], recommendations: tuple[str, ...]) -> str:
    revenue = metrics["revenue"]
    customers = metrics["customers"]
    products = metrics["products"]
    campaigns = metrics["campaigns"]

    lines: list[str] = [
        "# NovaCart - executive summary",
        "",
        (
            "_Generated from the canonical analytical layer. Every figure below is produced by "
            "`scripts/build_dashboard.py`; none is written by hand._"
        ),
        "",
        "## 1. Executive KPIs",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    lines += [f"| {label} | {value} |" for label, value in _kpi_rows(metrics)]

    lines += [
        "",
        "## 2. Revenue trend",
        "",
        (
            f"* Revenue over the last {revenue['recent_months']} months: "
            f"**{format_compact_currency(revenue['recent_revenue'])}**, "
            f"{format_percent(abs(float(revenue['growth_pct'])))} "
            f"{'above' if float(revenue['growth_pct']) >= 0 else 'below'} "
            f"{revenue['comparison_label']} "
            f"({format_compact_currency(revenue['previous_revenue'])})."
        ),
        (
            f"* Strongest month: **{revenue['peak_month']}** at "
            f"{format_compact_currency(revenue['peak_month_revenue'])}."
        ),
        (
            f"* Most recent month ({revenue['last_month']}): "
            f"{format_compact_currency(revenue['last_month_revenue'])}"
            + (
                f", {format_percent(revenue['last_month_revenue_mom_pct'])} month over month."
                if pd.notna(revenue["last_month_revenue_mom_pct"])
                else "."
            )
        ),
        "",
        "## 3. Customer behaviour",
        "",
        (
            f"* Champions: {format_count(customers['champions_customers'])} customers "
            f"({format_percent(customers['champions_customer_share'] / 100)} of registered "
            f"customers) generating "
            f"{format_percent(customers['champions_revenue_share'] / 100)} of revenue."
        ),
        (
            f"* At Risk: {format_count(customers['at_risk_customers'])} customers representing "
            f"{format_compact_currency(customers['at_risk_revenue'])} of historical revenue."
        ),
        (
            f"* Never purchased: {format_count(customers['never_purchased_customers'])} customers "
            f"({format_percent(customers['never_purchased_share'] / 100)} of registrations)."
        ),
        (
            f"* Revenue concentration: the top 10% of purchasing customers hold "
            f"{format_percent(customers['top_10pct_revenue_share'] / 100)} of revenue; the bottom "
            f"half hold {format_percent(customers['bottom_50pct_revenue_share'] / 100)}."
        ),
        (
            f"* Cohort retention: {customers['cohort_count']} monthly cohorts, median month-1 "
            f"activity retention {format_percent(customers['median_month_one_retention'])} "
            f"(excluding the left-censored first cohort, which shows "
            f"{format_percent(customers['first_cohort_month_one_retention'])})."
        ),
        "",
        "## 4. Product findings",
        "",
        (
            f"* Largest category: **{products['top_category']}** at "
            f"{format_compact_currency(products['top_category_revenue'])} "
            f"({format_percent(products['top_category_share'] / 100)} of revenue)"
            + (
                f", followed by {products['second_category']} "
                f"({format_percent(products['second_category_share'] / 100)})."
                if products["second_category"]
                else "."
            )
        ),
        (
            f"* Largest single product: **{products['top_product']}** at "
            f"{format_compact_currency(products['top_product_revenue'])}."
        ),
        (
            f"* Declining products: {format_count(products['declining_flagged'])} of "
            f"{format_count(products['declining_compared'])} comparable products met the decline "
            "rule (prior units >= 10 and a unit change of -30% or worse)"
            + (
                f"; the steepest is {products['worst_declining_product']} "
                f"({format_percent(products['worst_declining_units_pct'])})."
                if products["worst_declining_product"]
                else "."
            )
        ),
        "",
        "## 5. Campaign findings",
        "",
        f"* {campaigns['campaigns_tested']} campaigns were evaluated with a randomised holdout.",
        (
            f"* {campaigns['significant_campaigns']} show a statistically significant lift at a 5% "
            f"false-discovery rate; {campaigns['practical_campaigns']} also clear the practical "
            "thresholds (>= 10% relative and >= EUR 5 absolute per assigned customer)."
        ),
        (
            f"* {campaigns['inconclusive_campaigns']} campaigns are directionally positive but "
            "statistically inconclusive, and "
            f"{campaigns['no_detectable_effect_campaigns']} show no detectable difference."
        ),
        (
            f"* Largest significant effect: **{campaigns['best_campaign_id']} "
            f"({campaigns['best_campaign_name']})** at "
            f"{format_percent(campaigns['best_campaign_relative'])} "
            f"({format_currency(campaigns['best_campaign_absolute'])} per assigned customer, "
            f"95% CI {format_currency(campaigns['best_campaign_ci_low'])} to "
            f"{format_currency(campaigns['best_campaign_ci_high'])})."
            if campaigns["best_campaign_id"]
            else "* No campaign reached statistical and practical significance."
        ),
        "",
        "## 6. Data limitations",
        "",
        "* All data is **synthetic**; the analysis demonstrates method, not a client result.",
        (
            "* The dataset simulates randomised campaign assignment, while real client data often "
            "contains confounding, selection bias, targeting effects and non-random exposure. "
            "Campaign effects are therefore not automatically transferable."
        ),
        (
            "* The primary campaign comparison is intention-to-treat and is diluted by "
            "treatment-arm members who were never exposed."
        ),
        (
            "* Cohort retention measures any recognised order in a month; the generated data has "
            "no churn-decay process, so retention is flatter than a real retail cohort."
        ),
        (
            "* The first cohort (2024-10) is left-censored - it contains customers who were "
            "already active before the window - and should be excluded from retention benchmarks."
        ),
        "",
        "## 7. Recommended business actions",
        "",
    ]
    lines += [f"{index}. {text}" for index, text in enumerate(recommendations, start=1)]
    lines.append("")
    return "\n".join(lines)


def _render_html(metrics: dict[str, object], recommendations: tuple[str, ...]) -> str:
    kpi_rows = "".join(
        f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in _kpi_rows(metrics)
    )
    markdown = _render_markdown(metrics, recommendations)
    sections = markdown.split("\n")
    body_parts: list[str] = []
    for line in sections:
        if line.startswith("## "):
            body_parts.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("# "):
            body_parts.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("* "):
            body_parts.append(f"<p class=\"bullet\">{escape(line[2:])}</p>")
        elif line.startswith("1. ") or line[:3] in {f"{i}. " for i in range(1, 10)}:
            body_parts.append(f"<p class=\"action\">{escape(line)}</p>")
        elif line.startswith("|"):
            continue
        elif line.startswith("_"):
            body_parts.append(f"<p class=\"note\">{escape(line.strip('_'))}</p>")
        elif line.strip():
            body_parts.append(f"<p>{escape(line)}</p>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>NovaCart - executive summary</title>
<style>
  body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 2.5rem auto; max-width: 60rem;
         color: #1f2933; line-height: 1.55; }}
  h1 {{ font-size: 1.9rem; margin-bottom: 0.2rem; }}
  h2 {{ font-size: 1.25rem; margin-top: 2rem; border-bottom: 1px solid #d6dbe1; padding-bottom: 0.25rem; }}
  table {{ border-collapse: collapse; margin: 0.75rem 0 1.5rem; width: 100%; }}
  th, td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #e6e9ed; }}
  th {{ width: 45%; color: #4a5568; font-weight: 600; }}
  td {{ font-variant-numeric: tabular-nums; }}
  .note {{ color: #6b7280; font-style: italic; }}
  .bullet {{ margin: 0.3rem 0 0.3rem 1rem; }}
  .action {{ margin: 0.5rem 0 0.5rem 1rem; }}
</style>
</head>
<body>
<h1>NovaCart - executive summary</h1>
<p class="note">Generated from the canonical analytical layer. Every figure is produced by
scripts/build_dashboard.py; none is written by hand.</p>
<h2>1. Executive KPIs</h2>
<table>{kpi_rows}</table>
{''.join(part for part in body_parts if not part.startswith('<h1') and '1. Executive KPIs' not in part)}
</body>
</html>
"""


def _write_excel(summary: ExecutiveSummary, path: Path) -> bool:
    try:
        import xlsxwriter  # noqa: F401
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning("XlsxWriter is not installed; skipping the Excel summary")
        return False

    metrics = summary.metrics
    kpis = metrics["kpis"]
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        kpi_frame = pd.DataFrame(_kpi_rows(metrics), columns=["metric", "value"])
        kpi_frame.to_excel(writer, sheet_name="KPIs", index=False)
        pd.DataFrame({"recommendation": list(summary.recommendations)}).to_excel(
            writer, sheet_name="Recommendations", index=False
        )
        pd.DataFrame([kpis]).to_excel(writer, sheet_name="KPI data", index=False)
        workbook = writer.book
        header = workbook.add_format({"bold": True, "bg_color": "#1f4e79", "font_color": "white"})
        money = workbook.add_format({"num_format": "#,##0.00"})
        for sheet_name in ("KPIs", "Recommendations", "KPI data"):
            worksheet = writer.sheets[sheet_name]
            worksheet.set_column(0, 0, 42)
            worksheet.set_column(1, 1, 32)
            for column_index, column in enumerate(
                {"KPIs": ["metric", "value"], "Recommendations": ["recommendation"], "KPI data": list(kpis)}[
                    sheet_name
                ]
            ):
                worksheet.write(0, column_index, column, header)
            if sheet_name == "KPI data":
                worksheet.set_column(0, len(kpis) - 1, 18, money)
    return True


def write_executive_summary(
    summary: ExecutiveSummary,
    *,
    output_dir: Path | None = None,
    write_excel: bool = True,
) -> dict[str, Path]:
    """Write the Markdown, HTML and (optionally) Excel versions of the summary."""
    target = (output_dir or (DASHBOARD_DIR / SUMMARY_DIR_NAME))
    target.mkdir(parents=True, exist_ok=True)

    paths = {
        "markdown": target / "executive_summary.md",
        "html": target / "executive_summary.html",
    }
    paths["markdown"].write_text(summary.markdown, encoding="utf-8")
    paths["html"].write_text(summary.html, encoding="utf-8")

    if write_excel:
        excel_path = target / "executive_summary.xlsx"
        if _write_excel(summary, excel_path):
            paths["excel"] = excel_path
    return paths

