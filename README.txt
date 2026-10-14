==============================================================================
EMPLOYEE PAYROLL SYSTEM - README
==============================================================================

A Streamlit web application for managing employee payroll records. It lets
you browse employees, add new ones, recalculate monthly salary, view
payslips, search, and save everything to disk.


------------------------------------------------------------------------------
1. QUICK START
------------------------------------------------------------------------------

Requirements:
  - Python 3.9+
  - pandas
  - streamlit

Install and run:
  pip install pandas streamlit
  streamlit run app.py        (use whatever your script file is called)

Required files in the same folder:
  - employee_payroll_400.csv  : seed data (used only on the very first run)
  - payroll_records.pkl       : created automatically; holds saved records

First run:  the app reads the CSV, calculates salary figures for every
            employee, and writes payroll_records.pkl.
Later runs: the app loads payroll_records.pkl directly (the CSV is ignored).

To reset to the original data: delete payroll_records.pkl and restart.


------------------------------------------------------------------------------
2. PROGRAM STRUCTURE AT A GLANCE
------------------------------------------------------------------------------

  Constants (data)         -> column names, dropdown options, field groups
  Helper functions         -> money formatting, tables, flash messages
  AllowanceRatios          -> learns allowance/deduction ratios from data
  SalaryCalculator         -> gross, loss of pay, deductions, net pay
  Person / Employee        -> one person / one payroll record
  PayrollRepository        -> reads and writes the data file
  PayrollService           -> business logic (search, add, calculate)
  ReportSection family     -> on-screen report blocks (tables, payslip)
  Tab functions + main()   -> the Streamlit user interface

Layering: UI functions call PayrollService; PayrollService uses
PayrollRepository (storage), SalaryCalculator (math), AllowanceRatios
(defaults) and Employee (record wrapper).


------------------------------------------------------------------------------
3. CONSTANTS (DATA)
------------------------------------------------------------------------------

DATA_FILE = "payroll_records.pkl"
    Name of the pickle file where payroll records are saved.

SEED_FILE = "employee_payroll_400.csv"
    CSV with the initial 400 employee records.

DEPARTMENTS, DESIGNATIONS, GRADES, EMPLOYMENT_TYPES, PAYMENT_MODES, GENDERS
    Allowed values for the matching dropdowns in the "Add employee" form.
    They are also used to validate input in PayrollService.add_employee().

COLUMNS
    The full, ordered list of 35 columns every payroll record has (ID, name,
    personal info, job info, attendance, earnings, deductions, bank info).
    Used to build DataFrames with a consistent column order.

EARNING_FIELDS
    Columns that add up to gross salary: basic_salary, hra,
    dearness_allowance, special_allowance, transport_allowance,
    incentive_bonus.

DEDUCTION_FIELDS
    Statutory/other deductions that are subtracted from gross: pf_employee,
    esi, professional_tax, income_tax_tds, other_deductions.
    (Loss of pay is calculated separately and is not in this list.)

RATIO_FIELDS
    Fields that are estimated as a fraction of basic salary when a new
    employee is added: hra, dearness_allowance, special_allowance,
    transport_allowance, incentive_bonus, pf_employee, esi,
    professional_tax, income_tax_tds, pf_employer.

SEARCH_FIELDS
    Columns the Search tab looks through: employee_name, employee_id,
    department, designation.

DIRECTORY_COLUMNS
    Columns shown in the employee list and search results tables.


------------------------------------------------------------------------------
4. HELPER FUNCTIONS
------------------------------------------------------------------------------

money(value)
    Formats a number as Indian rupees with thousand separators and no
    decimals, e.g. 45250 -> "₹45,250".

amount_table(rows)
    Takes a list of (label, number) pairs and returns a two-column DataFrame
    ("Component", "Amount") with the amounts formatted by money(). Used for
    the Earnings and Deductions tables on the payslip.

flash(kind, text)
    Stores a one-time message in st.session_state["flash"]. "kind" is a
    Streamlit method name such as "success" or "error". Needed because the
    page reruns after an action and a normal message would disappear.

show_flash()
    Removes the stored flash message (if any) and displays it using the
    matching Streamlit function. Called once at the top of main().


------------------------------------------------------------------------------
5. CLASSES
------------------------------------------------------------------------------

5.1  PayrollError(Exception)
     Custom exception for business-rule violations (empty name, invalid
     choice, negative values, unknown employee ID, etc.). The UI catches it
     and shows the message with st.error().


5.2  AllowanceRatios
     Purpose: when a new employee is added, only basic salary is entered.
     This class estimates all the other pay components by using the average
     ratio of each component to basic salary across existing employees.

     Data:
       _ratios            dict {field name: average ratio to basic salary}

     Methods:
       __init__(ratios)
           Stores a copy of the ratio dictionary.
       from_frame(frame)             [classmethod]
           Builds an AllowanceRatios object from a DataFrame. Ignores rows
           with basic salary <= 0, divides each RATIO_FIELDS column by basic
           salary, and takes the mean.
       amount(field, basic)
           Returns the estimated whole-number amount for a field, given a
           basic salary (basic x stored ratio, rounded).


