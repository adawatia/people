from fastapi import APIRouter

from routers import departments, organizations, units

router = APIRouter()
router.include_router(organizations.router)
router.include_router(units.router)
router.include_router(departments.router)
