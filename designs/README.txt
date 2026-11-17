Configurations saved from the GUI land here.

"Save" in the GUI writes a complete, annotated design file into this directory: every value keeps its units,
description, source and provenance, and anything you changed is re-tagged t: user with a source saying you set
it in the GUI. A file saved here is an ordinary design and runs from the command line like any other:

    python -m launch_vehicle.main run --design designs/<your file>.yaml --all-studies

The directory is listed first in the GUI's Open dialog, under "My designs".
