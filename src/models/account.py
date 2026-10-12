from sqlalchemy import BigInteger, Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from models.account_status import AccountStatus
from models.base import Base
from models.client import Client


class Account(Base):
    __tablename__ = "account"

    id = Column(BigInteger, primary_key=True)
    account_key = Column(UUID(as_uuid=True), nullable=False, unique=True)
    client_id = Column(
        BigInteger,
        ForeignKey(Client.id, ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    status_id = Column(
        BigInteger,
        ForeignKey(AccountStatus.id, ondelete="RESTRICT"),
        nullable=False,
    )
    balance_cents = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    status = relationship(AccountStatus, foreign_keys=[status_id])
