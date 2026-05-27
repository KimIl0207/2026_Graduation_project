from fastapi import APIRouter

from schemas import RootResponse


router = APIRouter()


@router.get(
    "/",
    response_model=RootResponse,
    summary="Server status",
    tags=["Health"],
)
async def root():
    return {"message": "Server is running"}
