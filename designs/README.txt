Configurations saved from the GUI land here.

"Save" in the GUI writes a complete, annotated design file into this directory: every value keeps its units,
description, source and provenance, and anything you changed is re-tagged t: user with a source saying you set
it in the GUI. A file saved here is an ordinary design and runs from the command line like any other:

    python -m launch_vehicle.main run --design designs/<your file>.yaml --all-studies

The directory is listed first in the GUI's Open dialog, under "My designs".

my_library.yaml, if present, is your own library of propellants and tank materials, added from the
GUI's Library button. It is not a design. A design saved with one of its entries carries a copy, so you
do not need to send this file along with a design.
