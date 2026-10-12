from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from models.base import Base


class TransactionEntry(Base):
    __tablename__ = "transaction_entry"

    id = Column(BigInteger, primary_key=True)
    transaction_id = Column(
        BigInteger,
        ForeignKey("financial_transaction.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id = Column(
        BigInteger,
        ForeignKey("account.id", ondelete="RESTRICT"),
        nullable=False,
    )
    direction = Column(String(10), nullable=False)
    entry_type = Column(String(20), nullable=False)
    amount_cents = Column(BigInteger, nullable=False)
    balance_after_cents = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    transaction = relationship(
        "FinancialTransaction",
        back_populates="entries",
    )
    account = relationship("Account", foreign_keys=[account_id])

    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    PRINCIPAL = "PRINCIPAL"
    FEE = "FEE"
