from datetime import date
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuthSession, Department, Designation, Employee, EmployeeWorkHistory, Shift, Unit, User, now_ist
from repositories.employee_repo import EmployeeRepository
from schemas.employees import (
    EmployeeCreate,
    EmployeeRead,
    EmployeeUpdate,
    EmployeeWorkHistoryRead,
    PaginatedEmployeesResponse,
)


class EmployeeService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = EmployeeRepository(session)

    def enrich(self, emp: Employee) -> EmployeeRead:
        """Constructs EmployeeRead with nested readable names and computed full_name."""
        data = EmployeeRead.model_validate(emp)
        # Compute full name
        full_name_parts = [p for p in (emp.first_name, emp.last_name) if p]
        data.full_name = " ".join(full_name_parts) if full_name_parts else emp.employee_code

        if emp.department:
            data.department_name = emp.department.name
        if emp.unit:
            data.unit_name = emp.unit.name
        if emp.shift:
            data.shift_name = emp.shift.name
        if emp.designation_rel:
            data.designation_name = emp.designation_rel.name
        elif emp.designation:
            data.designation_name = emp.designation

        if emp.reporting_manager:
            mgr_parts = [p for p in (emp.reporting_manager.first_name, emp.reporting_manager.last_name) if p]
            data.reporting_manager_name = " ".join(mgr_parts) if mgr_parts else emp.reporting_manager.employee_code

        return data

    async def list_employees(
        self,
        page: int = 1,
        page_size: int = 20,
        q: str | None = None,
        unit_id: int | None = None,
        department_id: int | None = None,
        designation_id: int | None = None,
        status_filter: str | None = None,
        reporting_manager_id: int | None = None,
    ) -> PaginatedEmployeesResponse:
        employees, total = await self.repo.list_paginated(
            page=page,
            page_size=page_size,
            q=q,
            unit_id=unit_id,
            department_id=department_id,
            designation_id=designation_id,
            status=status_filter,
            reporting_manager_id=reporting_manager_id,
        )
        items = [self.enrich(e) for e in employees]
        import math
        total_pages = math.ceil(total / page_size) if total else 1
        return PaginatedEmployeesResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def get_employee(self, employee_id: int) -> Employee:
        emp = await self.repo.get_by_id(employee_id)
        if not emp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Employee with ID {employee_id} not found",
            )
        return emp

    async def create_employee(self, data: EmployeeCreate, *, commit: bool = True) -> EmployeeRead:
        # 1. Validate employee code uniqueness
        existing_code = await self.repo.get_by_code(data.employee_code)
        if existing_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Employee code '{data.employee_code}' already exists",
            )

        # 2. Validate official email uniqueness if provided
        if data.official_email:
            existing_email = await self.repo.get_by_email(data.official_email)
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Official email '{data.official_email}' already in use by another employee",
                )

        # 3. Validate user link if provided
        if data.user_id is not None:
            existing_user_link = await self.repo.get_by_user_id(data.user_id)
            if existing_user_link:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User ID {data.user_id} is already linked to employee {existing_user_link.employee_code}",
                )
            user = await self.session.get(User, data.user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with ID {data.user_id} not found",
                )

        # 4. Validate Department & Unit
        unit_id = data.unit_id
        if data.department_id is not None:
            dept = await self.session.get(Department, data.department_id)
            if not dept:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Department with ID {data.department_id} not found",
                )
            if unit_id is not None and dept.unit_id != unit_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Department '{dept.name}' does not belong to Unit ID {unit_id}",
                )
            if unit_id is None:
                unit_id = dept.unit_id

        if unit_id is not None:
            unit = await self.session.get(Unit, unit_id)
            if not unit:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Unit with ID {unit_id} not found",
                )

        # 5. Validate Designation
        designation_title = data.designation
        if data.designation_id is not None:
            desig = await self.session.get(Designation, data.designation_id)
            if not desig:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Designation with ID {data.designation_id} not found",
                )
            designation_title = desig.name
        elif designation_title:
            # Look up designation by name to link ID if exists
            stmt = select(Designation).where(Designation.name == designation_title)
            desig_match = (await self.session.execute(stmt)).scalar_one_or_none()
            if desig_match:
                data.designation_id = desig_match.id

        # 6. Validate Reporting Manager
        if data.reporting_manager_id is not None:
            manager = await self.session.get(Employee, data.reporting_manager_id)
            if not manager:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Reporting manager with ID {data.reporting_manager_id} not found",
                )

        # 7. Create Employee
        payload = data.model_dump()
        payload["unit_id"] = unit_id
        payload["designation"] = designation_title
        emp = Employee(**payload)
        await self.repo.create(emp)

        # Record initial work history
        initial_history = EmployeeWorkHistory(
            employee_id=emp.id,
            unit_id=unit_id,
            department_id=data.department_id,
            designation_id=data.designation_id,
            from_date=data.date_of_joining or date.today(),
            remarks="Initial Appointment",
        )
        await self.repo.add_work_history(initial_history)

        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        refreshed = await self.get_employee(emp.id)
        return self.enrich(refreshed)

    async def update_employee(self, employee_id: int, data: EmployeeUpdate) -> EmployeeRead:
        emp = await self.get_employee(employee_id)
        update_data = data.model_dump(exclude_unset=True)

        # Check official email uniqueness if changing
        if "official_email" in update_data and update_data["official_email"]:
            existing_email = await self.repo.get_by_email(update_data["official_email"])
            if existing_email and existing_email.id != employee_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Official email '{update_data['official_email']}' is already in use",
                )

        # Check reporting manager
        if "reporting_manager_id" in update_data and update_data["reporting_manager_id"] is not None:
            mgr_id = update_data["reporting_manager_id"]
            if mgr_id == employee_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="An employee cannot be their own reporting manager",
                )
            # Cycle detection (walk up manager chain)
            current_mgr_id = mgr_id
            visited = {employee_id}
            while current_mgr_id:
                if current_mgr_id in visited:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Circular reporting hierarchy detected",
                    )
                visited.add(current_mgr_id)
                mgr_emp = await self.session.get(Employee, current_mgr_id)
                if not mgr_emp:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Reporting manager with ID {mgr_id} not found",
                    )
                current_mgr_id = mgr_emp.reporting_manager_id

        # Track movements for internal work history
        has_movement = False
        old_unit = emp.unit_id
        old_dept = emp.department_id
        old_desig = emp.designation_id

        # Check Department & Unit changes
        if "department_id" in update_data and update_data["department_id"] is not None:
            dept = await self.session.get(Department, update_data["department_id"])
            if not dept:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Department with ID {update_data['department_id']} not found",
                )
            target_unit = update_data.get("unit_id", emp.unit_id)
            if target_unit is not None and dept.unit_id != target_unit:
                # auto-align unit to department
                update_data["unit_id"] = dept.unit_id

        if "designation_id" in update_data and update_data["designation_id"] is not None:
            desig = await self.session.get(Designation, update_data["designation_id"])
            if not desig:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Designation with ID {update_data['designation_id']} not found",
                )
            update_data["designation"] = desig.name

        # Apply updates
        for key, val in update_data.items():
            setattr(emp, key, val)

        # Check if movement occurred
        new_unit = emp.unit_id
        new_dept = emp.department_id
        new_desig = emp.designation_id
        if (new_unit != old_unit) or (new_dept != old_dept) or (new_desig != old_desig):
            # Close previous active work history
            histories = await self.repo.get_work_history(emp.id)
            today = date.today()
            if histories:
                last_history = histories[0]
                if last_history.to_date is None:
                    last_history.to_date = today

            movement_history = EmployeeWorkHistory(
                employee_id=emp.id,
                unit_id=new_unit,
                department_id=new_dept,
                designation_id=new_desig,
                from_date=today,
                remarks="Position / Department Update",
            )
            await self.repo.add_work_history(movement_history)

        await self.session.commit()
        self.session.expire_all()
        refreshed = await self.get_employee(employee_id)
        return self.enrich(refreshed)

    async def deactivate_employee(
        self,
        employee_id: int,
        exit_date: date | None = None,
        exit_reason: str | None = None,
    ) -> EmployeeRead:
        emp = await self.get_employee(employee_id)
        emp.status = "INACTIVE"
        emp.exit_date = exit_date or date.today()
        emp.exit_reason = exit_reason or "Deactivated by Administrator"
        if emp.user_id:
            user = await self.session.get(User, emp.user_id)
            if user:
                user.is_active = False
            await self.session.execute(
                update(AuthSession)
                .where(AuthSession.user_id == emp.user_id, AuthSession.revoked_at.is_(None))
                .values(revoked_at=now_ist())
            )
        await self.session.commit()
        self.session.expire_all()
        refreshed = await self.get_employee(employee_id)
        return self.enrich(refreshed)

    async def activate_employee(self, employee_id: int) -> EmployeeRead:
        emp = await self.get_employee(employee_id)
        emp.status = "ACTIVE"
        emp.exit_date = None
        emp.exit_reason = None
        if emp.user_id:
            user = await self.session.get(User, emp.user_id)
            if user:
                user.is_active = True
        await self.session.commit()
        self.session.expire_all()
        refreshed = await self.get_employee(employee_id)
        return self.enrich(refreshed)

    async def delete_employee(self, employee_id: int) -> None:
        emp = await self.get_employee(employee_id)
        await self.session.execute(
            update(Employee)
            .where(Employee.reporting_manager_id == employee_id)
            .values(reporting_manager_id=None)
        )
        await self.repo.delete(emp)
        await self.session.commit()

    async def get_work_history(self, employee_id: int) -> list[EmployeeWorkHistoryRead]:
        await self.get_employee(employee_id)
        histories = await self.repo.get_work_history(employee_id)
        return [EmployeeWorkHistoryRead.model_validate(h) for h in histories]
