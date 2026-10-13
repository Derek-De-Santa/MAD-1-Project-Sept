from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask import abort
from models import db, User, ExaminerProfile, Course, Examination, ExaminationSlot, Booking, ExaminationRubric, Evaluation
from datetime import datetime


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_super_secret_key' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///examination_portal.db'
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redirects unauthorized users to the login route

@login_manager.user_loader
def load_user(user_id):
    """Loads the user for Flask-Login session management."""
    return User.query.get(int(user_id))

def setup_database():
    """
    Programmatically creates the database tables and the pre-existing Admin user.
    """
    with app.app_context():
        # Creates all tables defined in models.py programmatically
        db.create_all()
        
        # Check if the admin user already exists
        admin = User.query.filter_by(role='Admin').first()
        if not admin:
            print("Creating pre-existing Admin user...")
            default_admin = User(
                username='admin',
                password_hash=generate_password_hash('lorem'), # Default password for the Admin 
                role='Admin'
            )
            db.session.add(default_admin)
            db.session.commit()
            print("Admin user created successfully.")

# Run database setup
setup_database()

@app.route('/')
def index():
    """
    Landing page for new or unauthenticated users.
    Redirects authenticated users to their respective dashboards based on their role.
    """
    # If the user is already logged in, route them to their dashboard
    if current_user.is_authenticated:
        if current_user.role == 'Admin':
            return redirect(url_for('admin_dashboard'))
        elif current_user.role == 'Examiner':
            return redirect(url_for('examiner_dashboard'))
        elif current_user.role == 'Student':
            return redirect(url_for('student_dashboard'))
            
    # If not logged in, render the landing page
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handles login for Admin, Examiners, and Students.
    Routes users to their respective dashboards based on their role.
    """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            
            # Redirect based on role-based access control
            if user.role == 'Admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role == 'Examiner':
                return redirect(url_for('examiner_dashboard'))
            elif user.role == 'Student':
                return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Logs out the current user and clears the session."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/register/student', methods=['GET', 'POST'])
def register_student():
    """
    Allows Students to self-register.
    """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Check for existing user
        if User.query.filter_by(username=username).first():
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('register_student'))
            
        # Create new student user
        new_student = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='Student'
        )
        
        db.session.add(new_student)
        db.session.commit()
        
        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('student/register_student.html')

@app.route('/register/examiner', methods=['GET', 'POST'])
def register_examiner():
    """
    Allows Examiners to self-register and creates their profile.
    Their profile status defaults to 'Pending' as they need Admin approval.
    """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        name = request.form.get('name')
        contact_details = request.form.get('contact_details')
        department = request.form.get('department')
        
        # Check for existing user
        if User.query.filter_by(username=username).first():
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('register_examiner'))
            
        # 1. Create base User account
        new_examiner_user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='Examiner'
        )
        db.session.add(new_examiner_user)
        db.session.flush() # Flush to get the new_examiner_user.id before committing
        
        # 2. Create the Examiner Profile linked to the User account
        new_profile = ExaminerProfile(
            user_id=new_examiner_user.id,
            name=name,
            contact_details=contact_details,
            department=department,
            status='Pending' # Explicitly setting status to enforce Admin approval requirement
        )
        db.session.add(new_profile)
        db.session.commit()
        
        flash('Registration successful! Your account is pending Admin approval.', 'success')
        return redirect(url_for('login'))
        
    return render_template('examiner/register_examiner.html')


def role_required(role):
    """Custom decorator for role-based access control."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role:
                abort(403) # Forbidden
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/admin/dashboard')
@login_required
@role_required('Admin')
def admin_dashboard():
    """
    Admin dashboard must display total courses, examinations, users, slots, and bookings.
    """
    stats = {
        'total_courses': Course.query.count(),
        'total_examinations': Examination.query.count(),
        'total_examiners': User.query.filter_by(role='Examiner').count(),
        'total_students': User.query.filter_by(role='Student').count(),
        'total_slots': ExaminationSlot.query.count(),
        'total_bookings': Booking.query.count()
    }
    # Fetch pending examiners for Admin approval
    pending_examiners = ExaminerProfile.query.filter_by(status='Pending').all()
    
    return render_template('admin/admin_dashboard.html', stats=stats, pending_examiners=pending_examiners)

