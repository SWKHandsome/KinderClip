# User interface design

## AI-assisted multi-camera graduation video editor

**Document version:** 1.0  
**Application type:** Local Streamlit web application  
**Target device:** Laptop or desktop computer  
**Primary users:** Teachers, student video editors, and project reviewers

## 1. Design purpose

This document defines the user interface and user experience for the multi-camera graduation video editor. It covers screen layout, navigation, controls, messages, visual states, review behaviour, and export feedback. Backend modules, scoring formulas, video processing commands, and storage implementation are documented elsewhere.

The interface should help a user move through one clear workflow: set up a project, synchronise the cameras, run analysis, review the proposed edit, and export the final video. Technical details should remain hidden unless the user opens the advanced settings.

## 2. Interface principles

The interface shall follow these principles:

- Guide the user through one task at a time.
- Use plain language instead of technical video-processing terms where possible.
- Generate a complete draft before asking the user to edit camera choices.
- Explain why each camera was recommended.
- Save review progress whenever the user changes segments.
- Prevent export until all required checks pass.
- Keep warnings close to the control or segment that caused them.
- Use labels and icons together; colour alone shall not communicate status.
- Keep advanced controls hidden by default.
- Make human approval visible before rendering begins.

## 3. Application shell

The application shall use a fixed left sidebar and a main content area. The sidebar shows workflow navigation and project status. The main area contains the current page heading, a short instruction, page content, validation messages, and navigation controls.

### 3.1 Sidebar navigation

The sidebar shall contain five ordered steps:

```text
Graduation Video Editor

1. Project setup        Complete
2. Synchronisation      Complete
3. Camera analysis      Complete
4. Review edit          In progress
5. Export               Locked

Project: Graduation Demo
Target duration: 90 seconds
```

A completed step uses a check icon and a green status label. The current step uses the primary blue colour. A locked step appears grey and cannot be opened. Users may return to a completed step, but changing an earlier value may invalidate later results.

Before invalidating later work, the application shall display a warning:

```text
Changing a clap timestamp will remove the current analysis and edit draft.
Your uploaded videos and project details will remain available.

[Cancel] [Change timestamp]
```

### 3.2 Page actions

Each page shall place its main actions at the bottom. Use **Back** for returning to the previous step and **Save and continue** for completing the current step. The primary action appears on the right. Destructive actions require confirmation.

## 4. Project setup screen

The setup screen collects the project information and camera files.

### 4.1 Project details

The upper section shall contain:

- project name;
- target output duration in seconds;
- opening title;
- lower-third or subtitle text;
- closing credit.

The target duration field shall accept values between 60 and 180 seconds. A short helper message explains the permitted range.

### 4.2 Camera uploads

The user may upload two to four MP4 files. Each uploaded camera appears in a separate card containing:

```text
Front left

camera1_front_left.mp4
Duration: 02:05
Resolution: 1280 x 720
Frame rate: 30 fps
Audio: Available

Status: Ready
```

The user assigns a unique camera label such as "Front left" or "Wide back." Empty and duplicate labels are not accepted. Each card contains **Replace file** and **Remove camera** controls.

The page shall provide these main actions:

```text
[Add camera] [Inspect videos]
[Save and continue]
```

**Save and continue** remains unavailable until at least two readable cameras exist and all required project fields are valid.

## 5. Synchronisation screen

This screen helps the user map recordings that began at different times to one shared ceremony timeline.

### 5.1 Camera sync cards

Each camera card shall show the camera label, a compact video preview, a clap timestamp field, and a preview control.

```text
Camera: Front right

Clap timestamp
[00:08.5]

[Preview at timestamp]

Status: Valid
```

Selecting **Preview at timestamp** updates the preview frame. The user adjusts the timestamp until every camera shows the same visible or audible clap moment.

### 5.2 Shared duration

After valid timestamps are entered, the page displays the usable duration for each camera and the common duration:

```text
Front left usable duration: 120.0 seconds
Front right usable duration: 116.5 seconds
Wide back usable duration: 122.0 seconds

Common usable timeline: 116.5 seconds
Target output duration: 90 seconds
Status: Valid
```

### 5.3 Master audio

The user shall select one camera with audio as the continuous master source:

```text
Master audio source
[Wide back]
```

A helper message shall state:

> The selected camera supplies continuous audio. Changing the video angle will not change the audio source.

The page shall provide preview controls for one moment near the beginning and one near the end. These previews help the user check for visible timing drift. They do not perform automatic correction.

## 6. Camera analysis screen

The analysis screen presents the planned workload, progress, and results without exposing unnecessary calculations.

### 6.1 Before analysis

Show a summary card:

```text
Cameras: 3
Shared duration: 90 seconds
Analysis windows: 9
Sampling rate: 1 frame per second
```

