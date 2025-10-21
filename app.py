from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Student, SchoolClass, Event, Participation, PortfolioEntry, ClassPoints, PaperCollection  # добавили PaperCollection
from models import generate_student_login, generate_password, create_students_from_list
import os
from datetime import datetime
import csv
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # этот ключ также используется для сессий
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///school_rating.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация расширений
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@app.template_filter('has_attr')
def has_attr_filter(obj, attr_name):
    return hasattr(obj, attr_name)

# Или добавьте контекстный процессор
@app.context_processor
def utility_processor():
    def has_attr(obj, attr_name):
        return hasattr(obj, attr_name)
    return dict(has_attr=has_attr)



@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    if not user:
        user = Student.query.get(int(user_id))
    return user


# ===== МАРШРУТЫ АУТЕНТИФИКАЦИИ =====
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует')
            return redirect(url_for('register'))

        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Регистрация успешна!')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if not user:
            user = Student.query.filter_by(login=username).first()

        if user and hasattr(user, 'check_password') and user.check_password(password):
            login_user(user)
            name = user.full_name if hasattr(user, 'full_name') else user.username
            flash(f'Добро пожаловать, {name}!')
            return redirect(url_for('dashboard'))
        else:
            flash('Неверное имя пользователя или пароль')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# ===== ГЛАВНАЯ ПАНЕЛЬ =====
@app.route('/dashboard')
@login_required
def dashboard():
    if getattr(current_user, 'role', None):
        # Обычный пользователь (учитель/админ)
        total_school_rating = db.session.query(db.func.sum(SchoolClass.total_rating)).scalar() or 0
        classes_count = SchoolClass.query.count()
        events_count = Event.query.count()
        students_count = Student.query.count()

        return render_template('dashboard.html',
                               total_school_rating=total_school_rating,
                               classes_count=classes_count,
                               events_count=events_count,
                               students_count=students_count)
    else:
        # Ученик
        return render_template('dashboard.html')

# ===== МАРШРУТЫ ДЛЯ КЛАССОВ =====
@app.route('/classes')
@login_required
def classes():
    if getattr(current_user, 'role', None) not in ['admin', 'teacher']:
        flash('Недостаточно прав')
        return redirect(url_for('dashboard'))

    classes_list = SchoolClass.query.all()
    teachers = User.query.filter_by(role='teacher').all() if getattr(current_user, 'role', None) == 'admin' else []
    return render_template('classes/classes.html', classes=classes_list, teachers=teachers)


@app.route('/add_class', methods=['GET', 'POST'])
@login_required
def add_class():
    if not hasattr(current_user, 'role') or current_user.role != 'admin':
        flash('Недостаточно прав')
        return redirect(url_for('classes'))

    if request.method == 'POST':
        name = request.form['name']
        grade = request.form['grade']
        student_list = request.form.get('student_list', '')

        new_class = SchoolClass(name=name, grade=grade)
        db.session.add(new_class)
        db.session.commit()

        # Создаем учеников из списка
        if student_list:
            student_names = [name.strip() for name in student_list.split('\n') if name.strip()]
            if student_names:
                students_data = create_students_from_list(student_names, new_class.id, f"{grade}{name}")

                for data in students_data:
                    db.session.add(data['student'])

                db.session.commit()
                flash(f'Класс "{grade}{name}" и {len(students_data)} учеников успешно добавлены')
            else:
                flash(f'Класс "{grade}{name}" успешно добавлен (без учеников)')
        else:
            flash(f'Класс "{grade}{name}" успешно добавлен')

        return redirect(url_for('classes'))

    return render_template('classes/add_class.html')


@app.route('/class/<int:class_id>/students')
@login_required
def class_students(class_id):
    if not hasattr(current_user, 'role') or current_user.role not in ['admin', 'teacher']:
        flash('Недостаточно прав')
        return redirect(url_for('dashboard'))

    school_class = SchoolClass.query.get_or_404(class_id)
    return render_template('classes/class_students.html', school_class=school_class)


