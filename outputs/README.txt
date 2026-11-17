outputs/ - generated artefacts
==============================

Everything in this directory is GENERATED. Nothing here is a source of truth: delete it and the commands below
put it back.

The repository keeps one thing from here, the engineering method register (.xlsx and its .csv twin), because the
documentation points at it as the record of every engineering method with its book page, assumptions, limits
and verification basis, and it should be readable without running anything first.

To regenerate everything (after `pip install -e .`, from the project folder):

    python -m launch_vehicle.main run --out outputs --all-studies --pdf --cad

That writes the design report, the Excel workbook, the schematics, the CSV tables, run_summary.json, the CAD
exports and the method register. The optional PDF step needs Chrome or wkhtmltopdf, and the exact-solid CAD
formats need the optional geometry kernel (see requirements.txt); everything else works with the base install.

The validation set, per-vehicle reports and drawings:

    python tools/run_validation.py
    python tools/attribute_error.py
    python tools/build_validation_report.py