The main action is **Start camera analysis**. Advanced settings remain inside a collapsed panel. The panel may expose segment duration, sampling rate, scoring weights, brightness limits, motion threshold, camera-change threshold, and minimum acceptable score.

Changing an advanced setting after analysis shall display a warning that the existing analysis and edit draft will be replaced.

### 6.2 Analysis progress

During analysis, display:

```text
Analysing Front right
Camera 2 of 3
Window 6 of 9
Overall progress: 59%
```

Use one overall progress bar and a text status below it. The user shall not be able to start a second analysis while one is running.

### 6.3 Analysis results

After completion, show one summary card per camera with:

- average technical score;
- black-frame warnings;
- possible shake warnings;
- availability status.

A success message shall state how many cameras and windows were analysed. The page then enables **Generate edit draft** or **Continue to review**.

## 7. Review edit screen

The review screen is the main editing interface. It shall display one segment at a time to reduce clutter and avoid a large collection of active controls.

### 7.1 Segment heading

The page heading shall show:

```text
Review edit
Segment 4 of 9
Timeline: 00:30.0-00:40.0
Status: Pending review
```

### 7.2 Camera comparison

The page shall show a synchronised thumbnail for every available camera. Each card displays the camera label and score. The recommended camera receives a thicker blue border and a recommendation label.

```text
System recommendation: Front right
Score: 79.2
Reason: Highest technical score with acceptable stability
Decision source: Highest score
```

When a camera is recommended to maintain variety, the text shall be accurate:

```text
System recommendation: Wide back
Reason: Best acceptable alternative after 20 seconds on Front left
Decision source: Mandatory camera change
```

The interface must not describe a lower-scoring variety choice as the highest-scoring camera.

### 7.3 Editing controls

The control panel shall contain:

```text
Final camera
[Front right]

Transition
[Cut]

Cut boundary adjustment
[0.0 seconds]

Override reason
[________________________________]
```

The final-camera control initially contains the recommendation. If the user selects another camera, the override reason becomes required.

Transitions shall use a short list: **Cut**, **Crossfade**, and **Fade**. Most segments should default to **Cut**.

### 7.4 Cut boundary adjustment

The user may move the shared boundary between the previous and current segment by up to two seconds in 0.5-second steps.

```text
Original boundary: 00:30.0
Adjusted boundary: 00:31.0

Previous segment: 00:20.0-00:31.0
Current segment:  00:31.0-00:40.0
```

The interface shall update both adjacent segments together. Invalid adjustments shall be rejected immediately. An example message is:

```text
This adjustment would create a segment shorter than five seconds.
Choose a smaller adjustment.
```

### 7.5 Review navigation and progress

The bottom controls are:

```text
[Previous] [Save segment] [Next]
```

Selecting **Previous** or **Next** saves the current segment before navigation. A compact progress panel shall show:

```text
Reviewed: 6 of 9 segments
Overrides: 2
Adjusted cuts: 1
Cameras used: 3
Camera switches: 4
```

Segment states are **Pending**, **Reviewed**, **Overridden**, and **Warning**. Each state uses both text and colour.

## 8. Export screen

The export screen shall display a checklist before approval:

```text
Readable source cameras          Passed
Synchronisation                  Passed
Master audio                     Passed
All segments reviewed            Passed
Different cameras used           3
Camera switches                  4
Opening title                    Included
Text overlay                     Included
Transition                       Included
Closing credit                   Included
Final duration                   90 seconds
```

Blocking issues appear above the approval section with a direct action. For example:

```text
Export is unavailable.
Only two camera switches were found. At least three are required.

[Return to review]
```

The user must select this checkbox:

```text
[ ] I reviewed the camera choices, cut points, text, and audio source.
```

After approval, the edit becomes read-only. Selecting **Reopen review** removes approval and returns the user to the review step.

## 9. Rendering progress and completion

Rendering shall display the current stage and overall progress:

```text
Rendering final video

Completed:
- Opening title
- Segment 1
- Segment 2

Current:
- Rendering Segment 3 of 9

Overall progress: 31%
```

After completion, show the filename, duration, resolution, file size, saved location, video preview, and download control. A separate **Delete temporary files** control becomes available after the output passes validation.

## 10. Messages and visual style

Messages shall explain the problem and next action. Avoid messages such as "Analysis failed" without context.

```text
Front right could not be analysed at 00:40-00:50.
The application could not read enough frames from this interval.
Check the source file or shorten the project duration.
```

The application shall use a light background, dark blue primary controls, green success states, amber warnings, red blocking errors, and grey disabled controls. Cards use moderate rounded corners, clear spacing, and short labels. Animation is limited to progress indicators.

Camera colours remain consistent throughout the interface:

- Front left: blue;
- Front right: orange;
- Wide back: purple;
- Side angle: green.

The target layout is a laptop display at 1366 by 768 or larger. On narrower screens, camera cards stack vertically. Mobile-phone support is outside the first version.
