from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime
from models import db, User, Donation, Request, Task, ActivityLog, get_platform_stats

app = Flask(__name__)
app.config['SECRET_KEY'] = 'social-mentor-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///social_mentor.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create tables
with app.app_context():
    db.create_all()

# ==================== PUBLIC ROUTES ====================

@app.route('/')
def index():
    stats = get_platform_stats()
    recent_donations = Donation.query.order_by(Donation.created_at.desc()).limit(5).all()
    return render_template('index.html', stats=stats, recent_donations=recent_donations)

@app.route('/impact')
def impact():
    stats = get_platform_stats()
    # Get recent completed tasks with details
    completed_tasks = Task.query.filter_by(status='delivered').order_by(Task.delivered_at.desc()).limit(20).all()
    # Get top volunteers
    top_volunteers = User.query.filter_by(role='volunteer').order_by(User.points.desc()).limit(10).all()
    # Get top donors
    top_donors = User.query.filter_by(role='donor').order_by(User.points.desc()).limit(10).all()
    return render_template('impact.html', stats=stats, completed_tasks=completed_tasks, 
                          top_volunteers=top_volunteers, top_donors=top_donors)

# ==================== AUTH ROUTES ====================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        location = request.form.get('location')
        phone = request.form.get('phone')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        
        user = User(name=name, email=email, role=role, location=location, phone=phone)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'donor':
        return redirect(url_for('donor_dashboard'))
    elif current_user.role == 'volunteer':
        return redirect(url_for('volunteer_dashboard'))
    else:
        return redirect(url_for('receiver_dashboard'))

# ==================== DONOR ROUTES ====================

@app.route('/donor/dashboard')
@login_required
def donor_dashboard():
    if current_user.role != 'donor':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    my_donations = Donation.query.filter_by(donor_id=current_user.id).order_by(Donation.created_at.desc()).all()
    active_donations = [d for d in my_donations if d.status != 'completed']
    completed_donations = [d for d in my_donations if d.status == 'completed']
    
    # Calculate impact
    total_items = sum(d.quantity for d in completed_donations)
    
    return render_template('donor/dashboard.html', 
                          donations=my_donations,
                          active_donations=active_donations,
                          completed_donations=completed_donations,
                          total_items=total_items)

@app.route('/donor/create', methods=['GET', 'POST'])
@login_required
def create_donation():
    if current_user.role != 'donor':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        donation = Donation(
            donor_id=current_user.id,
            item_type=request.form.get('item_type'),
            quantity=int(request.form.get('quantity')),
            condition=request.form.get('condition'),
            description=request.form.get('description'),
            location=request.form.get('location') or current_user.location,
            pickup_address=request.form.get('pickup_address')
        )
        
        expiry = request.form.get('expiry_date')
        if expiry:
            donation.expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
        
        db.session.add(donation)
        
        # Create a task for this donation
        task = Task(donation_id=donation.id)
        db.session.add(task)
        
        # Add points to donor
        current_user.add_points(10)
        
        db.session.commit()
        
        # Log activity
        log = ActivityLog(task_id=task.id, action=f'Donation created by {current_user.name}', actor_id=current_user.id)
        db.session.add(log)
        db.session.commit()
        
        flash('Donation created successfully! +10 points', 'success')
        return redirect(url_for('donor_dashboard'))
    
    return render_template('donor/create_donation.html')

# ==================== VOLUNTEER ROUTES ====================

