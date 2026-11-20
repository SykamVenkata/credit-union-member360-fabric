-- One row per golden member. Survivorship: attributes come from the earliest core record,
-- status is Closed only when every core record is closed.
with ranked as (
    select *,
           row_number() over (partition by golden_id order by join_date, member_id) as rn,
           count(*) over (partition by golden_id) as core_records,
           sum(case when status = 'Active' then 1 else 0 end) over (partition by golden_id) as active_records
    from {{ ref('stg_members') }}
)
select
    golden_id,
    home_branch_id,
    segment,
    join_date as member_since,
    datediff(day, join_date, cast(getdate() as date)) / 365.25 as tenure_years,
    case when active_records > 0 then 'Active' else 'Closed' end as member_status,
    core_records
from ranked
where rn = 1
