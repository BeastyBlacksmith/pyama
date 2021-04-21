#! /bin/env python3
import os
import sys

if __name__ == "__main__":

    # Start workflow
    #from src import workflow_starter
    #workflow_starter.start_workflow(version=__version__, name=PACKAGE_NAME)

    # Check for arguments
    try:
        open_path = sys.argv[1]
    except IndexError:
        open_path = None
    else:
        if not os.path.isfile(open_path):
            open_path = None

    from src.session import SessionController
    SessionController(name=PACKAGE_NAME, version=__version__, read_session_path=open_path).start()


