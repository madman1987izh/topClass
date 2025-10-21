from datetime import datetime
from . import db


class PortfolioEntry(db.Model):
    __tablename__ = 'portfolio_entries'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    entry_type = db.Column(db.String(50), nullable=False)  # achievement, project, competition, etc.
    date_achieved = db.Column(db.Date, nullable=False)
    points_earned = db.Column(db.Integer, default=0)
    evidence_link = db.Column(db.String(500))  # ссылка на подтверждение
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