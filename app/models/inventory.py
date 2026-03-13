"""
Inventory 모델 - 재고/단가
"""
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Inventory(Base):
    """파트너사별 한약재 재고 및 단가."""

    __tablename__ = "inventory"

    inventory_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    herb_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("herb_master.herb_id"),
        nullable=False,
    )
    partner_id: Mapped[str] = mapped_column(String(100), index=True)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    # 관계
    herb = relationship("HerbMaster", back_populates="inventories")
