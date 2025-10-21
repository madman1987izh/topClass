from datetime import datetime
from . import db


class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    level = db.Column(db.String(20), nullable=False)  # school, city, republic, russian
    event_type = db.Column(db.String(20), nullable=False)  # class, student
    points = db.Column(db.Integer, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    # Связи
    participations = db.relationship('Participation', backref='event', lazy=True, cascade='all, delete-orphan')

    def get_level_display(self):
        levels = {
            'school': 'Школьный',
            'city': 'Городской',
            'republic': 'Республиканский',
            'russian': 'Российский'
        }
        return levels.get(self.level, self.level)

    def get_type_display(self):
        types = {
            'class': 'Рейтинг класса',
            'student': 'Личный рейтинг'
        }
        return types.get(self.event_type, self.event_type)


class Participation(db.Model):
    __tablename__ = 'participations'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    news_link = db.Column(db.String(500))
    participants_count = db.Column(db.Integer, default=1)
    media_files = db.Column(db.String(500))  # пути к файлам
    description = db.Column(db.Text)  # описание участия
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<Participation {self.student.full_name} in {self.event.name}>'