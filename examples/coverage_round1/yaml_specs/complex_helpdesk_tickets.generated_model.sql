with

reporter_contact as (
    select *
    from (
        select *,
            row_number() over (
                partition by ticket_id
                order by is_active desc, updated_at desc
            ) as rn
        from CONTACT_ROLE
        where role_code = 'REPORTER'
    ) t
    where rn = 1
),

assignee_contact as (
    select *
    from (
        select *,
            row_number() over (
                partition by ticket_id
                order by is_active desc, updated_at desc
            ) as rn
        from CONTACT_ROLE
        where role_code = 'ASSIGNEE'
    ) t
    where rn = 1
),

final as (

    select
        TICKET.ticket_id as ticket_id,
        TICKET.subject as subject,
        TICKET.priority as priority,
        TICKET.opened_at as opened_at,
        TICKET.closed_at as closed_at,
        reporter_contact.contact_name as reporter_name,
        assignee_contact.contact_name as assignee_name,
        date_diff('hour', opened_at, closed_at) as resolution_hours

    from TICKET
    left join reporter_contact
        on TICKET.ticket_id = reporter_contact.ticket_id
    left join assignee_contact
        on TICKET.ticket_id = assignee_contact.ticket_id

)

select * from final;