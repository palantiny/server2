"""
HerbPriceItem / HerbPriceHistory 모델
CSV 한약재 가격표 데이터를 저장하기 위한 테이블.
"""
from uuid import uuid4

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class HerbPriceItem(Base):
    """한약재 가격 항목 — CSV 1행 = 1레코드."""

    __tablename__ = "herb_price_item"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    code: Mapped[str] = mapped_column(String(20), index=True)
    herb_name: Mapped[str] = mapped_column(String(100), index=True)
    origin: Mapped[str | None] = mapped_column(String(100), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(10), index=True,
    )  # '국산' or '수입'
    # 현재 가격 (26년 3월 기준)
    price_per_geun: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True,
    )
    packaging_unit_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    packaging_unit_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True,
    )
    box_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 구독 가격
    subscription_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True,
    )
    subscription_unit_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subscription_unit_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True,
    )
    subscription_box_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 메타
    manufacturer: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    discount_rate: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # 관계
    price_history = relationship(
        "HerbPriceHistory", back_populates="item", cascade="all, delete-orphan",
    )


class HerbPriceHistory(Base):
    """월별 가격 이력 (일반 구매 / 구독 구매)."""

    __tablename__ = "herb_price_history"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    item_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("herb_price_item.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year_month: Mapped[str] = mapped_column(
        String(10), nullable=False, index=True,
    )  # 'YYYY-MM' 형식
    regular_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True,
    )
    subscription_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True,
    )

    # 관계
    item = relationship("HerbPriceItem", back_populates="price_history")