@app.route('/volunteer/dashboard')
@login_required
def volunteer_dashboard():
    if current_user.role != 'volunteer':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    # Get nearby tasks (same location)
    nearby_tasks = Task.query.join(Donation).filter(
        Task.status == 'created',
        Task.volunteer_id == None,
        Donation.location == current_user.location
    ).all()
    
    # Also get tasks from other locations
    other_tasks = Task.query.join(Donation).filter(
        Task.status == 'created',
        Task.volunteer_id == None,
        Donation.location != current_user.location
    ).limit(10).all()
    
    # My active tasks
    my_tasks = Task.query.filter(
        Task.volunteer_id == current_user.id,
        Task.status.in_(['assigned', 'picked_up'])
    ).all()
    
    # Completed tasks
    completed_tasks = Task.query.filter(
        Task.volunteer_id == current_user.id,
        Task.status == 'delivered'
    ).order_by(Task.delivered_at.desc()).limit(10).all()
    
    return render_template('volunteer/dashboard.html',
                          nearby_tasks=nearby_tasks,
                          other_tasks=other_tasks,
                          my_tasks=my_tasks,
                          completed_tasks=completed_tasks)

@app.route('/volunteer/accept/<int:task_id>')
@login_required
def accept_task(task_id):
    if current_user.role != 'volunteer':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    task = Task.query.get_or_404(task_id)
    
    if task.volunteer_id:
        flash('Task already assigned', 'error')
        return redirect(url_for('volunteer_dashboard'))
    
    task.volunteer_id = current_user.id
    task.status = 'assigned'
    task.assigned_at = datetime.utcnow()
    
    # Update donation status
    task.donation.status = 'matched'
    
    # Log activity
    log = ActivityLog(task_id=task.id, action=f'Task accepted by volunteer {current_user.name}', actor_id=current_user.id)
    db.session.add(log)
    
    db.session.commit()
    flash('Task accepted! Please proceed with pickup.', 'success')
    return redirect(url_for('volunteer_dashboard'))

@app.route('/volunteer/update/<int:task_id>/<status>')
@login_required
def update_task(task_id, status):
    if current_user.role != 'volunteer':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    task = Task.query.get_or_404(task_id)
    
    if task.volunteer_id != current_user.id:
        flash('Not your task', 'error')
        return redirect(url_for('volunteer_dashboard'))
    
    if status == 'picked_up':
        task.status = 'picked_up'
        task.picked_up_at = datetime.utcnow()
        log_action = f'Items picked up by {current_user.name}'
    elif status == 'delivered':
        task.status = 'delivered'
        task.delivered_at = datetime.utcnow()
        task.donation.status = 'completed'
        
        # Award points
        current_user.add_points(15)
        
        # If there's a matched request, update it too
        if task.request_id:
            task.request.status = 'fulfilled'
        
        log_action = f'Items delivered by {current_user.name}'
        flash('Delivery completed! +15 points', 'success')
    else:
        flash('Invalid status', 'error')
        return redirect(url_for('volunteer_dashboard'))
    
    # Log activity
    log = ActivityLog(task_id=task.id, action=log_action, actor_id=current_user.id)
    db.session.add(log)
    
    db.session.commit()
    return redirect(url_for('volunteer_dashboard'))

@app.route('/volunteer/task/<int:task_id>')
@login_required
def task_detail(task_id):
    if current_user.role != 'volunteer':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    task = Task.query.get_or_404(task_id)
    logs = ActivityLog.query.filter_by(task_id=task_id).order_by(ActivityLog.timestamp.asc()).all()
    
    return render_template('volunteer/task_detail.html', task=task, logs=logs)

# ==================== RECEIVER ROUTES ====================

@app.route('/receiver/dashboard')
@login_required
def receiver_dashboard():
    if current_user.role != 'receiver':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    my_requests = Request.query.filter_by(receiver_id=current_user.id).order_by(Request.created_at.desc()).all()
    pending_requests = [r for r in my_requests if r.status == 'pending']
    fulfilled_requests = [r for r in my_requests if r.status == 'fulfilled']
    
    # Available donations in my area
    available_donations = Donation.query.filter(
        Donation.status == 'available',
        Donation.location == current_user.location
    ).order_by(Donation.created_at.desc()).limit(10).all()
    
    return render_template('receiver/dashboard.html',
                          requests=my_requests,
                          pending_requests=pending_requests,
                          fulfilled_requests=fulfilled_requests,
                          available_donations=available_donations)

