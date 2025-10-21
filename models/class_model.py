from datetime import datetime
from . import db


class SchoolClass(db.Model):
    __tablename__ = 'school_classes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    grade = db.Column(db.String(10), nullable=False)
    class_teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    total_rating = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Связи
    students = db.relationship('Student', backref='school_class', lazy=True, cascade='all, delete-orphan')

    def get_full_name(self):
        return f"{self.grade}{self.name}"

    def __repr__(self):
        return f'<SchoolClass {self.grade}{self.name}>'