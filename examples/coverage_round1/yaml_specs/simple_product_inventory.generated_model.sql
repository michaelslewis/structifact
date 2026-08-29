with

warehouse as (
    select *
    from WAREHOUSE
),

final as (

    select
        PRODUCT_STOCK.sku as sku,
        PRODUCT_STOCK.product_name as product_name,
        PRODUCT_STOCK.warehouse_id as warehouse_id,
        PRODUCT_STOCK.quantity_on_hand as quantity_on_hand,
        PRODUCT_STOCK.unit_cost as unit_cost,
        warehouse.name as warehouse_name,
        warehouse.region_code as region,
        quantity_on_hand * unit_cost as total_value

    from PRODUCT_STOCK
    left join warehouse
        on PRODUCT_STOCK.warehouse_id = warehouse.warehouse_id

)

select * from final;