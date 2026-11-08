-- Staging: plan, county, and date dimensions. Casts only; these feeds are clean.
DROP TABLE IF EXISTS staging.stg_plan;
CREATE TABLE staging.stg_plan AS
SELECT
    plan_id,
    plan_type,
    CAST(monthly_premium AS DECIMAL(8, 2)) AS monthly_premium,
    CAST(star_rating AS DECIMAL(3, 1))     AS star_rating
FROM raw.dim_plan;

DROP TABLE IF EXISTS staging.stg_county;
CREATE TABLE staging.stg_county AS
SELECT county_fips, county_name_synthetic, urban_rural
FROM raw.dim_county
UNION ALL
-- Placeholder row so members with a null county keep referential integrity.
SELECT 'UNKNOWN', 'Unknown county', 'unknown';

DROP TABLE IF EXISTS staging.stg_date;
CREATE TABLE staging.stg_date AS
SELECT
    CAST(date AS DATE)            AS date,
    CAST(year AS INTEGER)         AS year,
    CAST(month AS INTEGER)        AS month,
    CAST(month_start AS DATE)     AS month_start,
    CAST(quarter AS INTEGER)      AS quarter,
    CAST(day_of_week AS INTEGER)  AS day_of_week,
    CAST(is_oep_month AS INTEGER) AS is_oep_month
FROM raw.dim_date;