@app.route('/class/<int:class_id>/export_logins')
@login_required
def export_student_logins(class_id):
    if not hasattr(current_user, 'role') or current_user.role not in ['admin', 'teacher']:
        flash('Недостаточно прав')
        return redirect(url_for('dashboard'))

    school_class = SchoolClass.query.get_or_404(class_id)

    # Создаем CSV в памяти
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ФИО', 'Логин', 'Пароль', 'Класс'])

    for student in school_class.students:
        # Генерируем новый пароль для каждого ученика
        new_password = generate_password()

        # Обновляем пароль ученика в базе данных
        student.set_password(new_password)

        writer.writerow([
            student.full_name,
            student.login,
            new_password,
            school_class.get_full_name()
        ])

    # Сохраняем все изменения паролей
    db.session.commit()

    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'logins_{school_class.get_full_name()}.csv'
    )


@app.route('/assign_teacher/<int:class_id>', methods=['POST'])
@login_required
def assign_teacher(class_id):
    if not hasattr(current_user, 'role') or current_user.role != 'admin':
        flash('Недостаточно прав')
        return redirect(url_for('classes'))

    teacher_id = request.form['teacher_id']
    school_class = SchoolClass.query.get_or_404(class_id)
    school_class.class_teacher_id = teacher_id if teacher_id else None
    db.session.commit()

    flash('Классный руководитель назначен')
    return redirect(url_for('classes'))


# ===== МАРШРУТЫ ДЛЯ УПРАВЛЕНИЯ БАЛЛАМИ КЛАССА =====
@app.route('/add_class_points/<int:class_id>', methods=['GET', 'POST'])
@login_required
def add_class_points(class_id):
    if not hasattr(current_user, 'role') or current_user.role not in ['admin', 'teacher']:
        flash('Недостаточно прав')
        return redirect(url_for('dashboard'))

    school_class = SchoolClass.query.get_or_404(class_id)

    if hasattr(current_user,
               'role') and current_user.role == 'teacher' and school_class.class_teacher_id != current_user.id:
        flash('Вы не являетесь классным руководителем этого класса')
        return redirect(url_for('classes'))

    if request.method == 'POST':
        points = int(request.form['points'])
        reason = request.form['reason']

        class_points = ClassPoints(
            class_id=class_id,
            points=points,
            reason=reason,
            assigned_by=current_user.id
        )
        db.session.add(class_points)
        school_class.update_total_rating()
        db.session.commit()

        flash(f'Классу {school_class.get_full_name()} начислено {points} баллов')
        return redirect(url_for('class_students', class_id=class_id))

    return render_template('classes/add_class_points.html', school_class=school_class)


@app.route('/class_points_history/<int:class_id>')
@login_required
def class_points_history(class_id):
    if not hasattr(current_user, 'role') or current_user.role not in ['admin', 'teacher']:
        flash('Недостаточно прав')
        return redirect(url_for('dashboard'))

    school_class = SchoolClass.query.get_or_404(class_id)
    points_history = ClassPoints.query.filter_by(class_id=class_id).order_by(ClassPoints.created_at.desc()).all()

    return render_template('classes/class_points_history.html',
                           school_class=school_class,
                           points_history=points_history)


# ===== МАРШРУТЫ ДЛЯ МЕРОПРИЯТИЙ =====
@app.route('/events')
@login_required
def events():
    events_list = Event.query.filter_by(is_active=True).all()
    return render_template('events/events.html', events=events_list)


@app.route('/add_event', methods=['GET', 'POST'])
@login_required
def add_event():
    if not hasattr(current_user, 'role') or current_user.role not in ['admin', 'teacher']:
        flash('Недостаточно прав')
        return redirect(url_for('events'))

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        level = request.form['level']
        event_type = request.form['event_type']
        class_points = int(request.form['class_points']) if request.form['class_points'] else 0

        event = Event(
            name=name,
            description=description,
            level=level,
            event_type=event_type,
            class_points=class_points,
            created_by=current_user.id
        )
        db.session.add(event)
        db.session.commit()

        flash('Мероприятие добавлено')
        return redirect(url_for('events'))

    return render_template('events/add_event.html')


