from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String

from models.base import Base
from models.client import Client
from models.client_status import ClientStatus


class ClientStatusEvent(Base):
    __tablename__ = "client_status_event"

    id = Column(BigInteger, primary_key=True)

    client_id = Column(
        BigInteger,
        ForeignKey(Client.id),
        nullable=False,
    )

    from_status_id = Column(
        BigInteger,
        ForeignKey(ClientStatus.id),
    )

    to_status_id = Column(
        BigInteger,
        ForeignKey(ClientStatus.id),
        nullable=False,
    )

    actor_type = Column(String(20), nullable=False)
    reason = Column(String(500))
    created_at = Column(DateTime(timezone=True), nullable=False)

    SYSTEM = "SYSTEM"
    INTERNAL = "INTERNAL"