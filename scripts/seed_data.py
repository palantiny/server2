"""
시드 데이터 스크립트
DB 테이블 생성 및 초기 데이터 삽입.
실행: python -m scripts.seed_data (프로젝트 루트에서)
"""
import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import async_session_maker, init_db
from app.models import HerbMaster, Inventory, User


async def seed():
    """시드 데이터 삽입."""
    await init_db()

    async with async_session_maker() as session:
        # User
        result = await session.execute(select(User).where(User.partner_token == "partner_demo_token_001"))
        user = result.scalar_one_or_none()
        if not user:
            user = User(partner_token="partner_demo_token_001", role="user")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print(f"Created user: {user.user_id}, token: {user.partner_token}")
        else:
            print(f"User exists: {user.user_id}")

        # HerbMaster
        herbs = [
            ("감초", "중국, 몽골", "보익기, 화해제독"),
            ("대추", "한국, 중국", "보혈안신, 건비위"),
            ("생강", "한국, 중국", "온중산한, 지해구담"),
            ("인삼", "한국, 중국", "대보원기, 보비익폐"),
        ]
        for name, origin, efficacy in herbs:
            r = await session.execute(select(HerbMaster).where(HerbMaster.name == name))
            if r.scalar_one_or_none() is None:
                session.add(HerbMaster(name=name, origin=origin, efficacy=efficacy))
        await session.commit()
        print("HerbMaster seeded")

        # Inventory
        herb_result = await session.execute(select(HerbMaster))
        for herb in herb_result.scalars().all():
            r = await session.execute(
                select(Inventory).where(
                    Inventory.herb_id == herb.herb_id,
                    Inventory.partner_id == "partner_001",
                )
            )
            if r.scalar_one_or_none() is None:
                session.add(
                    Inventory(
                        herb_id=herb.herb_id,
                        partner_id="partner_001",
                        stock_quantity=100,
                        price=15000.0,
                    )
                )
        await session.commit()
        print("Inventory seeded")


if __name__ == "__main__":
    asyncio.run(seed())