@app.route('/event/<int:event_id>/participate', methods=['GET', 'POST'])
@login_required
def participate_in_event(event_id):
    event = Event.query.get_or_404(event_id)

    if request.method == 'POST':
        if getattr(current_user, 'role', None) in ['admin', 'teacher']:
            # Проверяем, выбрана ли опция "все ученики"
            all_students = request.form.get('all_students') == 'on'

            if all_students:
                # Если выбрано "все ученики", получаем список всех учеников класса
                if getattr(current_user, 'role', None) == 'teacher' and current_user.managed_class:
                    # Получаем класс, которым руководит учитель
                    managed_class = SchoolClass.query.get(
                        current_user.managed_class[0].id) if current_user.managed_class else None
                    if managed_class:
                        student_ids = [student.id for student in managed_class.students]
                    else:
                        flash('У вас нет класса для управления')
                        return redirect(url_for('participate_in_event', event_id=event_id))
                else:
                    # Для админа - все ученики из выбранного класса
                    class_id = request.form.get('class_id')
                    if class_id:
                        student_ids = [student.id for student in Student.query.filter_by(class_id=class_id).all()]
                    else:
                        flash('Для регистрации всех учеников выберите класс')
                        return redirect(url_for('participate_in_event', event_id=event_id))
            else:
                # Обычный выбор конкретных учеников
                student_ids = request.form.getlist('student_ids')

            news_link = request.form['news_link']
            participants_count = int(request.form['participants_count'])
            description = request.form['description']

            registered_count = 0
            for student_id in student_ids:
                place = request.form.get(f'place_{student_id}')
                # Если место "не участвовал", пропускаем ученика
                if place == 'not_participated':
                    continue

                # Если место не указано (участие без места) или указано конкретное место
                place = int(place) if place and place != 'not_participated' and place != '' else None

                participation = Participation(
                    event_id=event_id,
                    student_id=student_id,
                    news_link=news_link,
                    participants_count=participants_count,
                    description=description,
                    place=place,
                    approved=True
                )
                db.session.add(participation)
                registered_count += 1

                # Обновляем рейтинг ученика
                student = Student.query.get(student_id)
                student.update_personal_rating()

            # Обновляем рейтинг класса после регистрации всех участников
            if event.event_type in ['class', 'both'] and registered_count > 0:
                # Находим класс первого зарегистрированного ученика
                if student_ids:
                    first_student = Student.query.get(student_ids[0])
                    if first_student:
                        first_student.school_class.update_total_rating()

            db.session.commit()
            flash(f'Участие зарегистрировано для {registered_count} учеников')

        else:
            # Код для учеников
            place = request.form.get('place')
            place = int(place) if place and place != '' else None

            participation = Participation(
                event_id=event_id,
                student_id=current_user.id,
                news_link=request.form['news_link'],
                participants_count=1,
                description=request.form['description'],
                place=place,
                approved=False
            )
            db.session.add(participation)

            # Обновляем рейтинг ученика
            current_user.update_personal_rating()

            db.session.commit()
            flash('Заявка на участие отправлена')

        return redirect(url_for('events'))

    # Получаем студентов для выбора
    if getattr(current_user, 'role', None) in ['admin', 'teacher']:
        managed_class = None
        if getattr(current_user, 'role', None) == 'teacher' and current_user.managed_class:
            # Классный руководитель видит только своих учеников
            managed_class = SchoolClass.query.get(
                current_user.managed_class[0].id) if current_user.managed_class else None
            if managed_class:
                students = managed_class.students
            else:
                students = []
                flash('У вас нет класса для управления')
        else:
            # Админ видит всех учеников
            students = Student.query.all()

        # Получаем список классов для админа
        classes = SchoolClass.query.all() if getattr(current_user, 'role', None) == 'admin' else []
    else:
        students = [current_user]
        managed_class = None
        classes = []

    return render_template('events/participate_event.html',
                           event=event,
                           students=students,
                           managed_class=managed_class,
                           classes=classes)
