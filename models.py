from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # donor, volunteer, receiver
    location = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    points = db.Column(db.Integer, default=0)
    badges = db.Column(db.String(500), default='')  # comma-separated badges
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    donations = db.relationship('Donation', backref='donor', lazy=True)
    requests = db.relationship('Request', backref='receiver', lazy=True)
    tasks = db.relationship('Task', backref='volunteer', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def add_points(self, points):
        self.points += points
        self.update_badges()
    
    def update_badges(self):
        badges = []
        if self.points >= 10:
            badges.append('Bronze Helper')
        if self.points >= 50:
            badges.append('Silver Helper')
        if self.points >= 100:
            badges.append('Gold Helper')
        if self.points >= 200:
            badges.append('Platinum Helper')
        self.badges = ','.join(badges)
    
    def get_badges_list(self):
        if self.badges:
            return self.badges.split(',')
        return []


class Donation(db.Model):
    __tablename__ = 'donations'
    
    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    item_type = db.Column(db.String(50), nullable=False)  # food, clothes, books, toys, other
    quantity = db.Column(db.Integer, nullable=False)
    condition = db.Column(db.String(20), default='good')  # new, good, fair
    description = db.Column(db.Text)
    location = db.Column(db.String(100), nullable=False)
    pickup_address = db.Column(db.String(200))
    expiry_date = db.Column(db.Date)  # for food items
    status = db.Column(db.String(20), default='available')  # available, matched, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    tasks = db.relationship('Task', backref='donation', lazy=True)


class Request(db.Model):
    __tablename__ = 'requests'
    
    id = db.Column(db.Integer, primary_key=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    item_type = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    urgency = db.Column(db.String(20), default='normal')  # low, normal, high, urgent
    description = db.Column(db.Text)
    location = db.Column(db.String(100), nullable=False)
    delivery_address = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')  # pending, matched, fulfilled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    tasks = db.relationship('Task', backref='request', lazy=True)


class Task(db.Model):
    __tablename__ = 'tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    donation_id = db.Column(db.Integer, db.ForeignKey('donations.id'), nullable=False)
    request_id = db.Column(db.Integer, db.ForeignKey('requests.id'))
    volunteer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    status = db.Column(db.String(20), default='created')  # created, assigned, picked_up, delivered, verified
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_at = db.Column(db.DateTime)
    picked_up_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    verified_at = db.Column(db.DateTime)
    
    # Relationships
    activity_logs = db.relationship('ActivityLog', backref='task', lazy=True)


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    action = db.Column(db.String(200), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    actor = db.relationship('User', backref='activities')


# Helper function to get stats
def get_platform_stats():
    total_donations = Donation.query.count()
    completed_tasks = Task.query.filter_by(status='delivered').count()
    total_users = User.query.count()
    total_volunteers = User.query.filter_by(role='volunteer').count()
    
    # Calculate items donated
    completed_donation_ids = [t.donation_id for t in Task.query.filter_by(status='delivered').all()]
    items_donated = db.session.query(db.func.sum(Donation.quantity)).filter(
        Donation.id.in_(completed_donation_ids)
    ).scalar() or 0
    
    return {
        'total_donations': total_donations,
        'completed_deliveries': completed_tasks,
        'total_users': total_users,
        'total_volunteers': total_volunteers,
        'items_donated': items_donated
    }
