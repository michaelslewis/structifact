with

wo_line as (
    select *
    from WO_LINE
),

customer as (
    select *
    from CUST_MST
),

price_condition as (
    select *
    from PRICE_COND
),

requested_by_contact as (
    select *
    from (
        select *,
            row_number() over (
                partition by wo_id
                order by is_current desc, updated_at desc
            ) as rn
        from PARTNER_ROLE
        where role_code = 'REQ'
    ) t
    where rn = 1
),

billed_to_contact as (
    select *
    from (
        select *,
            row_number() over (
                partition by wo_id
                order by is_current desc, updated_at desc
            ) as rn
        from PARTNER_ROLE
        where role_code = 'BILL'
    ) t
    where rn = 1
),

site_contact as (
    select *
    from (
        select *,
            row_number() over (
                partition by wo_id
                order by is_current desc, updated_at desc
            ) as rn
        from PARTNER_ROLE
        where role_code = 'SITE'
    ) t
    where rn = 1
),

fx_rate as (
    select *
    from fx_rate_lookup
),

final as (

    select
        WO_HDR.src_wo_hdr_wo_id as wo_id,
        WO_HDR.src_wo_hdr_wo_date as wo_date,
        WO_HDR.src_wo_hdr_currency_code as currency_code,
        WO_HDR.src_wo_hdr_wo_type as wo_type,
        if src_wo_hdr_wo_type in ('CRM','RET') then -1 else 1 as sign_adjustment,
        wo_line.src_wo_line_line_id as line_id,
        wo_line.src_wo_line_labor_hours as labor_hours,
        wo_line.src_wo_line_rate_code as rate_code,
        price_condition.src_price_cond_labor_rate as labor_rate,
        src_wo_line_labor_hours * src_price_cond_labor_rate * sign_adjustment as labor_amount_lc,
        labor_amount_lc * resolved_fx_rate as labor_amount_usd,
        customer.src_cust_mst_customer_name as customer_name,
        customer.src_cust_mst_region_code as region_code,
        requested_by_contact.src_partner_requested_by_name as requested_by_name,
        billed_to_contact.src_partner_billed_to_name as billed_to_name,
        site_contact.src_partner_site_contact_name as site_contact_name,
        site_contact.src_partner_site_contact_phone as site_contact_phone

    from WO_HDR
    left join wo_line
        on WO_HDR.wo_id = wo_line.wo_id
    left join customer
        on WO_HDR.customer_id = customer.customer_id
    left join price_condition
        on wo_line.rate_code = price_condition.rate_code
    left join requested_by_contact
        on WO_HDR.wo_id = requested_by_contact.wo_id
    left join billed_to_contact
        on WO_HDR.wo_id = billed_to_contact.wo_id
    left join site_contact
        on WO_HDR.wo_id = site_contact.wo_id
    left join fx_rate
        on WO_HDR.currency_code = fx_rate.currency_code and WO_HDR.wo_date = fx_rate.rate_date

)

select * from final;