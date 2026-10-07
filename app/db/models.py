"""SQLAlchemy models: one row per file, one row per feature."""

from __future__ import annotations

import datetime

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class FileRecord(Base):
    """One uploaded file and its processing outcome."""

    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(16))
    size_bytes: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), index=True)
    crs: Mapped[str | None] = mapped_column(String(64), nullable=True)
    crs_wkt: Mapped[str | None] = mapped_column(nullable=True)
    crs_assumed: Mapped[bool] = mapped_column(default=False)
    feature_count: Mapped[int | None] = mapped_column(nullable=True)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC)
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)

    features: Mapped[list[FeatureRecord]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )


class FeatureRecord(Base):
    """One measured feature belonging to a file."""

    __tablename__ = "features"
    __table_args__ = (UniqueConstraint("file_id", "feature_index"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), index=True
    )
    feature_index: Mapped[int]
    layer: Mapped[str] = mapped_column(String(255), default="")
    geometry_type: Mapped[str] = mapped_column(String(64))
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    crs: Mapped[str] = mapped_column(String(64))
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    measurement_status: Mapped[str] = mapped_column(String(32))
    area_m2: Mapped[float | None] = mapped_column(nullable=True)
    perimeter_m: Mapped[float | None] = mapped_column(nullable=True)
    length_m: Mapped[float | None] = mapped_column(nullable=True)
    measurement_crs: Mapped[str | None] = mapped_column(String(32), nullable=True)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(nullable=True)

    file: Mapped[FileRecord] = relationship(back_populates="features")
