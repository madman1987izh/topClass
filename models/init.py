from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from .user import User
from .student import Student
from .class import SchoolClass
from .event import Event, Participation
from .portfolio import PortfolioEntry

__all__ = ['db', 'User', 'Student', 'SchoolClass', 'Event', 'Participation', 'PortfolioEntry']