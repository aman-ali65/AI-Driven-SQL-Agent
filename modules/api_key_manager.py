import os

class APIKeyManager:
    """Manages API keys and provides rotation capabilities from api.txt."""
    def __init__(self, primary_key: str):
        self.keys = []
        if primary_key:
            self.keys.append(primary_key)
            
        try:
            with open("api.txt", "r") as f:
                for line in f:
                    key = line.strip().strip(",")
                    if key and key not in self.keys:
                        self.keys.append(key)
        except Exception:
            pass
            
        self.current_idx = 0

    def get_key(self) -> str:
        if not self.keys:
            return ""
        return self.keys[self.current_idx]

    def rotate(self) -> bool:
        """Rotates to the next key. Returns True if a new key was selected, False if exhausted."""
        if not self.keys:
            return False
        self.current_idx += 1
        if self.current_idx >= len(self.keys):
            self.current_idx = 0
            return False # We've tried all keys
        return True
