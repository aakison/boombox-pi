from abc import ABC, abstractmethod

class IBoomboxFunction(ABC):
    """Interface for a boombox function that can be started and stopped"""

    @abstractmethod
    def start(self):
        """Start the function"""
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        """Stop the function"""
        raise NotImplementedError

    @abstractmethod
    def is_running(self):
        """Return True if the function is currently running"""
        raise NotImplementedError
