"""
Database Pool Manager for Controller
Manages connections to multiple orchestrator databases
"""

import logging
from typing import Dict, Optional, Any, List
from datetime import datetime
import asyncio
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from ..models.orchestrator import OrchestratorConnection
from ..models.organization import OrchestratorInstance
from ..db.database import get_db

logger = logging.getLogger(__name__)

class DatabasePoolManager:
	"""Manages database connections to multiple orchestrator databases."""
	
	def __init__(self):
		self.orchestrator_engines: Dict[str, Any] = {}
		self.orchestrator_sessions: Dict[str, async_sessionmaker] = {}
		self.connection_status: Dict[str, Dict[str, Any]] = {}
		self._lock = asyncio.Lock()
	
	async def register_orchestrator_instance_database(self, instance_id: str, database_url: str) -> bool:
		"""
		Register a new orchestrator instance database connection.
		Called when an orchestrator instance registers with the controller.
		"""
		async with self._lock:
			try:
				logger.info(f"Registering database for orchestrator instance: {instance_id}")
				logger.info(f"Database URL: {database_url}")
				
				# Create engine for the orchestrator instance database
				engine = create_async_engine(
					database_url,
					poolclass=QueuePool,
					pool_size=5,
					max_overflow=10,
					pool_pre_ping=True,
					pool_recycle=3600,  # Recycle connections every hour
					echo=False  # Set to True for SQL debugging
				)
				
				# Test the connection
				async with engine.begin() as conn:
					await conn.execute(text("SELECT 1"))
				
				# Create session factory
				session_factory = async_sessionmaker(
					engine,
					class_=AsyncSession,
					expire_on_commit=False
				)
				
				# Store engine and session factory
				self.orchestrator_engines[instance_id] = engine
				self.orchestrator_sessions[instance_id] = session_factory
				
				# Update connection status
				self.connection_status[instance_id] = {
					"status": "connected",
					"database_url": database_url,
					"connected_at": datetime.utcnow(),
					"last_tested": datetime.utcnow(),
					"error": None
				}
				
				logger.info(f"Successfully registered database for orchestrator instance: {instance_id}")
				return True
				
			except Exception as e:
				logger.error(f"Failed to register database for orchestrator instance {instance_id}: {e}")
				
				# Update connection status with error
				self.connection_status[instance_id] = {
					"status": "failed",
					"database_url": database_url,
					"connected_at": None,
					"last_tested": datetime.utcnow(),
					"error": str(e)
				}
				
				return False
	
	async def unregister_orchestrator_instance_database(self, instance_id: str) -> bool:
		"""
		Unregister an orchestrator instance database connection.
		Called when an orchestrator instance deregisters from the controller.
		"""
		async with self._lock:
			try:
				logger.info(f"Unregistering database for orchestrator instance: {instance_id}")
				
				# Close engine if exists
				if instance_id in self.orchestrator_engines:
					engine = self.orchestrator_engines[instance_id]
					await engine.dispose()
					del self.orchestrator_engines[instance_id]
				
				# Remove session factory
				if instance_id in self.orchestrator_sessions:
					del self.orchestrator_sessions[instance_id]
				
				# Update connection status
				if instance_id in self.connection_status:
					self.connection_status[instance_id]["status"] = "disconnected"
					self.connection_status[instance_id]["disconnected_at"] = datetime.utcnow()
				
				logger.info(f"Successfully unregistered database for orchestrator instance: {instance_id}")
				return True
				
			except Exception as e:
				logger.error(f"Failed to unregister database for orchestrator instance {instance_id}: {e}")
				return False
	
	@asynccontextmanager
	async def get_orchestrator_instance_session(self, instance_id: str):
		"""
		Get a database session for a specific orchestrator instance.
		Use as context manager: async with pool.get_orchestrator_instance_session(instance_id) as session:
		"""
		if instance_id not in self.orchestrator_sessions:
			raise ValueError(f"No database connection for orchestrator instance: {instance_id}")
		
		session_factory = self.orchestrator_sessions[instance_id]
		session = session_factory()
		
		try:
			yield session
		except Exception as e:
			logger.error(f"Database session error for orchestrator instance {instance_id}: {e}")
			await session.rollback()
			raise
		finally:
			await session.close()
	
	async def test_orchestrator_instance_connection(self, instance_id: str) -> bool:
		"""Test database connection for a specific orchestrator instance."""
		try:
			async with self.get_orchestrator_instance_session(instance_id) as session:
				await session.execute(text("SELECT 1"))
			
			# Update connection status
			if instance_id in self.connection_status:
				self.connection_status[instance_id]["last_tested"] = datetime.utcnow()
				self.connection_status[instance_id]["status"] = "connected"
				self.connection_status[instance_id]["error"] = None
			
			return True
			
		except Exception as e:
			logger.error(f"Connection test failed for orchestrator instance {instance_id}: {e}")
			
			# Update connection status with error
			if instance_id in self.connection_status:
				self.connection_status[instance_id]["last_tested"] = datetime.utcnow()
				self.connection_status[instance_id]["status"] = "failed"
				self.connection_status[instance_id]["error"] = str(e)
			
			return False
	
	async def test_all_connections(self) -> Dict[str, bool]:
		"""Test all orchestrator instance database connections."""
		results = {}
		
		for instance_id in self.orchestrator_sessions.keys():
			results[instance_id] = await self.test_orchestrator_instance_connection(instance_id)
		
		return results
	
	async def get_orchestrator_instance_data(self, instance_id: str, table_name: str, limit: int = 100) -> List[Dict]:
		"""
		Get data from a specific table in an orchestrator instance's database.
		Generic method for querying orchestrator instance data.
		"""
		try:
			async with self.get_orchestrator_instance_session(instance_id) as session:
				# Use raw SQL for generic table querying
				query = text(f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT :limit")
				result = await session.execute(query, {"limit": limit})
				
				# Convert to list of dictionaries
				rows = result.fetchall()
				columns = result.keys()
				
				data = []
				for row in rows:
					row_dict = {}
					for i, column in enumerate(columns):
						value = row[i]
						# Convert datetime objects to ISO strings
						if isinstance(value, datetime):
							value = value.isoformat()
						row_dict[column] = value
					data.append(row_dict)
				
				return data
				
		except Exception as e:
			logger.error(f"Failed to get data from {table_name} for orchestrator instance {instance_id}: {e}")
			raise
	
	async def get_user_metrics(self, instance_id: str, user_id: str = None, limit: int = 100) -> List[Dict]:
		"""Get user LLM metrics from an orchestrator instance's database."""
		try:
			async with self.get_orchestrator_instance_session(instance_id) as session:
				if user_id:
					query = text("""
						SELECT * FROM user_llm_realtime 
						WHERE user_id = :user_id 
						ORDER BY request_timestamp DESC 
						LIMIT :limit
					""")
					result = await session.execute(query, {"user_id": user_id, "limit": limit})
				else:
					query = text("""
						SELECT * FROM user_llm_realtime 
						ORDER BY request_timestamp DESC 
						LIMIT :limit
					""")
					result = await session.execute(query, {"limit": limit})
				
				# Convert to list of dictionaries
				rows = result.fetchall()
				columns = result.keys()
				
				metrics = []
				for row in rows:
					row_dict = {}
					for i, column in enumerate(columns):
						value = row[i]
						if isinstance(value, datetime):
							value = value.isoformat()
						row_dict[column] = value
					metrics.append(row_dict)
				
				return metrics
				
		except Exception as e:
			logger.error(f"Failed to get user metrics for orchestrator instance {instance_id}: {e}")
			raise
	
	async def get_system_metrics(self, instance_id: str, hours_back: int = 24) -> List[Dict]:
		"""Get system performance metrics from an orchestrator instance's database."""
		try:
			async with self.get_orchestrator_instance_session(instance_id) as session:
				# Query system metrics from the last N hours
				query = text("""
					SELECT * FROM user_system_performance 
					WHERE timestamp >= NOW() - INTERVAL ':hours hours'
					ORDER BY timestamp DESC 
					LIMIT 1000
				""")
				result = await session.execute(query, {"hours": hours_back})
				
				# Convert to list of dictionaries
				rows = result.fetchall()
				columns = result.keys()
				
				metrics = []
				for row in rows:
					row_dict = {}
					for i, column in enumerate(columns):
						value = row[i]
						if isinstance(value, datetime):
							value = value.isoformat()
						row_dict[column] = value
					metrics.append(row_dict)
				
				return metrics
				
		except Exception as e:
			logger.error(f"Failed to get system metrics for orchestrator instance {instance_id}: {e}")
			raise
	
	def get_connection_status(self) -> Dict[str, Dict[str, Any]]:
		"""Get connection status for all registered orchestrator instance databases."""
		return self.connection_status.copy()
	
	def get_connected_orchestrator_instances(self) -> List[str]:
		"""Get list of orchestrator instance IDs with active database connections."""
		return [
			instance_id for instance_id, status in self.connection_status.items()
			if status["status"] == "connected"
		]
	
	async def refresh_all_connections(self) -> Dict[str, bool]:
		"""Refresh all orchestrator instance database connections."""
		logger.info("Refreshing all orchestrator instance database connections...")
		
		# Get list of registered orchestrator instances from controller database
		async with get_db() as session:
			from sqlalchemy import select
			result = await session.execute(select(OrchestratorInstance))
			instances = result.scalars().all()
		
		refresh_results = {}
		
		for instance in instances:
			if instance.status == "active":
				try:
					# Re-register the database connection
					success = await self.register_orchestrator_instance_database(
						instance.orchestrator_id,
						instance.database_url
					)
					refresh_results[instance.orchestrator_id] = success
				except Exception as e:
					logger.error(f"Failed to refresh connection for {instance.orchestrator_id}: {e}")
					refresh_results[instance.orchestrator_id] = False
		
		return refresh_results
	
	async def cleanup_all_connections(self):
		"""Clean up all database connections. Called during shutdown."""
		logger.info("Cleaning up all orchestrator instance database connections...")
		
		for instance_id in list(self.orchestrator_engines.keys()):
			await self.unregister_orchestrator_instance_database(instance_id)
		
		logger.info("All orchestrator instance database connections cleaned up")


# Global database pool manager instance
_database_pool: Optional[DatabasePoolManager] = None

def get_database_pool() -> DatabasePoolManager:
	"""Get the global database pool manager instance."""
	global _database_pool
	if _database_pool is None:
		_database_pool = DatabasePoolManager()
	return _database_pool

async def initialize_database_pool():
	"""Initialize the database pool with existing orchestrator instance registrations."""
	pool = get_database_pool()
	
	logger.info("Initializing database pool with existing orchestrator instance registrations...")
	
	try:
		# Load existing orchestrator instance registrations
		async with get_db() as session:
			from sqlalchemy import select
			result = await session.execute(
				select(OrchestratorInstance).where(OrchestratorInstance.status == "active")
			)
			instances = result.scalars().all()
			
			for instance in instances:
				if instance.database_url:
					await pool.register_orchestrator_instance_database(
						instance.orchestrator_id,
						instance.database_url
					)
			
			logger.info(f"Initialized database pool with {len(instances)} orchestrator instance connections")
			
	except Exception as e:
		logger.error(f"Failed to initialize database pool: {e}")

async def cleanup_database_pool():
	"""Clean up database pool during shutdown."""
	pool = get_database_pool()
	await pool.cleanup_all_connections()