CREATE TABLE home_warranty_claims (
    claim_id TEXT,
    contractor_id TEXT NOT NULL,
    contract_id TEXT,
    plan_tier TEXT,
    effective_date DATE,
    -- computed: normalized_item_category = CASE WHEN claims.item_category = 'Water Heater' THEN 'WtrHtr' ELSE claims.item_category END,
    normalized_item_category TEXT,
    -- computed: is_pre_existing_exclusion = claims.claim_date <= effective_date + INTERVAL '30 days',
    is_pre_existing_exclusion BOOLEAN,
    -- computed: is_covered = NOT is_pre_existing_exclusion AND coverage_rules.covered IS NOT NULL AND coverage_rules.covered = TRUE,
    is_covered BOOLEAN,
    -- computed: effective_copay = COALESCE(coverage_rules.copay_amount, 0),
    effective_copay DECIMAL,
    -- computed: reimbursement_amount = CASE WHEN NOT is_covered THEN 0 ELSE LEAST(GREATEST(claims.claim_amount - effective_copay, 0), COALESCE(coverage_rules.coverage_cap, claims.claim_amount)) * CASE WHEN contractor_network.network_status = 'In-Network' THEN 1.0 ELSE 0.8 END END,
    reimbursement_amount DECIMAL,
    FOREIGN KEY (contractor_id) REFERENCES contractor_network (contractor_id)
);