# ===== МАРШРУТЫ ДЛЯ ПОРТФОЛИО =====
@app.route('/portfolio/<int:student_id>')
@login_required
def student_portfolio(student_id):
    if hasattr(current_user, 'role') and current_user.role in ['admin', 'teacher']:
        student = Student.query.get_or_404(student_id)
    else:
        if current_user.id != student_id:
            flash('Недостаточно прав')
            return redirect(url_for('dashboard'))
        student = current_user

    statistics = student.get_statistics()
    participations = Participation.query.filter_by(student_id=student_id, approved=True).all()
    portfolio_entries = PortfolioEntry.query.filter_by(student_id=student_id, approved=True).all()

    return render_template('portfolio/student_portfolio.html',
                           student=student,
                           statistics=statistics,
                           participations=participations,
                           portfolio_entries=portfolio_entries)


@app.route('/add_portfolio_entry', methods=['POST'])
@login_required
def add_portfolio_entry():
    if hasattr(current_user, 'role'):
        flash('Только ученики могут добавлять записи в портфолио')
        return redirect(url_for('dashboard'))

    title = request.form['title']
    description = request.form['description']
    entry_type = request.form['entry_type']
    date_achieved = datetime.strptime(request.form['date_achieved'], '%Y-%m-%d').date()
    points_earned = int(request.form['points_earned'])
    evidence_link = request.form['evidence_link']

    entry = PortfolioEntry(
        student_id=current_user.id,
        title=title,
        description=description,
        entry_type=entry_type,
        date_achieved=date_achieved,
        points_earned=points_earned,
        evidence_link=evidence_link,
        approved=False
    )
    db.session.add(entry)
    db.session.commit()

    flash('Запись добавлена в портфолио и ожидает подтверждения')
    return redirect(url_for('student_portfolio', student_id=current_user.id))
# ===== МАРШРУТЫ ДЛЯ РЕЙТИНГОВ И ОТЧЕТОВ =====
@app.route('/ratings')
@login_required
def ratings():
    class_ratings = SchoolClass.query.order_by(SchoolClass.total_rating.desc()).all()
    student_ratings = Student.query.order_by(Student.personal_rating.desc()).all()

    return render_template('ratings.html',
                           class_ratings=class_ratings,
                           student_ratings=student_ratings)


@app.route('/reports')
@login_required
def reports():
    classes = SchoolClass.query.all()
    events = Event.query.all()

    return render_template('reports.html', classes=classes, events=events)


# ===== API ДЛЯ ОТЧЕТОВ =====
@app.route('/api/class_report/<int:class_id>')
@login_required
def class_report(class_id):
    school_class = SchoolClass.query.get_or_404(class_id)
    students = Student.query.filter_by(class_id=class_id).all()

    report_data = {
        'class_name': school_class.get_full_name(),
        'total_rating': school_class.total_rating,
        'students': [
            {
                'name': student.full_name,
                'personal_rating': student.personal_rating,
                'participations': [
                    {
                        'event_name': p.event.name,
                        'points': p.get_points_earned(),
                        'date': p.created_at.strftime('%Y-%m-%d')
                    } for p in student.participations if p.approved
                ]
            } for student in students
        ]
    }

    return jsonify(report_data)


