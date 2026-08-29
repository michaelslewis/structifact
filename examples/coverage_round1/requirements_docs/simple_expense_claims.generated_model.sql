select
    employee_expense_claims.claim_id as claim_id,
    employee_expense_claims.employee_id as employee_id,
    employee_expense_claims.employee_name as employee_name,
    employee_expense_claims.department as department,
    employee_expense_claims.category as category,
    employee_expense_claims.expense_date as expense_date,
    employee_expense_claims.submitted_date as submitted_date,
    employee_expense_claims.approved_date as approved_date,
    employee_expense_claims.approved_flag as approved_flag,
    employee_expense_claims.amount_usd as amount_usd,
    if approved_flag = 'Y', the reimbursable amount is the full claimed amount_usd; otherwise it's 0 as reimbursable_amount,
    for approved claims, the number of days between submitted_date and approved_date as days_to_approval
from employee_expense_claims;