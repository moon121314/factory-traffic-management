import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db import Base, SessionLocal, engine
from app.domain.clock import FakeClock


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def session():
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
    async with SessionLocal() as s:
        yield s


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()