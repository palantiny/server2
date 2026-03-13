"""
HerbMaster 모델 - 한약재 기본 정보
"""
from uuid import uuid4

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class HerbMaster(Base):
    """한약재 마스터 데이터 (이름, 원산지, 효능)."""

    __tablename__ = "herb_master"

    herb_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    name: Mapped[str] = mapped_column(String(100), index=True)
    origin: Mapped[str] = mapped_column(String(100))
    efficacy: Mapped[str] = mapped_column(Text)

    # 관계
    inventories = relationship("Inventory", back_populates="herb")
