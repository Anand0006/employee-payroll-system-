import pandas as pd
import streamlit as st
from datetime import date


DATA_FILE = "payroll_records.pkl"
SEED_FILE = "employee_payroll_400.csv"

DEPARTMENTS = ["Customer Support", "Engineering", "Finance", "HR", "IT Support", "Marketing", "Operations", "Sales"]
DESIGNATIONS = ["Associate", "Senior Executive", "Executive", "Manager", "Senior Manager", "Director"]
GRADES = ["G1", "G2", "G3", "G4", "G5", "G6"]
EMPLOYMENT_TYPES = ["Permanent", "Contract", "Probation"]
PAYMENT_MODES = ["Bank Transfer", "Cheque"]
GENDERS = ["Female", "Male", "Other"]

COLUMNS = [
    "employee_id", "employee_name", "gender", "date_of_birth", "department", "designation", "grade",
    "employment_type", "date_of_joining", "work_location", "pay_month", "working_days", "days_present",
    "loss_of_pay_days", "loss_of_pay_amount", "basic_salary", "hra", "dearness_allowance", "special_allowance",
    "transport_allowance", "incentive_bonus", "gross_salary", "pf_employee", "esi", "professional_tax",
    "income_tax_tds", "other_deductions", "total_deductions", "net_salary", "pf_employer", "pan_number",
    "uan_number", "bank_account_number", "bank_name", "payment_mode",
]

EARNING_FIELDS = ["basic_salary", "hra", "dearness_allowance", "special_allowance", "transport_allowance", "incentive_bonus"]
DEDUCTION_FIELDS = ["pf_employee", "esi", "professional_tax", "income_tax_tds", "other_deductions"]
RATIO_FIELDS = [
    "hra", "dearness_allowance", "special_allowance", "transport_allowance", "incentive_bonus",
    "pf_employee", "esi", "professional_tax", "income_tax_tds", "pf_employer",
]
SEARCH_FIELDS = ["employee_name", "employee_id", "department", "designation"]
DIRECTORY_COLUMNS = [
    "employee_id", "employee_name", "department", "designation", "grade", "employment_type",
    "basic_salary", "gross_salary", "total_deductions", "net_salary", "payment_mode",
]


class PayrollError(Exception):
    pass


def money(value):
    return f"₹{int(value):,}"


def amount_table(rows):
    return pd.DataFrame([(label, money(value)) for label, value in rows], columns=["Component", "Amount"])


def flash(kind, text):
    st.session_state["flash"] = (kind, text)


def show_flash():
    message = st.session_state.pop("flash", None)
    if message:
        kind, text = message
        getattr(st, kind)(text)


class AllowanceRatios:
    def __init__(self, ratios):
        self._ratios = dict(ratios)

    @classmethod
    def from_frame(cls, frame):
        valid = frame[frame["basic_salary"].astype(float) > 0]
        basic = valid["basic_salary"].astype(float)
        ratios = {field: float((valid[field].astype(float) / basic).mean()) for field in RATIO_FIELDS}
        return cls(ratios)

    def amount(self, field, basic):
        return int(round(basic * self._ratios[field]))


class SalaryCalculator:
    def gross(self, record):
        return sum(int(record[field]) for field in EARNING_FIELDS)

    def loss_of_pay_amount(self, gross, working_days, loss_of_pay_days):
        if working_days <= 0:
            return 0
        return int(round(gross * loss_of_pay_days / working_days))

    def calculate(self, record):
        gross = self.gross(record)
        loss_of_pay = self.loss_of_pay_amount(gross, int(record["working_days"]), int(record["loss_of_pay_days"]))
        statutory = sum(int(record[field]) for field in DEDUCTION_FIELDS)
        total = loss_of_pay + statutory
        return {
            "gross_salary": gross,
            "loss_of_pay_amount": loss_of_pay,
            "total_deductions": total,
            "net_salary": gross - total,
        }


class Person:
    def __init__(self, name, gender, date_of_birth):
        self._name = name
        self._gender = gender
        self._date_of_birth = date_of_birth

    @property
    def name(self):
        return self._name

    @property
    def gender(self):
        return self._gender

    @property
    def date_of_birth(self):
        return self._date_of_birth

    def describe(self):
        return self._name


class Employee(Person):
    def __init__(self, record):
        super().__init__(record["employee_name"], record["gender"], record["date_of_birth"])
        self._record = dict(record)

    @property
    def record(self):
        return dict(self._record)

    @property
    def employee_id(self):
        return self._record["employee_id"]

    def get(self, field):
        return self._record[field]

    def update(self, figures):
        self._record.update(figures)

    def masked_account(self):
        account = str(self._record["bank_account_number"])
        return "*" * max(len(account) - 4, 0) + account[-4:]

    def describe(self):
        return f"{self.employee_id} - {self.name}"