5.3  SalaryCalculator
     Purpose: all salary arithmetic in one place. Holds no data.

     Methods:
       gross(record)
           Sum of all EARNING_FIELDS in the record.
       loss_of_pay_amount(gross, working_days, loss_of_pay_days)
           Pay cut for unpaid days:
           gross x loss_of_pay_days / working_days (rounded).
           Returns 0 if working_days <= 0.
       calculate(record)
           Returns a dict with four computed values:
             gross_salary       = sum of earnings
             loss_of_pay_amount = as above
             total_deductions   = loss of pay + sum of DEDUCTION_FIELDS
             net_salary         = gross_salary - total_deductions

     Formula summary:
       Gross  = basic + HRA + DA + special + transport + incentive
       Net    = Gross - (Loss of pay + PF + ESI + Prof. tax + TDS + Other)


5.4  Person
     Purpose: base class holding basic personal details.

     Data (private, read through properties):
       _name, _gender, _date_of_birth

     Methods / properties:
       name, gender, date_of_birth   Read-only properties.
       describe()                    Returns the person's name.


5.5  Employee(Person)
     Purpose: wraps one payroll record (a dict of column -> value) and adds
     employee-specific behaviour. Inherits name, gender and date of birth
     from Person.

     Data:
       _record            private copy of the full payroll record dict

     Methods / properties:
       __init__(record)
           Passes name, gender and date of birth to Person and stores a copy
           of the record.
       record                (property)
           Returns a copy of the record, so outside code cannot change it
           by accident.
       employee_id           (property)
           Returns the employee ID.
       get(field)
           Returns the value of one field.
       update(figures)
           Merges a dict of new values into the record.
       masked_account()
           Returns the bank account number with all but the last 4 digits
           replaced by "*" (e.g. "********1234"). Used everywhere the
           account is displayed, for privacy.
       describe()            (overrides Person.describe)
           Returns "EMP101 - Name".


5.6  PayrollRepository
     Purpose: the storage layer. Only this class touches the files.

     Data:
       _data_file         path to the pickle file
       _seed_file         path to the starting CSV

     Methods:
       __init__(data_file, seed_file)
           Stores both paths (defaults are DATA_FILE and SEED_FILE).
       load(calculator)
           Tries to read the pickle. If it does not exist, builds the data
           from the CSV (via _seed), saves it, and returns it.
       save(frame)
           Writes the DataFrame to the pickle file.
       _seed(calculator)
           Reads the CSV (PAN, UAN and bank account kept as text so leading
           zeros are not lost), inserts a loss_of_pay_amount column,
           calculates gross, loss of pay, total deductions and net salary for
           every row, and returns a DataFrame in COLUMNS order.

     Note: pickle files can run code when loaded. Only load a
     payroll_records.pkl that you created yourself.


5.7  PayrollService
     Purpose: the main business-logic class. It keeps the whole dataset in
     memory and provides every operation the UI needs.

     Data:
       _repository        PayrollRepository used for load/save
       _calculator        SalaryCalculator used for all math
       _frame             the in-memory pandas DataFrame of all employees
       _ratios            AllowanceRatios learned from the loaded data

     Methods / properties:
       __init__(repository, calculator)
           Loads the data and learns the allowance ratios.
       frame                 (property)
           Returns a copy of the full DataFrame.
       employee_ids          (property)
           List of all employee IDs (feeds the dropdowns).
       save()
           Writes the in-memory data to disk. Changes are NOT permanent
           until this is called (the "Save records" tab).
       employee(employee_id)
           Returns an Employee object for the given ID.
       search(text)
           Case-insensitive "contains" search across SEARCH_FIELDS. Returns
           matching rows with DIRECTORY_COLUMNS. Plain-text matching (no
           regex), so special characters are safe.
       add_employee(details)
           Validates the form data (name not empty; department, designation,
           grade, employment type and payment mode must be valid options;
           basic salary > 0). Then it:
             - generates the next employee ID,
             - uses the median working days and most common pay month,
             - sets full attendance and zero loss of pay,
             - fills allowances and deductions from AllowanceRatios,
             - calculates gross, deductions and net,
             - appends the new row to the DataFrame.
           Returns the new employee ID.
       calculate_salary(employee_id, working_days, loss_of_pay_days,
                        incentive_bonus, other_deductions)
           Recalculates one employee's pay for the month. Validates that
           working days > 0, loss of pay days between 0 and working days,
           incentive and other deductions not negative, and that the
           employee has a valid basic salary. Updates attendance,
           incentive, other deductions and the calculated totals, writes the
           result back, and returns the updated record.
       _locate(employee_id)
           Cleans the ID (trim + uppercase), finds its row index, or raises
           PayrollError "Unknown employee ID".
       _write(index, employee)
           Copies every field of an Employee object back into the DataFrame
           row.
       _next_employee_id()
           Finds the highest numeric part of existing IDs and returns the
           next one, e.g. "EMP501".

     Module-level helper:
       _require_choice(label, value, options)
           Raises PayrollError "Please choose a valid <label>." if the
           value is not in the allowed options.


