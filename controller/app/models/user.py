"""User model for controller service."""

from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from ..db.database import Base


class User(Base):
	"""Global user table for controller service."""
	__tablename__ = "users"
	
	# Primary key
	user_id = Column(String(255), primary_key=True)  # Format: "user_001_org_001"
	
	# Basic user information
	username = Column(String(100), unique=True, nullable=False, index=True)
	email = Column(String(255), unique=True, nullable=False, index=True)
	full_name = Column(String(255))
	
	# User status and permissions
	is_active = Column(Boolean, default=True, nullable=False)
	is_global_admin = Column(Boolean, default=False, nullable=False)
	is_system_user = Column(Boolean, default=False, nullable=False)
	
	# Profile information
	department = Column(String(100))
	job_title = Column(String(100))
	bio = Column(Text)
	avatar_url = Column(String(500))
	
	# Preferences and settings
	preferences = Column(JSON, default={})  # User preferences
	notification_settings = Column(JSON, default={})  # Notification preferences
	
	# Authentication and security
	password_hash = Column(String(255))  # Hashed password
	last_password_change = Column(DateTime)
	failed_login_attempts = Column(Integer, default=0)
	locked_until = Column(DateTime)
	
	# Multi-factor authentication
	mfa_enabled = Column(Boolean, default=False)
	mfa_secret = Column(String(255))  # Encrypted MFA secret
	backup_codes = Column(JSON, default=[])  # Encrypted backup codes
	
	# Activity tracking
	login_count = Column(Integer, default=0)
	last_login = Column(DateTime)
	last_activity = Column(DateTime)
	last_ip_address = Column(String(45))
	
	# Account metadata
	account_tier = Column(String(50), default="free")  # free, pro, enterprise
	created_by = Column(String(255))  # Admin who created the account
	
	# Timestamps
	created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
	updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
	deleted_at = Column(DateTime)  # Soft delete
	
	def __repr__(self):
		return f"<User(user_id={self.user_id}, username='{self.username}', email='{self.email}')>"