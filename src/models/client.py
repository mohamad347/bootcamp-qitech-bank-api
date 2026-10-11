from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from models.base import Base
from models.client_status import ClientStatus


class Client(Base):
    __tablename__ = "client"
    id = Column(BigInteger, primary_key=True)
    client_key = Column(UUID(as_uuid=True), nullable=False, unique=True)
    client_type = Column(String(20), nullable=False)
    email = Column(String(254), nullable=False, unique=True)
    timezone = Column(String(64), nullable=False)

    status_id = Column(
        BigInteger,
        ForeignKey(ClientStatus.id),
        nullable=False,
    )

    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    status = relationship(
        "ClientStatus",
        foreign_keys=[status_id],
        lazy="selectin",
    )
