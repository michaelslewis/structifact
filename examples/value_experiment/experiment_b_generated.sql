-- ============================================================
-- Generated via: structifact generate -g model <spec>.yml
-- Stage 1/3: order_status_and_revenue_candidates_model.sql
-- ============================================================
with

csh as (
    select *
    from customer_status_history
),

lines as (
    select
        order_id,
        sum(quantity * unit_price) as revenue
    from order_lines
    group by order_id
),

final as (

    select
        orders.order_id as order_id,
        orders.customer_id as customer_id,
        orders.order_date as order_date,
        csh.status as status,
        csh.effective_date as effective_date,
        lines.revenue as revenue

    from orders
    left join csh
        on csh.customer_id = orders.customer_id and csh.effective_date <= orders.order_date
    left join lines
        on lines.order_id = orders.order_id

)

select * from final;

-- ============================================================
-- Stage 2/3: order_status_resolved_model.sql
-- ============================================================
with

candidates as (
    select *
    from (
        select *,
            row_number() over (
                partition by order_id
                order by effective_date desc
            ) as rn
        from order_status_and_revenue_candidates
    ) t
    where rn = 1
),

final as (

    select
        candidates.order_id as order_id,
        candidates.customer_id as customer_id,
        candidates.order_date as order_date,
        candidates.status as status,
        candidates.revenue as revenue

    from candidates


)

select * from final;

-- ============================================================
-- Stage 3/3: order_status_revenue_summary_model.sql
-- ============================================================
with

resolved as (
    select
        status,
        sum(revenue) as total_revenue,
        count(*) as order_count
    from order_status_resolved
    group by status
),

final as (

    select
        resolved.status as status,
        resolved.total_revenue as total_revenue,
        resolved.order_count as order_count

    from resolved


)

select * from final;