-- Schema layout for the NovaCart analytics platform.
--
-- raw        : source-shaped tables loaded from the synthetic generator (no business logic applied)
-- analytics  : staging views, RFM/cohort/mart tables built on top of raw (later milestones)
-- meta       : ingestion and data-quality bookkeeping

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS meta;

COMMENT ON SCHEMA raw IS 'Source-shaped e-commerce tables as delivered by the synthetic source system.';
COMMENT ON SCHEMA analytics IS 'Analytical layer: cleaned views, customer features, RFM, cohorts and reporting marts.';
COMMENT ON SCHEMA meta IS 'Operational metadata: ingestion runs and data-quality results.';

