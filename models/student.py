from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import random
import string
from . import db


class Student(UserMixin, db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    personal_rating = db.Column(db.Integer, default=0)
    login = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Связи
    participations = db.relationship('Participation', backref='student', lazy=True, cascade='all, delete-orphan')
    portfolio_entries = db.relationship('PortfolioEntry', backref='student', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_statistics(self):
        """Получить статистику ученика"""
        total_events = len([p for p in self.participations if p.approved])
        total_points = self.personal_rating

        # Статистика по уровням мероприятий
        level_stats = {}
        for level in ['school', 'city', 'republic', 'russian']:
            level_events = [p for p in self.participations if p.approved and p.event.level == level]
            level_stats[level] = {
                'count': len(level_events),
                'points': sum(p.event.points for p in level_events)
            }

        return {
            'total_events': total_events,
            'total_points': total_points,
            'level_stats': level_stats,
            'portfolio_entries': len([p for p in self.portfolio_entries if p.approved])
        }

    def __repr__(self):
        return f'<Student {self.full_name}>'


# Вспомогательные функции
def generate_student_login(full_name, class_name):
    """Генерация логина для ученика"""
    names = full_name.split()
    if len(names) >= 2:
        last_name = names[0].lower()
        first_initial = names[1][0].lower() if names[1] else ''
        middle_initial = names[2][0].lower() if len(names) > 2 and names[2] else ''
        base_login = f"{last_name}_{first_initial}{middle_initial}"
    else:
        base_login = full_name.lower().replace(' ', '_')

    # Добавляем класс
    login = f"{base_login}_{class_name.lower().replace(' ', '')}"

    # Проверяем уникальность
    counter = 1
    original_login = login
    while Student.query.filter_by(login=login).first():
        login = f"{original_login}{counter}"
        counter += 1

    return login


def generate_password(length=8):
    """Генерация случайного пароля"""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def create_students_from_list(student_names, class_id, class_name):
    """Создание учеников из списка ФИО"""
    students_data = []
    for full_name in student_names:
        if full_name.strip():  # Пропускаем пустые строки
            login = generate_student_login(full_name.strip(), class_name)
            password = generate_password()

            student = Student(
                full_name=full_name.strip(),
                class_id=class_id,
                login=login
            )
            student.set_password(password)
            students_data.append({
                'student': student,
                'password': password
            })

    return students_data