# ===== ОБНОВЛЕНИЕ БАЗЫ ДАННЫХ =====
@app.route('/update-db')
def update_db():
    """Обновление структуры базы данных"""
    with app.app_context():
        # Создаем временную таблицу для событий
        db.session.execute('''
            CREATE TABLE IF NOT EXISTS events_new (
                id INTEGER PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                level VARCHAR(20) NOT NULL,
                event_type VARCHAR(20) NOT NULL,
                points INTEGER NOT NULL DEFAULT 0,
                class_points INTEGER DEFAULT 0,
                created_by INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        ''')

        # Копируем данные из старой таблицы
        db.session.execute('''
            INSERT INTO events_new (id, name, description, level, event_type, points, created_by, created_at, is_active)
            SELECT id, name, description, level, event_type, points, created_by, created_at, is_active FROM events
        ''')

        # Удаляем старую таблицу
        db.session.execute('DROP TABLE events')

        # Переименовываем новую таблицу
        db.session.execute('ALTER TABLE events_new RENAME TO events')

        # Создаем таблицу class_points если её нет
        db.session.execute('''
            CREATE TABLE IF NOT EXISTS class_points (
                id INTEGER PRIMARY KEY,
                class_id INTEGER NOT NULL,
                points INTEGER NOT NULL,
                reason VARCHAR(500) NOT NULL,
                assigned_by INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (class_id) REFERENCES school_classes (id),
                FOREIGN KEY (assigned_by) REFERENCES users (id)
            )
        ''')

        db.session.commit()
        flash('База данных успешно обновлена')
    return redirect(url_for('index'))

# ===== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ =====
@app.route('/init-db')
def init_db():
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(username='admin', email='admin@school.ru', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)

        teacher = User(username='teacher1', email='teacher1@school.ru', role='teacher')
        teacher.set_password('teacher123')
        db.session.add(teacher)

        class_5a = SchoolClass(name='А', grade='5')
        class_5b = SchoolClass(name='Б', grade='5')
        class_6a = SchoolClass(name='А', grade='6')

        db.session.add_all([class_5a, class_5b, class_6a])
        db.session.commit()

        class_5a.class_teacher_id = teacher.id
        db.session.commit()

        student_names_5a = [
            'Иванов Иван Иванович',
            'Петров Петр Петрович',
            'Сидорова Мария Сергеевна'
        ]

        student_names_5b = [
            'Козлов Алексей Владимирович',
            'Николаева Анна Дмитриевна'
        ]

        students_5a = create_students_from_list(student_names_5a, class_5a.id, '5А')
        students_5b = create_students_from_list(student_names_5b, class_5b.id, '5Б')

        for data in students_5a + students_5b:
            db.session.add(data['student'])

        event1 = Event(
            name='Школьная олимпиада по математике',
            description='Ежегодная школьная олимпиада',
            level='school',
            event_type='both',
            class_points=10,
            created_by=teacher.id
        )

        event2 = Event(
            name='Городской конкурс чтецов',
            description='Городской этап конкурса художественного чтения',
            level='city',
            event_type='student',
            class_points=0,
            created_by=teacher.id
        )

        event3 = Event(
            name='Субботник',
            description='Общешкольный субботник',
            level='school',
            event_type='class',
            class_points=15,
            created_by=teacher.id
        )

        db.session.add_all([event1, event2, event3])
        db.session.commit()

        flash('База данных инициализирована с тестовыми данными')
    return redirect(url_for('index'))


# ===== МАРШРУТЫ ДЛЯ СБОРА МАКУЛАТУРЫ =====
@app.route('/paper_collection')
@login_required
def paper_collection():
    current_year = datetime.now().year
    """Главная страница сбора макулатуры"""
    if not getattr(current_user, 'role', None) or current_user.role not in ['admin', 'teacher']:
        flash('Недостаточно прав')
        return redirect(url_for('dashboard'))

    # Получаем классы
    if getattr(current_user, 'role', None) == 'teacher' and current_user.managed_class:
        classes = [current_user.managed_class[0]] if current_user.managed_class else []
    else:
        classes = SchoolClass.query.all()

    # Статистика по классам
    class_stats = []
    for class_obj in classes:
        # Общее количество за год
        total_year = db.session.query(db.func.sum(PaperCollection.kilograms)).filter(
            PaperCollection.class_id == class_obj.id,
            PaperCollection.collection_date >= datetime(datetime.now().year, 1, 1).date()
        ).scalar() or 0

        # Количество за последнюю сдачу
        last_collection_date = db.session.query(db.func.max(PaperCollection.collection_date)).filter(
            PaperCollection.class_id == class_obj.id
        ).scalar()

        last_collection_total = 0
        if last_collection_date:
            last_collection_total = db.session.query(db.func.sum(PaperCollection.kilograms)).filter(
                PaperCollection.class_id == class_obj.id,
                PaperCollection.collection_date == last_collection_date
            ).scalar() or 0

        class_stats.append({
            'class': class_obj,
            'total_year': round(total_year, 2),
            'last_collection_total': round(last_collection_total, 2),
            'last_collection_date': last_collection_date
        })

    return render_template('paper_collection/paper_collection.html',
                         classes=classes,
                         class_stats=class_stats,
                         current_year=current_year)


