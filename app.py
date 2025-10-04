import logging
import traceback
import importlib

import streamlit as st

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CANDIDATE_MODULES = [
    "app",      # common entrypoint
    "main",     # alternate
    "src.app",  # if organized under src
    "app_main",
    "app_src",
]

def _show_traceback(e: Exception):
    tb = traceback.format_exc()
    logger.exception("Unhandled exception in Streamlit app")
    try:
        st.error("An unexpected error occurred during app startup. The traceback has been logged.")
        st.text_area("Traceback (copy to report):", tb, height=400)
    except Exception:
        # If Streamlit UI is not available, ensure traceback is printed to stderr
        print(tb)

def _try_import_and_run():
    """Try to import common module names and call a main() if present.

    This helps keep heavy initialization out of top-level imports in the future.
    If the user's app code runs at import-time, importing the module will execute it
    and the UI will appear as expected.
    """
    for name in CANDIDATE_MODULES:
        try:
            logger.info(f"Attempting to import module: {name}")
            mod = importlib.import_module(name)
            logger.info(f"Successfully imported module: {name}")

            # If the module exposes a callable named main, call it.
            if hasattr(mod, "main") and callable(mod.main):
                logger.info(f"Calling main() in module: {name}")
                mod.main()
            else:
                # If there is no main, importing may have already executed Streamlit UI code.
                logger.info(f"No main() found in module: {name}; assuming import executed the app.")
            return True
        except ModuleNotFoundError:
            # This candidate doesn't exist; try the next
            continue
        except Exception as e:
            # If import fails for any other reason, raise to be caught by caller
            raise

    # If we get here, none of the candidate modules were importable.
    return False

def main():
    try:
        imported = _try_import_and_run()
        if not imported:
            st.title("App placeholder")
            st.info("No app module found. Ensure your Streamlit entrypoint is set to the correct file (e.g., app.py) or add your app code to one of the common module names.)")

    except Exception as e:
        _show_traceback(e)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _show_traceback(e)
