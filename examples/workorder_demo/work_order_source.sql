-- work_order_source.sql (SYNTHETIC EXAMPLE — fictional company/data)
--
-- Built from REQUIREMENTS_workorder.md in this same folder. This
-- represents what a human data engineer builds by hand today —
-- Structifact cannot generate this yet. It exists to test how close
-- discover --requirements --ai gets on a document with two patterns
-- the wholesale-coffee example never exercised: the same source
-- table joined multiple times under different roles, and priority-
-- based deduplication (not just uniqueness).

{{ config(schema="DEMO") }}

with

wo_hdr as ( select * from {{ source('src', 'wo_hdr') }} ),

wo_line as ( select * from {{ source('src', 'wo_line') }} ),

cust_mst as ( select * from {{ source('src', 'cust_mst') }} ),

price_cond as ( select * from {{ source('src', 'price_cond') }} ),

fx as ( select * from {{ ref('int_fx_rate_lookup') }} ),

-- PARTNER_ROLE joined three times under three different roles — the
-- self-join/multi-role pattern from the real example (vbpa_shipped_to
-- / vbpa_sold_to / vbpa_payer / etc. joined off one shared table).
-- Each also applies the priority/tiebreak dedup rule: prefer
-- is_current = 'Y'; if none is current, fall back to the most
-- recently updated row.

partner_requested_by as (
    select *
    from (
        select *,
            row_number() over (
                partition by wo_id
                order by
                    case when is_current = 'Y' then 0 else 1 end,
                    updated_at desc
            ) as rn
        from {{ source('src', 'partner_role') }}
        where role_code = 'REQ'
    ) t
    where rn = 1
),

partner_billed_to as (
    select *
    from (
        select *,
            row_number() over (
                partition by wo_id
                order by
                    case when is_current = 'Y' then 0 else 1 end,
                    updated_at desc
            ) as rn
        from {{ source('src', 'partner_role') }}
        where role_code = 'BILL'
    ) t
    where rn = 1
),

partner_site_contact as (
    select *
    from (
        select *,
            row_number() over (
                partition by wo_id
                order by
                    case when is_current = 'Y' then 0 else 1 end,
                    updated_at desc
            ) as rn
        from {{ source('src', 'partner_role') }}
        where role_code = 'SITE'
    ) t
    where rn = 1
),

final as (

    select

        wo_hdr.wo_id              as src_wo_hdr_wo_id,
        wo_hdr.wo_date            as src_wo_hdr_wo_date,
        wo_hdr.currency_code      as src_wo_hdr_currency_code,
        wo_hdr.wo_type            as src_wo_hdr_wo_type,

        case
            when wo_hdr.wo_type in ('CRM', 'RET') then -1
            else 1
        end as sign_adjustment,

        wo_line.line_id           as src_wo_line_line_id,
        wo_line.labor_hours       as src_wo_line_labor_hours,
        wo_line.rate_code         as src_wo_line_rate_code,

        price_cond.labor_rate     as src_price_cond_labor_rate,

        (wo_line.labor_hours * price_cond.labor_rate * sign_adjustment)
            as labor_amount_lc,

        cust_mst.customer_name    as src_cust_mst_customer_name,
        cust_mst.region_code      as src_cust_mst_region_code,

        partner_requested_by.contact_name as src_partner_requested_by_name,
        partner_billed_to.contact_name    as src_partner_billed_to_name,
        partner_site_contact.contact_name as src_partner_site_contact_name,
        partner_site_contact.contact_phone as src_partner_site_contact_phone,

        -- FX rate resolution: fall back to 1.0 only for USD orders
        -- with no matching lookup row; otherwise leave null.
        coalesce(
            fx.rate_to_usd,
            case when wo_hdr.currency_code = 'USD' then 1.0 end
        ) as resolved_fx_rate,

        (wo_line.labor_hours * price_cond.labor_rate * sign_adjustment)
            * coalesce(
                fx.rate_to_usd,
                case when wo_hdr.currency_code = 'USD' then 1.0 end
            ) as labor_amount_usd

    from wo_hdr
    left join wo_line on wo_hdr.wo_id = wo_line.wo_id
    left join cust_mst on wo_hdr.customer_id = cust_mst.customer_id
    left join price_cond on wo_line.rate_code = price_cond.rate_code
    left join partner_requested_by on wo_hdr.wo_id = partner_requested_by.wo_id
    left join partner_billed_to on wo_hdr.wo_id = partner_billed_to.wo_id
    left join partner_site_contact on wo_hdr.wo_id = partner_site_contact.wo_id
    left join fx
        on wo_hdr.currency_code = fx.currency_code
        and wo_hdr.wo_date = fx.rate_date

)

select * from final
