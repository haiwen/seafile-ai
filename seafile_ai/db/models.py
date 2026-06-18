# -*- coding: utf-8 -*-
import json

from sqlalchemy import BigInteger, Column, DateTime, String, Text

from seafile_ai.db import Base


class ChatMessages(Base):
    __tablename__ = 'chat_messages'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_uuid = Column(String(length=36), nullable=False, index=True)
    message_id = Column(String(length=4), nullable=False)
    role = Column(String(length=20), nullable=False)
    content = Column(Text, nullable=True)
    attachments = Column(Text, nullable=True)
    sources = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=True)

    def to_dict(self):
        try:
            sources = json.loads(self.sources) if self.sources else []
        except Exception:
            sources = self.sources
        if not isinstance(sources, list):
            sources = []

        try:
            attachments = json.loads(self.attachments) if self.attachments else []
        except Exception:
            attachments = self.attachments
        if not isinstance(attachments, list):
            attachments = []

        return {
            'id': self.id,
            'session_uuid': self.session_uuid,
            'message_id': self.message_id,
            'role': self.role,
            'content': self.content,
            'attachments': attachments,
            'sources': sources,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