class PayrollRepository:
    def __init__(self, data_file=DATA_FILE, seed_file=SEED_FILE):
        self._data_file = data_file
        self._seed_file = seed_file

    def load(self, calculator):
        try:
            return pd.read_pickle(self._data_file)
        except FileNotFoundError:
            frame = self._seed(calculator)
            self.save(frame)
            return frame

    def save(self, frame):
        pd.to_pickle(frame, self._data_file)

    def _seed(self, calculator):
        raw = pd.read_csv(
            self._seed_file,
            dtype={"pan_number": str, "uan_number": str, "bank_account_number": str},
        )
        raw.insert(raw.columns.get_loc("loss_of_pay_days") + 1, "loss_of_pay_amount", 0)
        rows = []
        for record in raw.to_dict("records"):
            record.update(calculator.calculate(record))
            rows.append(record)
        return pd.DataFrame(rows, columns=COLUMNS)


class PayrollService:
    def __init__(self, repository, calculator):
        self._repository = repository
        self._calculator = calculator
        self._frame = repository.load(calculator)
        self._ratios = AllowanceRatios.from_frame(self._frame)

    @property
    def frame(self):
        return self._frame.copy()

    @property
    def employee_ids(self):
        return self._frame["employee_id"].tolist()

    def save(self):
        self._repository.save(self._frame)

    def employee(self, employee_id):
        return Employee(self._frame.loc[self._locate(employee_id)].to_dict())

    def search(self, text):
        query = str(text).strip()
        mask = pd.Series(False, index=self._frame.index)
        for field in SEARCH_FIELDS:
            mask |= self._frame[field].astype(str).str.contains(query, case=False, regex=False)
        return self._frame.loc[mask, DIRECTORY_COLUMNS]

    def add_employee(self, details):
        name = str(details["employee_name"]).strip()
        if not name:
            raise PayrollError("Employee name is required.")
        _require_choice("department", details["department"], DEPARTMENTS)
        _require_choice("designation", details["designation"], DESIGNATIONS)
        _require_choice("grade", details["grade"], GRADES)
        _require_choice("employment type", details["employment_type"], EMPLOYMENT_TYPES)
        _require_choice("payment mode", details["payment_mode"], PAYMENT_MODES)
        basic = float(details["basic_salary"])
        if basic <= 0:
            raise PayrollError("Basic salary must be a positive amount.")
        basic = int(round(basic))
        working = int(self._frame["working_days"].median())
        employee_id = self._next_employee_id()
        record = {column: "" for column in COLUMNS}
        record.update(
            employee_id=employee_id,
            employee_name=name,
            gender=details["gender"],
            date_of_birth=details["date_of_birth"],
            department=details["department"],
            designation=details["designation"],
            grade=details["grade"],
            employment_type=details["employment_type"],
            date_of_joining=details["date_of_joining"],
            work_location=details["work_location"],
            pay_month=self._frame["pay_month"].mode().iloc[0],
            working_days=working,
            days_present=working,
            loss_of_pay_days=0,
            loss_of_pay_amount=0,
            basic_salary=basic,
            other_deductions=0,
            pan_number=details["pan_number"],
            uan_number=details["uan_number"],
            bank_account_number=details["bank_account_number"],
            bank_name=details["bank_name"],
            payment_mode=details["payment_mode"],
        )
        for field in RATIO_FIELDS:
            record[field] = self._ratios.amount(field, basic)
        record.update(self._calculator.calculate(record))
        self._frame = pd.concat([self._frame, pd.DataFrame([record], columns=COLUMNS)], ignore_index=True)
        return employee_id

    def calculate_salary(self, employee_id, working_days, loss_of_pay_days, incentive_bonus, other_deductions):
        index = self._locate(employee_id)
        employee = Employee(self._frame.loc[index].to_dict())
        if working_days <= 0:
            raise PayrollError("Working days must be greater than zero.")
        if loss_of_pay_days < 0:
            raise PayrollError("Loss of pay days cannot be negative.")
        if loss_of_pay_days > working_days:
            raise PayrollError("Loss of pay days cannot be greater than working days.")
        if incentive_bonus < 0 or other_deductions < 0:
            raise PayrollError("Incentive and deduction amounts cannot be negative.")
        if float(employee.get("basic_salary")) <= 0:
            raise PayrollError("This employee has no valid basic salary.")
        employee.update(
            {
                "working_days": int(working_days),
                "days_present": int(working_days - loss_of_pay_days),
                "loss_of_pay_days": int(loss_of_pay_days),
                "incentive_bonus": int(incentive_bonus),
                "other_deductions": int(other_deductions),
            }
        )
        employee.update(self._calculator.calculate(employee.record))
        self._write(index, employee)
        return employee.record

    def _locate(self, employee_id):
        key = str(employee_id).strip().upper()
        matches = self._frame.index[self._frame["employee_id"] == key]
        if len(matches) == 0:
            raise PayrollError(f"Unknown employee ID '{key}'.")
        return matches[0]

    def _write(self, index, employee):
        for column, value in employee.record.items():
            self._frame.at[index, column] = value

    def _next_employee_id(self):
        numbers = self._frame["employee_id"].str.extract(r"(\d+)", expand=False).astype(int)
        return f"EMP{int(numbers.max()) + 1}"


