from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from datetime import datetime, timezone

db = SQLAlchemy()

class User(db.Model, UserMixin):
    """
    Handles authentication and role-based access for Admin, Examiners, and Students.
    """
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'Admin', 'Examiner', 'Student'
    
    # Relationships
    examiner_profile = db.relationship('ExaminerProfile', backref='user', uselist=False, cascade="all, delete-orphan")
    slots = db.relationship('ExaminationSlot', backref='examiner', lazy=True)
    bookings = db.relationship('Booking', backref='student', lazy=True)

class ExaminerProfile(db.Model):
    """
    Details of a registered examiner.
    """
    __tablename__ = 'examiner_profiles'
    
    examiner_id = db.Column(db.Integer, primary_key=True) # Maps to Examiner ID
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    contact_details = db.Column(db.String(150), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='Pending') # Pending, Approved, Deactivated

class Course(db.Model):
    """
    A course under which one or more examinations are conducted.
    """
    __tablename__ = 'courses'
    
    course_id = db.Column(db.Integer, primary_key=True)
    course_code = db.Column(db.String(20), unique=True, nullable=False)
    course_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Active') # Active, Inactive
    
    # Relationships
    examinations = db.relationship('Examination', backref='course', lazy=True, cascade="all, delete-orphan")

class Examination(db.Model):
    """
    An examination created by the Admin for a particular course.
    """
    __tablename__ = 'examinations'
    
    exam_id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.course_id'), nullable=False)
    exam_name = db.Column(db.String(100), nullable=False)
    exam_type = db.Column(db.String(50), nullable=False) # Viva, Practical, Project Demo, Assessment
    duration = db.Column(db.Integer, nullable=False) # Duration in minutes
    max_marks = db.Column(db.Float, nullable=False)
    
    # Timelines
    slot_creation_start_date = db.Column(db.DateTime, nullable=False)
    slot_creation_end_date = db.Column(db.DateTime, nullable=False)
    slot_booking_start_date = db.Column(db.DateTime, nullable=False)
    slot_booking_end_date = db.Column(db.DateTime, nullable=False)
    
    status = db.Column(db.String(20), default='Draft') # Draft, Slot Creation, Booking Open, Closed, Completed
    
    # Relationships
    rubrics = db.relationship('ExaminationRubric', backref='examination', lazy=True, cascade="all, delete-orphan")
    slots = db.relationship('ExaminationSlot', backref='examination', lazy=True, cascade="all, delete-orphan")

class ExaminationRubric(db.Model):
    """
    Defines the evaluation criteria for an examination.
    """
    __tablename__ = 'examination_rubrics'
    
    rubric_id = db.Column(db.Integer, primary_key=True)
    examination_id = db.Column(db.Integer, db.ForeignKey('examinations.exam_id'), nullable=False)
    criterion_name = db.Column(db.String(100), nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    weightage = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    # Relationships
    evaluations = db.relationship('Evaluation', backref='rubric', lazy=True)

class ExaminationSlot(db.Model):
    """
    A time slot created by an examiner.
    """
    __tablename__ = 'examination_slots'
    
    slot_id = db.Column(db.Integer, primary_key=True)
    examination_id = db.Column(db.Integer, db.ForeignKey('examinations.exam_id'), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False) 
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    max_student_capacity = db.Column(db.Integer, nullable=False)
    available_seats = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='Available') # Available, Full, Cancelled, Completed
    
    # Relationships
    bookings = db.relationship('Booking', backref='slot', lazy=True)

class Booking(db.Model):
    """
    A record of a student booking an examination slot.
    """
    __tablename__ = 'bookings'
    
    booking_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey('examination_slots.slot_id'), nullable=False)
    booking_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(20), default='Booked') # Booked, Cancelled, Completed
    
    # Relationships
    evaluations = db.relationship('Evaluation', backref='booking', lazy=True, cascade="all, delete-orphan")

class Evaluation(db.Model):
    """
    Handles evaluating students using rubrics and submitting marks and remarks.
    """
    __tablename__ = 'evaluations'
    
    evaluation_id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.booking_id'), nullable=False)
    rubric_id = db.Column(db.Integer, db.ForeignKey('examination_rubrics.rubric_id'), nullable=False)
    marks_awarded = db.Column(db.Float, nullable=False)
    remarks = db.Column(db.Text, nullable=True)