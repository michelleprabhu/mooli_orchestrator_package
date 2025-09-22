"""
Global OpenAI Client Manager
Provides singleton access to OpenAI clients with dynamic configuration updates.
"""

import os
import threading
import time
from typing import Optional, Dict, Any
from openai import AsyncOpenAI
from openai import RateLimitError, APIError, APIConnectionError, APITimeoutError
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

class OpenAIClientManager:
	"""Singleton manager for OpenAI clients with dynamic configuration."""
	
	_instance: Optional['OpenAIClientManager'] = None
	_lock = threading.Lock()
	
	def __new__(cls) -> 'OpenAIClientManager':
		if cls._instance is None:
			with cls._lock:
				if cls._instance is None:
					cls._instance = super().__new__(cls)
					cls._instance._initialized = False
		return cls._instance
	
	def __init__(self):
		if self._initialized:
			return
			
		self._client: Optional[AsyncOpenAI] = None
		self._api_key: Optional[str] = None
		self._organization_id: Optional[str] = None
		self._client_lock = threading.RLock()
		self._config_watcher: Optional['ConfigurationWatcher'] = None
		self._initialized = True
		
		self._load_initial_config()
		self._create_client()
		self._start_config_watcher()
	
	def _load_initial_config(self):
		"""Load initial configuration from environment."""
		load_dotenv()
		self._api_key = os.getenv("OPENAI_API_KEY")
		# Load org ID for internal system tracking, but don't send to OpenAI API
		self._organization_id = os.getenv("ORGANIZATION_ID", "org_001")
		
		if not self._api_key:
			raise ValueError("OPENAI_API_KEY environment variable is required")
		
		logger.info(f"Loaded OpenAI configuration - API key ends with: {self._api_key[-4:]}")
	
	def _create_client(self):
		"""Create or recreate the OpenAI client."""
		with self._client_lock:
			try:
				# Only send API key to OpenAI - don't send organization header
				client_config = {"api_key": self._api_key}
				
				self._client = AsyncOpenAI(**client_config)
				logger.info(f"OpenAI client created successfully (org {self._organization_id} for internal tracking only)")
			except Exception as e:
				logger.error(f"Failed to create OpenAI client: {e}")
				self._client = None
				raise
	
	def _start_config_watcher(self):
		"""Start configuration watcher in background thread."""
		self._config_watcher = ConfigurationWatcher(self)
		self._config_watcher.start()
	
	def get_client(self) -> AsyncOpenAI:
		"""Get the current OpenAI client instance."""
		with self._client_lock:
			if self._client is None:
				self._create_client()
			return self._client
	
	def update_configuration(self, api_key: str, organization_id: Optional[str] = None):
		"""Update configuration and recreate client."""
		with self._client_lock:
			old_key_suffix = self._api_key[-4:] if self._api_key else "None"
			self._api_key = api_key
			if organization_id:
				self._organization_id = organization_id  # For internal tracking only
			
			self._create_client()
			logger.info(f"Configuration updated - API key changed from *{old_key_suffix} to *{api_key[-4:]}")
	
	def get_current_config(self) -> Dict[str, Any]:
		"""Get current configuration for debugging."""
		return {
			"api_key_suffix": self._api_key[-4:] if self._api_key else None,
			"organization_id": self._organization_id,
			"client_initialized": self._client is not None
		}


class ConfigurationWatcher:
	"""Watches for configuration file changes and updates the client manager."""
	
	def __init__(self, client_manager: OpenAIClientManager):
		self.client_manager = client_manager
		self._stop_event = threading.Event()
		self._thread: Optional[threading.Thread] = None
		self._env_file_path = os.path.join(os.getcwd(), '.env')
		self._last_modified = self._get_file_mtime()
	
	def _get_file_mtime(self) -> float:
		"""Get the modification time of the .env file."""
		try:
			return os.path.getmtime(self._env_file_path)
		except OSError:
			return 0.0
	
	def start(self):
		"""Start the configuration watcher thread."""
		if self._thread and self._thread.is_alive():
			return
		
		self._thread = threading.Thread(target=self._watch_config, daemon=True)
		self._thread.start()
		logger.info("Configuration watcher started")
	
	def stop(self):
		"""Stop the configuration watcher."""
		self._stop_event.set()
		if self._thread:
			self._thread.join(timeout=5)
		logger.info("Configuration watcher stopped")
	
	def _watch_config(self):
		"""Watch for configuration changes."""
		while not self._stop_event.is_set():
			try:
				current_mtime = self._get_file_mtime()
				if current_mtime > self._last_modified:
					self._last_modified = current_mtime
					self._reload_config()
				
				time.sleep(2)  # Check every 2 seconds
			except Exception as e:
				logger.error(f"Error in configuration watcher: {e}")
				time.sleep(5)  # Wait longer on error
	
	def _reload_config(self):
		"""Reload configuration from .env file."""
		try:
			load_dotenv(override=True)  # Force reload
			new_api_key = os.getenv("OPENAI_API_KEY")
			new_org_id = os.getenv("ORGANIZATION_ID", "org_001")
			
			if new_api_key and new_api_key != self.client_manager._api_key:
				self.client_manager.update_configuration(new_api_key, new_org_id)
				logger.info("Configuration reloaded due to .env file change")
		except Exception as e:
			logger.error(f"Failed to reload configuration: {e}")


# Global instance
_global_client_manager: Optional[OpenAIClientManager] = None

def get_openai_client() -> AsyncOpenAI:
	"""Get the global OpenAI client instance."""
	global _global_client_manager
	if _global_client_manager is None:
		_global_client_manager = OpenAIClientManager()
	return _global_client_manager.get_client()

def get_client_manager() -> OpenAIClientManager:
	"""Get the global client manager instance."""
	global _global_client_manager
	if _global_client_manager is None:
		_global_client_manager = OpenAIClientManager()
	return _global_client_manager