def _require_choice(label, value, options):
    if value not in options:
        raise PayrollError(f"Please choose a valid {label}.")


class ReportSection:
    def __init__(self, title):
        self._title = title

    def render(self):
        st.subheader(self._title)
        self._body()

    def _body(self):
        raise NotImplementedError


class DirectorySection(ReportSection):
    def __init__(self, frame, title="All employees"):
        super().__init__(title)
        self._frame = frame

    def _body(self):
        st.dataframe(self._frame[DIRECTORY_COLUMNS], use_container_width=True, hide_index=True)


class SearchResultSection(DirectorySection):
    def __init__(self, frame):
        super().__init__(frame, "Search results")

    def _body(self):
        if self._frame.empty:
            st.info("No employees match your search.")
        else:
            super()._body()


class EmployeeDetailSection(ReportSection):
    def __init__(self, employee):
        super().__init__("Employee details")
        self._employee = employee

    def _body(self):
        record = self._employee.record
        rows = []
        for key, value in record.items():
            shown = self._employee.masked_account() if key == "bank_account_number" else str(value)
            rows.append((key, shown))
        st.dataframe(pd.DataFrame(rows, columns=["Field", "Value"]), use_container_width=True, hide_index=True)


class PayslipSection(ReportSection):
    def __init__(self, employee):
        super().__init__("Payslip")
        self._employee = employee

    def _body(self):
        record = self._employee.record
        st.caption(
            f"{self._employee.describe()}  |  {record['department']}  |  {record['designation']}  |  "
            f"Grade {record['grade']}  |  Pay month {record['pay_month']}"
        )
        earnings = [
            ("Basic salary", record["basic_salary"]),
            ("HRA", record["hra"]),
            ("Dearness allowance", record["dearness_allowance"]),
            ("Special allowance", record["special_allowance"]),
            ("Transport allowance", record["transport_allowance"]),
            ("Incentive / bonus", record["incentive_bonus"]),
        ]
        deductions = [
            ("Loss of pay", record["loss_of_pay_amount"]),
            ("PF (employee)", record["pf_employee"]),
            ("ESI", record["esi"]),
            ("Professional tax", record["professional_tax"]),
            ("Income tax (TDS)", record["income_tax_tds"]),
            ("Other deductions", record["other_deductions"]),
        ]
        left, right = st.columns(2)
        left.markdown("**Earnings**")
        left.dataframe(amount_table(earnings), use_container_width=True, hide_index=True)
        right.markdown("**Deductions**")
        right.dataframe(amount_table(deductions), use_container_width=True, hide_index=True)
        gross_col, deduction_col, net_col = st.columns(3)
        gross_col.metric("Gross salary", money(record["gross_salary"]))
        deduction_col.metric("Total deductions", money(record["total_deductions"]))
        net_col.metric("Net pay", money(record["net_salary"]))
        st.markdown(
            f"**Attendance:** {record['days_present']} of {record['working_days']} days present, "
            f"{record['loss_of_pay_days']} loss of pay day(s)"
        )
        st.markdown(
            f"**Bank:** {record['bank_name']}  |  **Account:** {self._employee.masked_account()}  |  "
            f"**Mode:** {record['payment_mode']}"
        )


def build_service():
    if "payroll_service" not in st.session_state:
        st.session_state["payroll_service"] = PayrollService(PayrollRepository(), SalaryCalculator())
    return st.session_state["payroll_service"]


