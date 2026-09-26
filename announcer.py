import subprocess

class Announcer:
    """Singleton class to handle spoken announcements"""
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Announcer, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not Announcer._initialized:
            Announcer._initialized = True

    def announce(self, text):
        """Announce text using espeak and aplay (non-blocking)"""
        try:
            # Use bash & to run in background, making it non-blocking
            command = f'espeak "{text}" --stdout | aplay -D plug:espeak &'
            result = subprocess.run(command, shell=True, check=False, capture_output=True, text=True)  # Don't check return code for background process
            print(f"Announcing: {text} (exit {result.returncode}, stderr={result.stderr.strip() or '(none)'})")
        except FileNotFoundError:
            print("Error: espeak or aplay command not found. Please ensure they are installed.")

def main():
    announcer = Announcer()
    announcer.announce("Would you like to play a game?")

if __name__ == "__main__":
    main()
