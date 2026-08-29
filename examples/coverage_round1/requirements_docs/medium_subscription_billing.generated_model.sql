with

customer as (
    select *
    from CUSTOMER
),

plan_catalog as (
    select *
    from PLAN_CATALOG
),

fx_rate as (
    select *
    from FX_RATE
),

final as (

    select
        SUBSCRIPTION.subscription_id as subscription_id,
        SUBSCRIPTION.customer_id as customer_id,
        SUBSCRIPTION.plan_code as plan_code,
        SUBSCRIPTION.start_date as start_date,
        SUBSCRIPTION.status as status,
        SUBSCRIPTION.snapshot_date as snapshot_date,
        snapshot_date - start_date as account_age_days,
        if customer's billing_currency = 'USD' then 1.0 else looked up from FX_RATE by currency_code; if no match and currency is not USD, leave null as resolved_fx_rate,
        plan_catalog.monthly_price_local * resolved_fx_rate as monthly_price_usd,
        customer.customer_name as customer_name,
        customer.region_code as region_code,
        customer.billing_currency as billing_currency,
        plan_catalog.plan_name as plan_name,
        plan_catalog.monthly_price_local as monthly_price_local,
        fx_rate.rate_to_usd as rate_to_usd

    from SUBSCRIPTION
    left join customer
        on SUBSCRIPTION.customer_id = customer.customer_id
    left join plan_catalog
        on SUBSCRIPTION.plan_code = plan_catalog.plan_code
    left join fx_rate
        on customer.billing_currency = fx_rate.currency_code

)

select * from final;