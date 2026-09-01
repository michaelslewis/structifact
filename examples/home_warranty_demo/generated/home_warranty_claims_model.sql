with

contracts as (
    select *
    from (
        select *,
            row_number() over (
                partition by contract_id
                order by record_entered_date desc
            ) as rn
        from contracts
    ) t
    where rn = 1
),

coverage_rules as (
    select *
    from coverage_rules
),

contractor_network as (
    select *
    from contractor_network
),

final as (

    select
        claims.claim_id as claim_id,
        claims.contractor_id as contractor_id,
        claims.contract_id as contract_id,
        contracts.plan_tier as plan_tier,
        contracts.start_date as effective_date,
        CASE WHEN claims.item_category = 'Water Heater' THEN 'WtrHtr' ELSE claims.item_category END as normalized_item_category,
        claims.claim_date <= effective_date + INTERVAL '30 days' as is_pre_existing_exclusion,
        NOT is_pre_existing_exclusion AND coverage_rules.covered IS NOT NULL AND coverage_rules.covered = TRUE as is_covered,
        COALESCE(coverage_rules.copay_amount, 0) as effective_copay,
        CASE WHEN NOT is_covered THEN 0 ELSE LEAST(GREATEST(claims.claim_amount - effective_copay, 0), COALESCE(coverage_rules.coverage_cap, claims.claim_amount)) * CASE WHEN contractor_network.network_status = 'In-Network' THEN 1.0 ELSE 0.8 END END as reimbursement_amount

    from claims
    left join contracts
        on contracts.contract_id = claims.contract_id
    left join coverage_rules
        on coverage_rules.plan_tier = contracts.plan_tier AND coverage_rules.item_category = (
  CASE WHEN claims.item_category = 'Water Heater' THEN 'WtrHtr'
  ELSE claims.item_category END
)

    left join contractor_network
        on contractor_network.contractor_id = claims.contractor_id

)

select * from final;