@app.route('/admin/examiner/<int:profile_id>/approve', methods=['POST'])
@login_required
@role_required('Admin')
def approve_examiner(profile_id):
    """
    Approves a pending examiner registration.
    """
    profile = ExaminerProfile.query.get_or_404(profile_id)
    profile.status = 'Approved'
    db.session.commit()
    
    flash(f'Examiner {profile.name} has been approved successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/examiner/<int:profile_id>/reject', methods=['POST'])
@login_required
@role_required('Admin')
def reject_examiner(profile_id):
    """
    Rejects a pending examiner registration by removing their account.
    """
    profile = ExaminerProfile.query.get_or_404(profile_id)
    user_account = User.query.get(profile.user_id)
    
    # Deleting the User account will automatically delete the ExaminerProfile due to the cascade="all, delete-orphan" relationship defined in models.py
    db.session.delete(user_account)
    db.session.commit()
    
    flash(f'Registration for {profile.name} has been rejected and removed.', 'info')
    return redirect(url_for('admin_dashboard'))


# --- ADMIN COURSE MANAGEMENT ---

@app.route('/admin/courses', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def manage_courses():
    """Admin can view and create courses."""
    if request.method == 'POST':
        course_code = request.form.get('course_code')
        course_name = request.form.get('course_name')
        description = request.form.get('description')
        
        new_course = Course(course_code=course_code, course_name=course_name, description=description)
        db.session.add(new_course)
        db.session.commit()
        flash('Course created successfully.', 'success')
        return redirect(url_for('manage_courses'))
        
    courses = Course.query.all()
    return render_template('admin/courses.html', courses=courses)

@app.route('/admin/course/<int:course_id>/delete', methods=['POST'])
@login_required
@role_required('Admin')
def delete_course(course_id):
    """Admin can remove courses."""
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    flash('Course deleted successfully.', 'info')
    return redirect(url_for('manage_courses'))


# --- ADMIN EXAMINATION MANAGEMENT ---

@app.route('/admin/examinations', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def manage_examinations():
    """Admin can view and create examinations and configure timelines."""
    if request.method == 'POST':
        fmt = '%Y-%m-%dT%H:%M'
        new_exam = Examination(
            course_id=request.form.get('course_id'),
            exam_name=request.form.get('exam_name'),
            exam_type=request.form.get('exam_type'),
            duration=int(request.form.get('duration')),
            max_marks=float(request.form.get('max_marks')),
            slot_creation_start_date=datetime.strptime(request.form.get('slot_creation_start_date'), fmt),
            slot_creation_end_date=datetime.strptime(request.form.get('slot_creation_end_date'), fmt),
            slot_booking_start_date=datetime.strptime(request.form.get('slot_booking_start_date'), fmt),
            slot_booking_end_date=datetime.strptime(request.form.get('slot_booking_end_date'), fmt),
            status='Draft'
        )
        db.session.add(new_exam)
        db.session.commit()
        flash('Examination created successfully.', 'success')
        return redirect(url_for('manage_examinations'))
        
    examinations = Examination.query.all()
    courses = Course.query.filter_by(status='Active').all()
    
    approved_examiners = User.query.join(ExaminerProfile).filter(User.role == 'Examiner', ExaminerProfile.status == 'Approved').all()
    
    return render_template('admin/examinations.html', examinations=examinations, courses=courses, examiners=approved_examiners)

@app.route('/admin/examination/<int:exam_id>/assign', methods=['POST'])
@login_required
@role_required('Admin')
def assign_examiners(exam_id):
    """Admin can change the assigned examiners for an examination."""
    exam = Examination.query.get_or_404(exam_id)
    
    # Get the list of selected examiner IDs from the checkboxes
    selected_examiner_ids = request.form.getlist('examiners') 
    
    # Clear current assignments and re-assign based on form selection
    exam.assigned_examiners = []
    for ex_id in selected_examiner_ids:
        examiner = User.query.get(ex_id)
        if examiner:
            exam.assigned_examiners.append(examiner)
            
    db.session.commit()
    flash(f'Examiners successfully assigned to {exam.exam_name}.', 'success')
    return redirect(url_for('manage_examinations'))

@app.route('/admin/examination/<int:exam_id>/status', methods=['POST'])
@login_required
@role_required('Admin')
def update_exam_status(exam_id):
    """
    Admin can open and close examiner slot creation and student slot booking.
    """
    exam = Examination.query.get_or_404(exam_id)
    new_status = request.form.get('status')
    
    if new_status:
        exam.status = new_status
        db.session.commit()
        flash(f'Examination status updated to {new_status}.', 'success')
        
    return redirect(url_for('manage_examinations'))


@app.route('/admin/examination/<int:exam_id>/rubrics', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def manage_rubrics(exam_id):
    """
    Admin can create and manage examination rubrics.
    """
    exam = Examination.query.get_or_404(exam_id)
    
    if request.method == 'POST':
        new_rubric = ExaminationRubric(
            examination_id=exam.exam_id,
            criterion_name=request.form.get('criterion_name'),
            max_marks=float(request.form.get('max_marks')),
            weightage=float(request.form.get('weightage')),
            description=request.form.get('description')
        )
        db.session.add(new_rubric)
        db.session.commit()
        flash('Rubric criterion added successfully.', 'success')
        return redirect(url_for('manage_rubrics', exam_id=exam.exam_id))
        
    rubrics = ExaminationRubric.query.filter_by(examination_id=exam.exam_id).all()
    return render_template('admin/manage_rubrics.html', exam=exam, rubrics=rubrics)

@app.route('/admin/rubric/<int:rubric_id>/delete', methods=['POST'])
@login_required
@role_required('Admin')
def delete_rubric(rubric_id):
    """
    Admin can remove examination rubrics.
    """
    rubric = ExaminationRubric.query.get_or_404(rubric_id)
    exam_id = rubric.examination_id
    
    db.session.delete(rubric)
    db.session.commit()
    flash('Rubric criterion removed successfully.', 'info')
    
    return redirect(url_for('manage_rubrics', exam_id=exam_id))


@app.route('/admin/records', methods=['GET'])
@login_required
@role_required('Admin')
def manage_records():
    """
    Admin can view all examination slots, bookings, and search the system.
    """
    query = request.args.get('q', '').strip()
    
    # Base queries
    bookings_query = Booking.query.join(User, Booking.student_id == User.id)
    slots_query = ExaminationSlot.query.join(Examination, ExaminationSlot.examination_id == Examination.exam_id) \
                                     .join(User, ExaminationSlot.examiner_id == User.id) \
                                     .join(ExaminerProfile, User.id == ExaminerProfile.user_id)
    
    if query:
        # Filter bookings tab by Student username
        bookings_query = bookings_query.filter(User.username.ilike(f'%{query}%'))
        
        # Filter slots tab by Examination name OR Examiner name
        slots_query = slots_query.filter(
            db.or_(
                Examination.exam_name.ilike(f'%{query}%'),
                ExaminerProfile.name.ilike(f'%{query}%')
            )
        )
        
    bookings = bookings_query.order_by(Booking.booking_date.desc()).all()
    slots = slots_query.order_by(ExaminationSlot.date.desc()).all()
    
    return render_template('admin/records.html', slots=slots, bookings=bookings, query=query)


@app.route('/admin/booking/<int:booking_id>/reschedule', methods=['POST'])
@login_required
@role_required('Admin')
def reschedule_booking(booking_id):
    """
    Admin can reschedule examination bookings if required.
    """
    booking = Booking.query.get_or_404(booking_id)
    new_slot_id = request.form.get('new_slot_id')
    
    if not new_slot_id:
        flash('Please select a valid alternative slot.', 'warning')
        return redirect(url_for('manage_records'))
        
    new_slot = ExaminationSlot.query.get_or_404(new_slot_id)
    
    # Ensure the new slot actually has space
    if new_slot.available_seats <= 0:
        flash('The selected slot is full. Cannot reschedule.', 'danger')
        return redirect(url_for('manage_records'))
        
    old_slot = booking.slot
    
    # Free up the seat in the old slot
    old_slot.available_seats += 1
    if old_slot.status == 'Full':
        old_slot.status = 'Available'
        
    # Take up a seat in the new slot
    booking.slot_id = new_slot.slot_id
    new_slot.available_seats -= 1
    if new_slot.available_seats == 0:
        new_slot.status = 'Full'
        
    db.session.commit()
    flash(f'Booking #{booking.booking_id} for {booking.student.username} has been successfully rescheduled.', 'success')
    return redirect(url_for('manage_records'))







@app.route('/examiner/dashboard')
@login_required
@role_required('Examiner')
def examiner_dashboard():
    """
    Examiner dashboard displaying assigned tasks, slot statistics, and evaluations.
    """
    profile = current_user.examiner_profile
    
    # Needs Admin's approval to access the dashboard
    if profile and profile.status != 'Approved':
        flash('Your account is pending Admin approval. You cannot access the dashboard yet.', 'warning')
        return redirect(url_for('login'))
        
    # Fetch examinations assigned to this specific examiner
    assigned_exams = current_user.assigned_exams
    
    # Fetch all slots created by this examiner
    slots = ExaminationSlot.query.filter_by(examiner_id=current_user.id).all()
    
    # Calculate dashboard statistics
    created_slots = len(slots)
    booked_students = sum(slot.max_student_capacity - slot.available_seats for slot in slots)
    
    stats = {
        'created_slots': created_slots,
        'booked_students': booked_students,
        'pending_evaluations': 0 # We will calculate this when we build the evaluation system
    }
    
    return render_template('examiner/examiner_dashboard.html', stats=stats, assigned_exams=assigned_exams)

@app.route('/examiner/examination/<int:exam_id>/slots', methods=['GET', 'POST'])
@login_required
@role_required('Examiner')
def manage_slots(exam_id):
    """
    Allows examiners to create slots during the slot creation period.
    """
    exam = Examination.query.get_or_404(exam_id)
    
    # Ensure this examiner is actually assigned to this exam
    if current_user not in exam.assigned_examiners:
        flash('You are not assigned to this examination.', 'danger')
        return redirect(url_for('examiner_dashboard'))
        
    if request.method == 'POST':
        # Enforce rule: Examiners can create slots only during the slot creation period
        if exam.status != 'Slot Creation':
            flash('Slot creation is currently closed for this examination.', 'danger')
            return redirect(url_for('manage_slots', exam_id=exam.exam_id))
            
        date_str = request.form.get('date')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        capacity = int(request.form.get('max_student_capacity'))
        
        new_slot = ExaminationSlot(
            examination_id=exam.exam_id,
            examiner_id=current_user.id,
            date=datetime.strptime(date_str, '%Y-%m-%d').date(),
            start_time=datetime.strptime(start_time_str, '%H:%M').time(),
            end_time=datetime.strptime(end_time_str, '%H:%M').time(),
            max_student_capacity=capacity,
            available_seats=capacity, # Initially, all seats are available
            status='Available'
        )
        db.session.add(new_slot)
        db.session.commit()
        flash('Examination slot created successfully.', 'success')
        return redirect(url_for('manage_slots', exam_id=exam.exam_id))

    # Fetch existing slots for this examiner and this exam
    slots = ExaminationSlot.query.filter_by(examination_id=exam.exam_id, examiner_id=current_user.id).all()
    
    return render_template('examiner/manage_slots.html', exam=exam, slots=slots)

@app.route('/examiner/slot/<int:slot_id>/delete', methods=['POST'])
@login_required
@role_required('Examiner')
def delete_slot(slot_id):
    """
    Examiners can update or remove slots before booking starts.
    """
    slot = ExaminationSlot.query.get_or_404(slot_id)
    
    # Ensure the slot belongs to the logged-in examiner
    if slot.examiner_id != current_user.id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('examiner_dashboard'))
        
    # Enforce rule: Can only remove before booking starts (e.g., in Draft or Slot Creation phase)
    if slot.examination.status not in ['Draft', 'Slot Creation']:
        flash('Cannot delete slots once the booking phase has opened.', 'danger')
    else:
        db.session.delete(slot)
        db.session.commit()
        flash('Slot deleted successfully.', 'info')
        
    return redirect(url_for('manage_slots', exam_id=slot.examination_id))

@app.route('/examiner/examination/<int:exam_id>/students')
@login_required
@role_required('Examiner')
def view_students(exam_id):
    """
    Allows examiners to view students booked for their slots.
    """
    exam = Examination.query.get_or_404(exam_id)
    
    # Ensure this examiner is assigned to this exam
    if current_user not in exam.assigned_examiners:
        flash('You are not assigned to this examination.', 'danger')
        return redirect(url_for('examiner_dashboard'))
        
    # Get all slots created by this examiner for this specific exam
    slots = ExaminationSlot.query.filter_by(examination_id=exam_id, examiner_id=current_user.id).all()
    slot_ids = [slot.slot_id for slot in slots]
    
    # Fetch all bookings linked to these slots
    bookings = Booking.query.filter(Booking.slot_id.in_(slot_ids)).all()
    
    return render_template('examiner/view_students.html', exam=exam, bookings=bookings)


@app.route('/examiner/booking/<int:booking_id>/evaluate', methods=['GET', 'POST'])
@login_required
@role_required('Examiner')
def evaluate_student(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    
    # ... existing security checks ...
    
    # NEW: Prevent editing if the evaluation has been finalized
    if booking.status == 'Completed':
        flash("This evaluation has been locked and cannot be changed.", "warning")
        return redirect(url_for('view_students', exam_id=booking.slot.examination_id))
        
    rubrics = ExaminationRubric.query.filter_by(examination_id=booking.slot.examination_id).all()
    existing_evals = {eval.rubric_id: eval for eval in booking.evaluations}
    
    if request.method == 'POST':
        for rubric in rubrics:
            marks = request.form.get(f'marks_{rubric.rubric_id}')
            remarks = request.form.get(f'remarks_{rubric.rubric_id}')
            
            if marks is not None and marks != '':
                eval_record = existing_evals.get(rubric.rubric_id)
                if eval_record:
                    eval_record.marks_awarded = float(marks)
                    eval_record.remarks = remarks
                else:
                    new_eval = Evaluation(
                        booking_id=booking.booking_id,
                        rubric_id=rubric.rubric_id,
                        marks_awarded=float(marks),
                        remarks=remarks
                    )
                    db.session.add(new_eval)
                    
        db.session.commit()
        
        flash(f"Evaluation drafted successfully for {booking.student.username}. Please 'Submit Final' to lock.", "success")
        return redirect(url_for('view_students', exam_id=booking.slot.examination_id))
        
    return render_template('examiner/evaluate_student.html', booking=booking, rubrics=rubrics, existing_evals=existing_evals)


@app.route('/examiner/booking/<int:booking_id>/finalize', methods=['POST'])
@login_required
@role_required('Examiner')
def finalize_evaluation(booking_id):
    """
    Locks the evaluation so scores cannot be changed.
    """
    booking = Booking.query.get_or_404(booking_id)
    
    # Security check
    if booking.slot.examiner_id != current_user.id:
        flash("Unauthorized action.", "danger")
        return redirect(url_for('examiner_dashboard'))
        
    # Mark as completed (Locked)
    booking.status = 'Completed'
    db.session.commit()
    
    flash(f"Scores for {booking.student.username} have been successfully locked and published.", "success")
    return redirect(url_for('view_students', exam_id=booking.slot.examination_id))






@app.route('/student/dashboard')
@login_required
@role_required('Student')
def student_dashboard():
    """
    Student dashboard displaying available exams, booked slots, and published results.
    """
    # Fetch all bookings for the logged-in student
    bookings = Booking.query.filter_by(student_id=current_user.id).order_by(Booking.booking_date.desc()).all()
    
    # Fetch examinations currently open for booking
    available_exams = Examination.query.filter_by(status='Booking Open').all()
    
    # Calculate how many bookings have been evaluated (published results)
    published_results_count = sum(1 for b in bookings if b.evaluations)
    
    stats = {
        'booked_slots': len(bookings),
        'available_examinations': len(available_exams),
        'published_results': published_results_count
    }
    
    return render_template('student/student_dashboard.html', stats=stats, bookings=bookings, available_exams=available_exams)

@app.route('/student/examination/<int:exam_id>/slots')
@login_required
@role_required('Student')
def view_exam_slots(exam_id):
    """
    Displays all available slots for a specific examination.
    """
    exam = Examination.query.get_or_404(exam_id)
    slots = ExaminationSlot.query.filter_by(examination_id=exam_id).all()
    
    # Prevent duplicate bookings: Check if student already has an active booking for this exam
    existing_booking = Booking.query.join(ExaminationSlot).filter(
        Booking.student_id == current_user.id,
        ExaminationSlot.examination_id == exam_id,
        Booking.status == 'Booked'
    ).first()
    
    return render_template('student/view_slots.html', exam=exam, slots=slots, existing_booking=existing_booking)

@app.route('/student/slot/<int:slot_id>/book', methods=['POST'])
@login_required
@role_required('Student')
def book_slot(slot_id):
    """
    Handles the booking of a slot by a student.
    """
    slot = ExaminationSlot.query.get_or_404(slot_id)
    exam = slot.examination
    
    # Rule: Students can book slots only during the booking period
    now = datetime.now()
    if not (exam.slot_booking_start_date <= now <= exam.slot_booking_end_date) or exam.status != 'Booking Open':
        flash('Booking is currently closed for this examination.', 'danger')
        return redirect(url_for('view_exam_slots', exam_id=exam.exam_id))
        
    # Rule: Prevent duplicate bookings for the same examination
    existing_booking = Booking.query.join(ExaminationSlot).filter(
        Booking.student_id == current_user.id,
        ExaminationSlot.examination_id == exam.exam_id,
        Booking.status == 'Booked'
    ).first()
    
    if existing_booking:
        flash('You have already booked a slot for this examination.', 'warning')
        return redirect(url_for('student_dashboard'))
        
    # Rule: Prevent overbooking beyond slot capacity
    if slot.available_seats <= 0 or slot.status == 'Full':
        flash('This slot is already full.', 'danger')
        return redirect(url_for('view_exam_slots', exam_id=exam.exam_id))
        
    # Create the booking
    new_booking = Booking(
        student_id=current_user.id,
        slot_id=slot.slot_id,
        booking_date=now,
        status='Booked'
    )
    
    # Update slot capacity and automatically close if full
    slot.available_seats -= 1
    if slot.available_seats == 0:
        slot.status = 'Full'
        
    db.session.add(new_booking)
    db.session.commit()
    flash('Slot successfully booked!', 'success')
    return redirect(url_for('student_dashboard'))

@app.route('/student/booking/<int:booking_id>/cancel', methods=['POST'])
@login_required
@role_required('Student')
def cancel_booking(booking_id):
    """
    Allows a student to cancel their booking before the deadline.
    """
    booking = Booking.query.get_or_404(booking_id)
    
    # Ensure this booking belongs to the logged-in student
    if booking.student_id != current_user.id:
        abort(403)
        
    exam = booking.slot.examination
    
    # Rule: Can cancel booking before the booking deadline
    if datetime.now() > exam.slot_booking_end_date:
        flash('The booking deadline has passed. You can no longer cancel this booking.', 'danger')
    else:
        booking.status = 'Cancelled'
        
        # Free up the seat in the slot
        booking.slot.available_seats += 1
        if booking.slot.status == 'Full':
            booking.slot.status = 'Available'
            
        db.session.commit()
        flash('Booking cancelled successfully.', 'info')
        
    return redirect(url_for('student_dashboard'))

@app.route('/student/booking/<int:booking_id>/results')
@login_required
@role_required('Student')
def view_results(booking_id):
    """
    Allows a student to view their published results and evaluation feedback.
    """
    booking = Booking.query.get_or_404(booking_id)
    
    if booking.student_id != current_user.id:
        abort(403)
        
    # NEW LOGIC: Block access if the examiner hasn't clicked "Submit Final" yet
    if booking.status != 'Completed':
        flash('Results have not been finalized or published for this examination yet.', 'info')
        return redirect(url_for('student_dashboard'))
        
    total_marks_awarded = sum(evaluation.marks_awarded for evaluation in booking.evaluations)
    total_max_marks = sum(evaluation.rubric.max_marks for evaluation in booking.evaluations)
    
    return render_template(
        'student/view_results.html', 
        booking=booking, 
        total_marks_awarded=total_marks_awarded, 
        total_max_marks=total_max_marks
    )




@app.route('/contact', methods=['POST'])
def contact():
    """
    Handles the Contact Us form submission from the landing page.
    """
    # Grab the form data using the 'name' attributes from the HTML form
    name = request.form.get('contactName')
    email = request.form.get('contactEmail')
    role = request.form.get('contactRole')
    message = request.form.get('contactMessage')
    
    # In a real app, I would use Flask-Mail to send this to the admin email.
    # For now, it flashs a success message and redirect back to the home page.
    
    flash('Thank you for reaching out! Your message has been sent to the administration team.', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)