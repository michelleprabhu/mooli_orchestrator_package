"""Database configuration for controller service."""

import os
from typing import Optional
from contextlib import asynccontextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


class DatabaseManager:
	"""Manages database connections for controller service."""
	
	def __init__(self):
		self._async_engine: Optional[AsyncEngine] = None
		self._async_session_factory: Optional[sessionmaker] = None
		self._sync_engine = None
		
	def get_database_url(self) -> str:
		"""Get the database URL from environment."""
		database_url = os.getenv("DATABASE_URL")
		if not database_url:
			# Build from individual environment variables
			host = os.getenv("DATABASE_HOST", "localhost")
			port = os.getenv("DATABASE_PORT", "5432")
			user = os.getenv("DATABASE_USER", "moolai")
			password = os.getenv("DATABASE_PASSWORD", "moolai_password")
			database = os.getenv("DATABASE_NAME", "moolai_controller")
			database_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
		return database_url
	
	def get_sync_database_url(self) -> str:
		"""Get the synchronous database URL for migrations."""
		async_url = self.get_database_url()
		# Convert async URL to sync URL for migrations
		if "postgresql+asyncpg://" in async_url:
			return async_url.replace("postgresql+asyncpg://", "postgresql://")
		elif "postgresql://" in async_url:
			return async_url
		else:
			# Handle other async drivers
			if "+aio" in async_url:
				return async_url.replace("+aiosqlite", "").replace("+aio", "")
			return async_url.replace("+asyncpg", "")
	
	@property
	def async_engine(self) -> AsyncEngine:
		"""Get or create the async database engine."""
		if self._async_engine is None:
			database_url = self.get_database_url()
			print(f"Creating controller async engine for: {database_url.split('@')[-1] if '@' in database_url else database_url}")
			self._async_engine = create_async_engine(
				database_url,
				echo=False,
				pool_pre_ping=True,
				pool_recycle=3600,
			)
		return self._async_engine
	
	@property
	def sync_engine(self):
		"""Get or create the sync database engine."""
		if self._sync_engine is None:
			sync_url = self.get_sync_database_url()
			self._sync_engine = create_engine(
				sync_url,
				echo=False,
				pool_pre_ping=True,
				pool_recycle=3600,
			)
		return self._sync_engine
	
	@property
	def async_session_factory(self) -> sessionmaker:
		"""Get or create the async session factory."""
		if self._async_session_factory is None:
			self._async_session_factory = sessionmaker(
				self.async_engine,
				class_=AsyncSession,
				expire_on_commit=False
			)
		return self._async_session_factory
	
	@asynccontextmanager
	async def get_session(self) -> AsyncSession:
		"""Get a database session."""
		session_factory = self.async_session_factory
		session = session_factory()
		try:
			yield session
		finally:
			await session.close()
	
	async def test_connection(self) -> bool:
		"""Test database connection."""
		try:
			async with self.async_engine.begin() as conn:
				await conn.execute(text("SELECT 1"))
			return True
		except Exception as e:
			print(f"Controller database connection test failed: {e}")
			return False
	
	async def init_database(self):
		"""Initialize database tables."""
		# Import all models to ensure they're registered with Base.metadata
		from ..models.user import User
		from ..models.organization import Organization, OrchestratorInstance
		from ..models.orchestrator import OrchestratorConnection
		from ..models.activity_log import ActivityLog
		from ..models.orchestrator_message import OrchestratorMessage
		
		print(f"Creating controller database tables...")
		print(f"Registered tables: {list(Base.metadata.tables.keys())}")
		
		async with self.async_engine.begin() as conn:
			await conn.run_sync(Base.metadata.create_all)
		
		print(f"Controller database tables created successfully!")
	
	async def close(self):
		"""Close database connections."""
		if self._async_engine:
			await self._async_engine.dispose()
		if self._sync_engine:
			self._sync_engine.dispose()
	
	def reset(self):
		"""Reset the database manager - useful for testing."""
		if self._async_engine:
			self._async_engine = None
		if self._sync_engine:
			try:
				self._sync_engine.dispose()
			except:
				pass
			self._sync_engine = None
		self._async_session_factory = None


# Global database manager instance
db_manager = DatabaseManager()

# Base class for models
Base = declarative_base()

# Compatibility functions
async def get_db():
	"""Dependency to get database session."""
	async with db_manager.get_session() as session:
		yield session

async def init_db():
	"""Initialize database tables."""
	await db_manager.init_database()