from sqlalchemy import BigInteger, CHAR, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from models.base import Base


class FinancialTransaction(Base):
    __tablename__ = "financial_transaction"

    id = Column(BigInteger, primary_key=True)
    transaction_key = Column(UUID(as_uuid=True), nullable=False, unique=True)
    request_control_key = Column(UUID(as_uuid=True), nullable=False, unique=True)
    request_hash = Column(CHAR(64), nullable=False)
    transaction_type = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    entries = relationship(
        "TransactionEntry",
        back_populates="transaction",
        order_by="TransactionEntry.id",
    )

    DEPOSIT = "DEPOSIT"
    TRANSFER = "TRANSFER"
