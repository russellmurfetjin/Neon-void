"""Launch script that catches ALL errors including import failures."""
import sys
import os
import traceback

if __name__ == "__main__":
    try:
        # This import triggers all game imports
        from main import Game
        game = Game()
        game.run()
    except BaseException as e:
        error_text = traceback.format_exc()

        # Write crash log
        try:
            crash_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")
            with open(crash_path, "w") as f:
                f.write(error_text)
            print(f"\nCrash saved to: {crash_path}")
        except Exception:
            pass

        # Print to terminal
        print("\n===== NEON VOID CRASHED =====")
        print(error_text)
        print("=============================")

        # Keep terminal open
        try:
            input("\nPress ENTER to close...")
        except Exception:
            import time
            time.sleep(30)

        sys.exit(1)
