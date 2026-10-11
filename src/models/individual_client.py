from sqlalchemy import BigInteger, Column, Date, ForeignKey, String

from models.base import Base
from models.client import Client


class IndividualClient(Base):
    __tablename__ = "individual_client"

    client_id = Column(
        BigInteger,
        ForeignKey(Client.id),
        primary_key=True,
    )

    cpf = Column(String(11), nullable=False, unique=True)
    full_name = Column(String(200), nullable=False)
    birth_date = Column(Date, nullable=False)