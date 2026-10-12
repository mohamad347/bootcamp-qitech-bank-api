from sqlalchemy import BigInteger, Column, String, UniqueConstraint

from models.base import Base


class AccountStatus(Base):
    __tablename__ = "account_status"

    id = Column(BigInteger, primary_key=True)
    enumerator = Column(String(20), nullable=False)
    __table_args__ = (UniqueConstraint("enumerator"),)

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    CLOSED = "CLOSED"