@app.route('/paper_collection/class/<int:class_id>')
@login_required
def paper_collection_class(class_id):
    """Страница сбора макулатуры для конкретного класса"""
    if not getattr(current_user, 'role', None) or current_user.role not in ['admin', 'teacher']:
        flash('Недостаточно прав')
        return redirect(url_for('dashboard'))

    school_class = SchoolClass.query.get_or_404(class_id)

    # Проверяем права доступа для учителя
    if (getattr(current_user, 'role', None) == 'teacher' and
            current_user.managed_class and
            school_class.id not in [c.id for c in current_user.managed_class]):
        flash('У вас нет доступа к этому классу')
        return redirect(url_for('paper_collection'))

    # Получаем даты сбора макулатуры
    collection_dates = db.session.query(PaperCollection.collection_date).filter(
        PaperCollection.class_id == class_id
    ).distinct().order_by(PaperCollection.collection_date.desc()).all()

    collection_dates = [date[0] for date in collection_dates]

    # Получаем данные для выбранной даты или последней даты
    selected_date = request.args.get('date')
    if selected_date:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    elif collection_dates:
        selected_date = collection_dates[0]
    else:
        selected_date = datetime.now().date()

    # Получаем записи для выбранной даты
    collections = PaperCollection.query.filter_by(
        class_id=class_id,
        collection_date=selected_date
    ).all()

    # Создаем словарь для быстрого доступа
    collections_dict = {collection.student_id: collection for collection in collections}

    # Подготавливаем данные для таблицы
    table_data = []
    for student in school_class.students:
        collection = collections_dict.get(student.id)
        table_data.append({
            'student': student,
            'kilograms': collection.kilograms if collection else 0,
            'collection_id': collection.id if collection else None
        })

    # Статистика
    total_today = sum(item['kilograms'] for item in table_data)

    # Общее за год
    total_year = db.session.query(db.func.sum(PaperCollection.kilograms)).filter(
        PaperCollection.class_id == class_id,
        PaperCollection.collection_date >= datetime(datetime.now().year, 1, 1).date()
    ).scalar() or 0

    # Статистика по ученикам за год
    student_year_stats = db.session.query(
        PaperCollection.student_id,
        db.func.sum(PaperCollection.kilograms).label('total_kg')
    ).filter(
        PaperCollection.class_id == class_id,
        PaperCollection.collection_date >= datetime(datetime.now().year, 1, 1).date()
    ).group_by(PaperCollection.student_id).all()

    student_stats_dict = {stat.student_id: stat.total_kg for stat in student_year_stats}

    return render_template('paper_collection/class_collection.html',
                           school_class=school_class,
                           table_data=table_data,
                           collection_dates=collection_dates,
                           selected_date=selected_date,
                           total_today=round(total_today, 2),
                           total_year=round(total_year, 2),
                           student_stats_dict=student_stats_dict)