@app.route('/receiver/request', methods=['GET', 'POST'])
@login_required
def create_request():
    if current_user.role != 'receiver':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        req = Request(
            receiver_id=current_user.id,
            item_type=request.form.get('item_type'),
            quantity=int(request.form.get('quantity')),
            urgency=request.form.get('urgency'),
            description=request.form.get('description'),
            location=request.form.get('location') or current_user.location,
            delivery_address=request.form.get('delivery_address')
        )
        
        db.session.add(req)
        db.session.commit()
        
        flash('Request submitted successfully!', 'success')
        return redirect(url_for('receiver_dashboard'))
    
    return render_template('receiver/create_request.html')

# ==================== MATCHING ROUTES ====================

@app.route('/match')
@login_required
def smart_match():
    """Smart matching page - shows best matches based on location and category"""
    
    if current_user.role == 'receiver':
        # Find available donations matching receiver's pending requests
        my_requests = Request.query.filter_by(receiver_id=current_user.id, status='pending').all()
        matches = []
        
        for req in my_requests:
            # Find donations in same location with same item type
            matching_donations = Donation.query.filter(
                Donation.status == 'available',
                Donation.location == req.location,
                Donation.item_type == req.item_type
            ).all()
            
            if matching_donations:
                matches.append({
                    'request': req,
                    'donations': matching_donations
                })
        
        return render_template('match.html', matches=matches, role='receiver')
    
    elif current_user.role == 'donor':
        # Find requests matching donor's donations
        my_donations = Donation.query.filter_by(donor_id=current_user.id, status='available').all()
        matches = []
        
        for donation in my_donations:
            matching_requests = Request.query.filter(
                Request.status == 'pending',
                Request.location == donation.location,
                Request.item_type == donation.item_type
            ).all()
            
            if matching_requests:
                matches.append({
                    'donation': donation,
                    'requests': matching_requests
                })
        
        return render_template('match.html', matches=matches, role='donor')
    
    else:  # volunteer
        flash('Use the dashboard to find tasks', 'info')
        return redirect(url_for('volunteer_dashboard'))

@app.route('/match/connect/<int:donation_id>/<int:request_id>')
@login_required
def connect_match(donation_id, request_id):
    """Connect a donation with a request"""
    donation = Donation.query.get_or_404(donation_id)
    req = Request.query.get_or_404(request_id)
    
    # Find existing task for this donation or create new one
    task = Task.query.filter_by(donation_id=donation_id).first()
    if not task:
        task = Task(donation_id=donation_id)
        db.session.add(task)
    
    task.request_id = request_id
    donation.status = 'matched'
    req.status = 'matched'
    
    # Log activity
    log = ActivityLog(task_id=task.id, 
                     action=f'Donation matched with request by {current_user.name}', 
                     actor_id=current_user.id)
    db.session.add(log)
    
    db.session.commit()
    flash('Match created! A volunteer can now pick this up.', 'success')
    return redirect(url_for('smart_match'))

# ==================== LEADERBOARD ====================

@app.route('/leaderboard')
def leaderboard():
    volunteers = User.query.filter_by(role='volunteer').order_by(User.points.desc()).limit(20).all()
    donors = User.query.filter_by(role='donor').order_by(User.points.desc()).limit(20).all()
    return render_template('leaderboard.html', volunteers=volunteers, donors=donors)

# ==================== CERTIFICATE ====================

@app.route('/certificate')
@login_required
def certificate():
    completed_count = 0
    if current_user.role == 'volunteer':
        completed_count = Task.query.filter_by(volunteer_id=current_user.id, status='delivered').count()
    elif current_user.role == 'donor':
        completed_count = Donation.query.filter_by(donor_id=current_user.id, status='completed').count()
    
    return render_template('certificate.html', user=current_user, completed_count=completed_count)

if __name__ == '__main__':
    app.run(debug=True)