5.8  ReportSection  (base class for on-screen report blocks)
     Purpose: template for anything shown as "heading + content".

     Data:
       _title             heading text

     Methods:
       render()
           Draws the heading with st.subheader() and then calls _body().
       _body()
           Abstract. Subclasses must implement it (raises
           NotImplementedError otherwise).


5.9  DirectorySection(ReportSection)
     Purpose: shows a table of employees using DIRECTORY_COLUMNS.

     Data:
       _frame             DataFrame to display

     Methods:
       __init__(frame, title="All employees")
       _body()            Displays the table (full width, no index).


5.10 SearchResultSection(DirectorySection)
     Purpose: same table, but for search results.

     Methods:
       __init__(frame)    Sets the title to "Search results".
       _body()            Shows "No employees match your search." if empty,
                          otherwise shows the table.


5.11 EmployeeDetailSection(ReportSection)
     Purpose: shows every field of one employee as a Field/Value table.

     Data:
       _employee          the Employee being shown

     Methods:
       __init__(employee) Title is "Employee details".
       _body()            Lists all record fields; the bank account number
                          is shown masked.


5.12 PayslipSection(ReportSection)
     Purpose: formatted payslip for one employee.

     Data:
       _employee          the Employee being shown

     Methods:
       __init__(employee) Title is "Payslip".
       _body()            Displays:
                            - caption: ID, name, department, designation,
                              grade, pay month
                            - Earnings table and Deductions table (side by
                              side)
                            - metrics: Gross salary, Total deductions,
                              Net pay
                            - attendance line (days present / working days /
                              loss of pay days)
                            - bank line (bank, masked account, payment mode)


------------------------------------------------------------------------------
6. USER INTERFACE FUNCTIONS
------------------------------------------------------------------------------

build_service()
    Creates the PayrollService once and keeps it in st.session_state, so
    data is not reloaded on every Streamlit rerun and edits survive between
    interactions.

add_employee_tab(service)
    "Add employee" tab. A form collects personal, job, salary and bank
    details. On submit it calls service.add_employee(). Errors are shown
    in red; on success a flash message is set and the page reruns.

calculate_tab(service)
    "Calculate salary" tab. Choose an employee, then edit working days,
    loss of pay days, incentive/bonus and other deductions (pre-filled with
    current values). Calls service.calculate_salary() and shows the new
    gross, deductions and net.

payslip_tab(service)
    "Payslip" tab. Choose an employee and display PayslipSection.

search_tab(service)
    "Search" tab. Type a name, ID, department or designation; shows
    SearchResultSection. Shows a hint if the box is empty.

save_tab(service)
    "Save records" tab. The "Save records" button calls service.save() and
    reports success, or an error if the file cannot be written.

main()
    Entry point. Sets up the page (title, icon, wide layout), builds the
    service, shows any flash message, then draws:
      1. the full employee directory
      2. a dropdown + full details of one employee
      3. five tabs: Add employee, Calculate salary, Payslip, Search,
         Save records


------------------------------------------------------------------------------
7. DATA FLOW EXAMPLES
------------------------------------------------------------------------------

Adding an employee
  Form -> add_employee_tab -> PayrollService.add_employee -> validate ->
  AllowanceRatios fills components -> SalaryCalculator.calculate ->
  new row appended in memory -> flash message -> page reruns.

Recalculating salary
  Form -> calculate_tab -> PayrollService.calculate_salary -> validate ->
  Employee.update -> SalaryCalculator.calculate -> _write to DataFrame ->
  flash message -> page reruns.

Saving
  "Save records" button -> PayrollService.save -> PayrollRepository.save ->
  payroll_records.pkl.


------------------------------------------------------------------------------
8. IMPORTANT NOTES
------------------------------------------------------------------------------

- Changes (new employees, recalculated salaries) exist only in memory until
  you click "Save records". Closing the app without saving loses them.
- Estimated components for new employees are averages of existing data, not
  legal statutory calculations. Review PF, ESI, professional tax and TDS
  against actual rules before real-world use.
- Bank account numbers are always displayed masked (last 4 digits only).
- Employee IDs typed anywhere are trimmed and converted to uppercase before
  lookup.
- If the CSV or pickle is missing or corrupted, delete payroll_records.pkl
  and make sure employee_payroll_400.csv is present, then restart.

==============================================================================
END OF README
==============================================================================