@app.route('/paper_collection/save', methods=['POST'])
@login_required
def save_paper_collection():
    """Сохранение данных о сборе макулатуры"""
    if not getattr(current_user, 'role', None) or current_user.role not in ['admin', 'teacher']:
        return jsonify({'success': False, 'message': 'Недостаточно прав'})

    class_id = request.form.get('class_id')
    collection_date = request.form.get('collection_date')

    if not class_id or not collection_date:
        return jsonify({'success': False, 'message': 'Отсутствуют обязательные данные'})

    try:
        collection_date = datetime.strptime(collection_date, '%Y-%m-%d').date()
        class_id = int(class_id)
    except ValueError:
        return jsonify({'success': False, 'message': 'Неверный формат данных'})

    # Проверяем права доступа для учителя
    school_class = SchoolClass.query.get(class_id)
    if (getattr(current_user, 'role', None) == 'teacher' and
            current_user.managed_class and
            school_class.id not in [c.id for c in current_user.managed_class]):
        return jsonify({'success': False, 'message': 'У вас нет доступа к этому классу'})

    # Обрабатываем данные учеников
    for key, value in request.form.items():
        if key.startswith('kilograms_'):
            student_id = int(key.replace('kilograms_', ''))
            try:
                kilograms = float(value) if value else 0
            except ValueError:
                continue

            if kilograms > 0:
                # Ищем существующую запись
                existing = PaperCollection.query.filter_by(
                    student_id=student_id,
                    class_id=class_id,
                    collection_date=collection_date
                ).first()

                if existing:
                    # Обновляем существующую запись
                    existing.kilograms = kilograms
                else:
                    # Создаем новую запись
                    collection = PaperCollection(
                        student_id=student_id,
                        class_id=class_id,
                        kilograms=kilograms,
                        collection_date=collection_date,
                        created_by=current_user.id
                    )
                    db.session.add(collection)

    db.session.commit()
    return jsonify({'success': True, 'message': 'Данные успешно сохранены'})


@app.route('/paper_collection/class/<int:class_id>/stats')
@login_required
def paper_collection_stats(class_id):
    """Подробная статистика по сбору макулатуры"""
    if not getattr(current_user, 'role', None) or current_user.role not in ['admin', 'teacher']:
        flash('Недостаточно прав')
        return redirect(url_for('dashboard'))

    school_class = SchoolClass.query.get_or_404(class_id)

    # Проверяем права доступа для учителя
    if (getattr(current_user, 'role', None) == 'teacher' and
            current_user.managed_class and
            school_class.id not in [c.id for c in current_user.managed_class]):
        flash('У вас нет доступа к этому классу')
        return redirect(url_for('paper_collection'))

    # Статистика по месяцам
    monthly_stats = db.session.query(
        db.func.strftime('%Y-%m', PaperCollection.collection_date).label('month'),
        db.func.sum(PaperCollection.kilograms).label('total_kg')
    ).filter(
        PaperCollection.class_id == class_id,
        PaperCollection.collection_date >= datetime(datetime.now().year, 1, 1).date()
    ).group_by('month').order_by('month').all()

    # Топ учеников
    top_students = db.session.query(
        Student,
        db.func.sum(PaperCollection.kilograms).label('total_kg')
    ).join(PaperCollection).filter(
        PaperCollection.class_id == class_id,
        PaperCollection.collection_date >= datetime(datetime.now().year, 1, 1).date()
    ).group_by(Student.id).order_by(db.desc('total_kg')).limit(10).all()

    # Общая статистика
    total_year = db.session.query(db.func.sum(PaperCollection.kilograms)).filter(
        PaperCollection.class_id == class_id,
        PaperCollection.collection_date >= datetime(datetime.now().year, 1, 1).date()
    ).scalar() or 0

    collection_days = db.session.query(PaperCollection.collection_date).filter(
        PaperCollection.class_id == class_id,
        PaperCollection.collection_date >= datetime(datetime.now().year, 1, 1).date()
    ).distinct().count()
    current_year = datetime.now().year
    avg_per_day = total_year / collection_days if collection_days > 0 else 0

    return render_template('paper_collection/class_stats.html',
                         school_class=school_class,
                         monthly_stats=monthly_stats,
                         top_students=top_students,
                         total_year=round(total_year, 2),
                         collection_days=collection_days,
                         avg_per_day=round(avg_per_day, 2),
                         current_year=current_year)
with app.app_context():
    try:
        # Проверяем существование таблицы paper_collections
        result = db.session.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_collections'")
        if not result.fetchone():
            print("Создание таблицы для макулатуры...")
            db.create_all()
            print("Таблица paper_collections создана")
    except Exception as e:
        print(f"Ошибка при проверке таблицы макулатуры: {e}")
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host ='0.0.0.0')