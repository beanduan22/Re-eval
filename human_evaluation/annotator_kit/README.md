# Code Annotation Kit

An offline Python desktop application for independently reviewing original and
modified code. The bundled dataset contains 200 blind samples.

## Setup

Extract the entire ZIP into a writable folder. Install Python 3.10 or newer with
Tkinter, then open a terminal in this folder and run:

```bash
python -m pip install -r requirement.txt
python annotate.py
```

After setup, Windows users can also double-click `start_annotation.bat`.
On macOS or Linux, use `python3` if `python` is unavailable. On Linux, a missing
Tkinter module may require the system `python3-tk` package.
No models or other repository dependencies are needed.

## Annotate

Enter your assigned annotator ID. Compare the two code panels and select:

- **Valid and behavior-preserving**
- **Validity or behavior violation** (select a failure mode)
- **Cannot determine**

Add an optional note, then click **Save and next**. Use **Show full diff** to see
added and deleted lines. The application displays code without executing it.

## Resume and submit

Use the same annotator ID to resume at the first unanswered sample. Saved answers
are stored by default in `results/YOUR_ID_blind_samples_results.json`; the window
always shows the actual path. Use a separate ID for each annotator.

When finished, click **Finish annotation** and send the result JSON file to the
study coordinator. **Export results** saves a copy to a location of your choice.

See [INSTRUCTIONS.txt](INSTRUCTIONS.txt) for the full annotation guidance,
troubleshooting, and coordinator notes.