def add_employee_tab(service):
    with st.form("add_employee_form"):
        col1, col2, col3 = st.columns(3)
        name = col1.text_input("Employee name")
        gender = col2.selectbox("Gender", GENDERS)
        date_of_birth = col3.date_input(
            "Date of birth", value=date(1995, 1, 1), min_value=date(1950, 1, 1), max_value=date.today()
        )
        department = col1.selectbox("Department", DEPARTMENTS)
        designation = col2.selectbox("Designation", DESIGNATIONS)
        grade = col3.selectbox("Grade", GRADES)
        employment_type = col1.selectbox("Employment type", EMPLOYMENT_TYPES)
        date_of_joining = col2.date_input("Date of joining", value=date.today())
        work_location = col3.text_input("Work location", value="Head Office")
        basic_salary = col1.number_input("Basic salary (₹)", min_value=0.0, step=1000.0, value=0.0)
        payment_mode = col2.selectbox("Payment mode", PAYMENT_MODES)
        bank_name = col3.text_input("Bank name")
        bank_account_number = col1.text_input("Bank account number")
        pan_number = col2.text_input("PAN number")
        uan_number = col3.text_input("UAN number")
        submitted = st.form_submit_button("Add employee")
    if submitted:
        try:
            employee_id = service.add_employee(
                {
                    "employee_name": name,
                    "gender": gender,
                    "date_of_birth": date_of_birth.isoformat(),
                    "department": department,
                    "designation": designation,
                    "grade": grade,
                    "employment_type": employment_type,
                    "date_of_joining": date_of_joining.isoformat(),
                    "work_location": work_location,
                    "basic_salary": basic_salary,
                    "payment_mode": payment_mode,
                    "bank_name": bank_name,
                    "bank_account_number": bank_account_number,
                    "pan_number": pan_number,
                    "uan_number": uan_number,
                }
            )
        except PayrollError as error:
            st.error(str(error))
        else:
            flash("success", f"Employee {employee_id} added. Use Save records to keep the change.")
            st.rerun()


def calculate_tab(service):
    selected = st.selectbox("Employee ID", service.employee_ids, key="calc_employee")
    record = service.employee(selected).record
    with st.form(f"calc_form_{selected}"):
        col1, col2 = st.columns(2)
        working_days = col1.number_input("Working days", min_value=1, step=1, value=int(record["working_days"]))
        loss_of_pay_days = col2.number_input(
            "Loss of pay days", min_value=0, step=1, value=int(record["loss_of_pay_days"])
        )
        incentive_bonus = col1.number_input(
            "Incentive / bonus (₹)", min_value=0, step=500, value=int(record["incentive_bonus"])
        )
        other_deductions = col2.number_input(
            "Other deductions (₹)", min_value=0, step=100, value=int(record["other_deductions"])
        )
        submitted = st.form_submit_button("Calculate salary")
    if submitted:
        try:
            updated = service.calculate_salary(
                selected, int(working_days), int(loss_of_pay_days), int(incentive_bonus), int(other_deductions)
            )
        except PayrollError as error:
            st.error(str(error))
        else:
            flash(
                "success",
                f"Salary recalculated for {selected}: gross {money(updated['gross_salary'])}, "
                f"total deductions {money(updated['total_deductions'])}, net {money(updated['net_salary'])}. "
                f"Use Save records to keep the change.",
            )
            st.rerun()


def payslip_tab(service):
    selected = st.selectbox("Employee ID", service.employee_ids, key="slip_employee")
    PayslipSection(service.employee(selected)).render()


def search_tab(service):
    query = st.text_input("Search by name, employee ID, department or designation")
    if not query.strip():
        st.info("Type a name, ID, department or designation to search.")
    else:
        SearchResultSection(service.search(query)).render()


def save_tab(service):
    st.write(f"Saves all employee records and salary figures to `{DATA_FILE}` so they persist between runs.")
    if st.button("Save records"):
        try:
            service.save()
        except OSError as error:
            st.error(f"Could not save records: {error}")
        else:
            st.success("Payroll records saved.")


def main():
    st.set_page_config(page_title="Payroll System", page_icon="💼", layout="wide")
    st.title("Employee Payroll System")
    service = build_service()
    show_flash()

    DirectorySection(service.frame).render()

    selected = st.selectbox("View full details of an employee", service.employee_ids, key="detail_employee")
    EmployeeDetailSection(service.employee(selected)).render()

    st.divider()
    add_tab, calc_tab, slip_tab, search_tab_view, save_tab_view = st.tabs(
        ["Add employee", "Calculate salary", "Payslip", "Search", "Save records"]
    )
    with add_tab:
        try:
            add_employee_tab(service)
        except PayrollError as error:
            st.error(str(error))
    with calc_tab:
        calculate_tab(service)
    with slip_tab:
        payslip_tab(service)
    with search_tab_view:
        search_tab(service)
    with save_tab_view:
        save_tab(service)


main()