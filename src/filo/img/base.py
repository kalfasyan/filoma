from abc import ABC, abstractmethod

class BaseImageChecker(ABC):
    @abstractmethod
    def check(self, path):
        """Perform checks and return a report (dict or custom object)."""
        pass
