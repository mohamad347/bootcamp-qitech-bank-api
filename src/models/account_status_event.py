from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String

from models.account import Account
from models.account_status import AccountStatus
from models.base import Base


class AccountStatusEvent(Base):
    __tablename__ = "account_status_event"

    id = Column(BigInteger, primary_key=True)
    account_id = Column(
        BigInteger,
        ForeignKey(Account.id, ondelete="RESTRICT"),
        nullable=False,
    )
    from_status_id = Column(
        BigInteger,
        ForeignKey(AccountStatus.id, ondelete="RESTRICT"),
    )
    to_status_id = Column(
        BigInteger,
        ForeignKey(AccountStatus.id, ondelete="RESTRICT"),
        nullable=False,
    )
    actor_type = Column(String(20), nullable=False)
    reason = Column(String(500))
    created_at = Column(DateTime(timezone=True), nullable=False)

    SYSTEM = "SYSTEM"
    INTERNAL = "INTERNAL"
