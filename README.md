# KinderClip

KinderClip is a local, semi-automated Streamlit editor for creating a first cut of a multi-camera kindergarten graduation video. It analyses only technical image quality, recommends camera changes, requires human review, and renders with one continuous master-audio source.

Choose the longest recording as the **main video timeline**. KinderClip keeps that camera available for the entire edit, then uses shorter or late-starting cameras only during the intervals where they overlap it. The main camera is normally also the continuous master-audio source.

## Prerequisites

- Python 3.11 or later
- [FFmpeg](https://ffmpeg.org/download.html) with both `ffmpeg` and `ffprobe` available on `PATH`

On Windows, install Python from python.org and a trusted FFmpeg Windows build, then reopen PowerShell after adding the FFmpeg `bin` directory to `PATH`.

## Run locally

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

KinderClip checks for FFmpeg and FFprobe on launch. Media inspection, analysis, and rendering remain disabled until both are available. All uploaded media and generated output stay in the local `projects/` workspace and are ignored by Git.

## Test

```powershell
python -m pytest -q
```

The unit suite uses synthetic image data and subprocess mocks. It does not require real footage or FFmpeg. An optional FFmpeg integration test is skipped when the tools are unavailable.

## Privacy

Use simulated footage unless written permission covers the project. KinderClip performs no face, emotion, action, speech, or identity recognition, and it never uploads footage.
