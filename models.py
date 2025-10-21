from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import random
import string

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='teacher')
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


    # Связи
    managed_class = db.relationship('SchoolClass', backref='class_teacher', foreign_keys='SchoolClass.class_teacher_id')
    created_events = db.relationship('Event', backref='creator', foreign_keys='Event.created_by')
    approved_participations = db.relationship('Participation', backref='approver',
                                              foreign_keys='Participation.approved_by')
    approved_portfolio_entries = db.relationship('PortfolioEntry', backref='approver',
                                                 foreign_keys='PortfolioEntry.approved_by')
    class_points = db.relationship('ClassPoints', backref='teacher', foreign_keys='ClassPoints.assigned_by')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class SchoolClass(db.Model):
    __tablename__ = 'school_classes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    grade = db.Column(db.String(10), nullable=False)
    class_teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    total_rating = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Связи с учениками и баллами
    students = db.relationship('Student', backref='school_class', lazy=True, cascade='all, delete-orphan')
    class_points = db.relationship('ClassPoints', backref='school_class', lazy=True, cascade='all, delete-orphan')

    def get_full_name(self):
        return f"{self.grade}{self.name}"

    def update_total_rating(self):
        """Обновить общий рейтинг класса"""
        # Суммируем баллы от мероприятий
        participations = Participation.query.join(Student).filter(
            Student.class_id == self.id,
            Participation.approved == True
        ).all()

        event_points = 0
        # Собираем уникальные мероприятия, в которых участвовал класс
        participated_events = set()

        for participation in participations:
            if participation.event.event_type in ['class', 'both']:
                # Для классных мероприятий даем 2 балла за участие (независимо от количества участников)
                if participation.event.id not in participated_events:
                    event_points += 2
                    participated_events.add(participation.event.id)

        # Добавляем баллы, начисленные классным руководителем
        teacher_points = sum(cp.points for cp in self.class_points)

        self.total_rating = event_points + teacher_points
        db.session.commit()

    def __repr__(self):
        return f'<SchoolClass {self.grade}{self.name}>'


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

    def update_personal_rating(self):
        """Обновить личный рейтинг ученика"""
        total = 0
        for participation in self.participations:
            if participation.approved:
                # Участие без указания места = 1 балл
                if participation.place is None:
                    total += 1
                # Участие с указанием места
                elif participation.place == 1:
                    total += 5
                elif participation.place == 2:
                    total += 4
                elif participation.place == 3:
                    total += 3
                elif participation.place == 4:
                    total += 2
                # Любое другое место (участие) = 1 балл
                else:
                    total += 1

        # Добавляем баллы из портфолио
        portfolio_points = sum(entry.points_earned for entry in self.portfolio_entries if entry.approved)

        self.personal_rating = total + portfolio_points
        db.session.commit()

        self.personal_rating = total + portfolio_points
        db.session.commit()

    def get_statistics(self):
        """Получить статистику ученика"""
        self.update_personal_rating()

        participations = [p for p in self.participations if p.approved]
        total_events = len(participations)
        total_points = self.personal_rating

        # Статистика по уровням мероприятий
        level_stats = {}
        for level in ['school', 'city', 'republic', 'russian']:
            level_participations = [p for p in participations if p.event.level == level]
            level_points = sum(self._calculate_points(p.place) for p in level_participations)
            level_stats[level] = {
                'count': len(level_participations),
                'points': level_points
            }

        # Записи в портфолио
        portfolio_count = len([p for p in self.portfolio_entries if p.approved])

        return {
            'total_events': total_events,
            'total_points': total_points,
            'level_stats': level_stats,
            'portfolio_entries': portfolio_count
        }

    def _calculate_points(self, place):
        """Рассчитать баллы за место"""
        if place == 1:
            return 5
        elif place == 2:
            return 4
        elif place == 3:
            return 3
        elif place == 4:
            return 2
        else:
            return 1

    def __repr__(self):
        return f'<Student {self.full_name}>'


