from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from . import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='teacher')  # admin, teacher
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Связи
    managed_class = db.relationship('SchoolClass', backref='class_teacher', foreign_keys='SchoolClass.class_teacher_id')
    created_events = db.relationship('Event', backref='creator', foreign_keys='Event.created_by')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'