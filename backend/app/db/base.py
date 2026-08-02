"""SQLALchemy 2.0 声明式基类。所有ORM模型集成base"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


