from repositories.lookup_repo import LookupRepository


class LookupService:
    def __init__(self, session):
        self.repo = LookupRepository(session)

    async def list_page(self, model, **params):
        return await self.repo.list_page(model, **params)
