from sqlalchemy import BigInteger, Column, ForeignKey, String

from models.base import Base
from models.client import Client


class CompanyClient(Base):
    __tablename__ = "company_client"

    client_id = Column(
        BigInteger,
        ForeignKey(Client.id),
        primary_key=True,
    )

    cnpj = Column(String(14), nullable=False, unique=True)
    legal_name = Column(String(200), nullable=False)
    trade_name = Column(String(200))
