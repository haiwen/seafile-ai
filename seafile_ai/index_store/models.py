from sqlalchemy import Column, Integer, String, DateTime, BigInteger
from seafile_ai.db import Base


class LibrarySdocIndex(Base):
    __tablename__ = 'library_sdoc_index'

    id = Column(Integer, primary_key=True, autoincrement=True)
    associate_id = Column(String(length=36), nullable=False)
    last_modify = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated = Column(DateTime, nullable=False)

    def __init__(self, associate_id, last_modify, created_at, updated=None):
        self.associate_id = associate_id
        self.last_modify = last_modify
        self.created_at = created_at
        self.updated = updated

    def to_dict(self):
        res = {
            'id': self.id,
            'associate_id': self.associate_id,
            'last_modify': self.last_modify,
            'created_at': self.created_at.isoformat(),
            'updated': self.updated.isoformat() if self.updated else None,
        }
        return res