class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    level = db.Column(db.String(20), nullable=False)
    event_type = db.Column(db.String(20), nullable=False)  # class, student, both
    points = db.Column(db.Integer, nullable=False, default=0)  # устаревшее поле
    class_points = db.Column(db.Integer, default=0)  # баллы для класса
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
            'class': 'Только классный',
            'student': 'Только личный',
            'both': 'Личный и классный'
        }
        return types.get(self.event_type, self.event_type)

    def __repr__(self):
        return f'<Event {self.name}>'


class Participation(db.Model):
    __tablename__ = 'participations'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    news_link = db.Column(db.String(500))
    participants_count = db.Column(db.Integer, default=1)
    media_files = db.Column(db.String(500))
    description = db.Column(db.Text)
    place = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime)

    def get_place_display(self):
        if self.place == 1:
            return "🥇 1 место"
        elif self.place == 2:
            return "🥈 2 место"
        elif self.place == 3:
            return "🥉 3 место"
        elif self.place == 4:
            return "4 место"
        else:
            return "Участие"

    def get_points_earned(self):
        """Получить количество заработанных баллов"""
        if not self.approved:
            return 0

        # Участие без указания места = 1 балл
        if self.place is None:
            return 1
        # Участие с указанием места
        elif self.place == 1:
            return 5
        elif self.place == 2:
            return 4
        elif self.place == 3:
            return 3
        elif self.place == 4:
            return 2
        # Любое другое место (участие) = 1 балл
        else:
            return 1

    def get_place_display(self):
        if self.place == 1:
            return "🥇 1 место"
        elif self.place == 2:
            return "🥈 2 место"
        elif self.place == 3:
            return "🥉 3 место"
        elif self.place == 4:
            return "4 место"
        elif self.place is None:
            return "🎯 Участие"
        else:
            return f"{self.place} место"
    def __repr__(self):
        return f'<Participation student:{self.student_id} event:{self.event_id}>'


class PortfolioEntry(db.Model):
    __tablename__ = 'portfolio_entries'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    entry_type = db.Column(db.String(50), nullable=False)
    date_achieved = db.Column(db.Date, nullable=False)
    points_earned = db.Column(db.Integer, default=0)
    evidence_link = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime)

    def get_type_display(self):
        types = {
            'achievement': 'Достижение',
            'project': 'Проект',
            'competition': 'Конкурс',
            'olympiad': 'Олимпиада',
            'sport': 'Спорт',
            'art': 'Творчество'
        }
        return types.get(self.entry_type, self.entry_type)

    def __repr__(self):
        return f'<PortfolioEntry {self.title}>'


class ClassPoints(db.Model):
    __tablename__ = 'class_points'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    assigned_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ClassPoints class:{self.class_id} points:{self.points}>'


class StudentPassword(db.Model):
    __tablename__ = 'student_passwords'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    password = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<StudentPassword student:{self.student_id}>'


# Обновите функцию create_students_from_list
def create_students_from_list(student_names, class_id, class_name):
    """Создание учеников из списка ФИО"""
    students_data = []
    for full_name in student_names:
        if full_name.strip():
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

    login = f"{base_login}_{class_name.lower().replace(' ', '')}"

    # Проверяем уникальность
    counter = 1
    original_login = login
    while Student.query.filter_by(login=login).first():
        login = f"{original_login}{counter}"
        counter += 1

    return login


class PaperCollection(db.Model):
    __tablename__ = 'paper_collections'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    kilograms = db.Column(db.Float, nullable=False)  # количество килограмм
    collection_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Связи
    student = db.relationship('Student', backref='paper_collections')
    school_class = db.relationship('SchoolClass', backref='paper_collections')
    creator = db.relationship('User', backref='created_paper_collections')

    def __repr__(self):
        return f'<PaperCollection student:{self.student_id} kg:{self.kilograms}>'


def generate_password(length=8):
    """Генерация случайного пароля"""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def create_students_from_list(student_names, class_id, class_name):
    """Создание учеников из списка ФИО"""
    students_data = []
    for full_name in student_names:
        if full_name.strip():
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
                'password': password  # сохраняем пароль
            })

    return students_data