-- Mart: member dimension with plan and county attributes attached.
DROP TABLE IF EXISTS marts.dim_member;
CREATE TABLE marts.dim_member AS
SELECT
    m.member_id,
    m.enroll_date,
    m.plan_id,
    p.plan_type,
    m.county_fips,
    c.urban_rural,
    m.age,
    m.age_band,
    m.sex,
    m.dual_eligible_flag,
    m.lis_flag,
    m.channel
FROM staging.stg_member m
JOIN staging.stg_plan p   ON p.plan_id = m.plan_id
JOIN staging.stg_county c ON c.county_fips = m.county_fips;
