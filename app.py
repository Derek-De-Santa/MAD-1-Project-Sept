from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask import abort
from models import db, User, ExaminerProfile, Course, Examination, ExaminationSlot, Booking

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

@app.route('/examiner/dashboard')
@login_required
@role_required('Examiner')
def examiner_dashboard():
    """
    Examiner dashboard displaying assigned tasks and evaluations.
    """
    profile = current_user.examiner_profile
    
    # Needs Admin's approval to access the dashboard
    if profile and profile.status != 'Approved':
        flash('Your account is pending Admin approval. You cannot access the dashboard yet.', 'warning')
        return redirect(url_for('login'))
        
    slots = ExaminationSlot.query.filter_by(examiner_id=current_user.id).all()
    
    stats = {
        'created_slots': len(slots),
        'booked_students': sum(slot.max_student_capacity - slot.available_seats for slot in slots),
        'pending_evaluations': 0 # To be calculated later based on bookings without evaluations
    }
    return render_template('examiner/examiner_dashboard.html', stats=stats)

@app.route('/student/dashboard')
@login_required
@role_required('Student')
def student_dashboard():
    """
    Student dashboard displaying available exams and booking history.
    """
    bookings = Booking.query.filter_by(student_id=current_user.id).all()
    
    stats = {
        'booked_slots': len(bookings),
        'available_examinations': Examination.query.filter_by(status='Booking Open').count(),
        'published_results': 0 # To be queried later from Evaluation table
    }
    return render_template('student/student_dashboard.html', stats=stats, bookings=bookings)

if __name__ == '__main__':
    app.run(debug=True)