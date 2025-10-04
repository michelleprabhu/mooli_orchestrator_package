# services/orchestrator/app/utils/dispatch.py
"""
Dispatcher for incoming messages from controller.
Imports from controller_dispatch for compatibility.
"""
from .controller_dispatch import dispatch_incoming

__all__ = ['dispatch_incoming']


