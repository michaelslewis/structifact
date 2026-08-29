with

claimant as (
    select *
    from (
        select *,
            row_number() over (
                partition by claim_id
                order by is_current desc, updated_at desc
            ) as rn
        from PARTY_ROLE
        where role_code = 'CLAIMANT'
    ) t
    where rn = 1
),

adjuster as (
    select *
    from (
        select *,
            row_number() over (
                partition by claim_id
                order by is_current desc, updated_at desc
            ) as rn
        from PARTY_ROLE
        where role_code = 'ADJUSTER'
    ) t
    where rn = 1
),

beneficiary as (
    select *
    from (
        select *,
            row_number() over (
                partition by claim_id
                order by is_current desc, updated_at desc
            ) as rn
        from PARTY_ROLE
        where role_code = 'BENEFICIARY'
    ) t
    where rn = 1
),

policy_status as (
    select *
    from POLICY_STATUS_HISTORY
),

final as (

    select
        CLAIM_HDR.claim_id as claim_id,
        CLAIM_HDR.policy_id as policy_id,
        CLAIM_HDR.claim_date as claim_date,
        CLAIM_HDR.claim_type as claim_type,
        CLAIM_HDR.status_code as status_code,
        CLAIM_HDR.claim_amount as claim_amount,
        sum of all CLAIM_PAYMENT rows for this claim as total_paid_amount,
        claim_amount - total_paid_amount as net_exposure,
        claimant.claimant_name as claimant_name,
        adjuster.adjuster_name as adjuster_name,
        adjuster.adjuster_email as adjuster_email,
        beneficiary.beneficiary_name as beneficiary_name,
        policy_status.policy_status_as_of_claim as policy_status_as_of_claim

    from CLAIM_HDR
    left join claimant
        on CLAIM_HDR.claim_id = claimant.claim_id
    left join adjuster
        on CLAIM_HDR.claim_id = adjuster.claim_id
    left join beneficiary
        on CLAIM_HDR.claim_id = beneficiary.claim_id
    left join policy_status
        on CLAIM_HDR.policy_id = policy_status.policy_id and policy_status.effective_date <= CLAIM_HDR.claim_date

)

select * from final;