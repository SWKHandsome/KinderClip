# Product requirements document

## AI-assisted multi-camera graduation video editor

**Document version:** 2.0  
**Product type:** Local Streamlit web application  
**Primary users:** Teachers, student video editors, and project reviewers  
**Implementation stack:** Python 3.11, Streamlit, OpenCV, FFmpeg, FFprobe, JSON, and Pytest  
**Project context:** BTIS3053 Social & Professional Issues group project

## 1. Product summary

The product is a local, semi-automated website that prepares a first edit of a multi-camera kindergarten graduation recording. A user provides two to four camera videos that may begin recording at different times. The user identifies one shared clap or synchronisation event in each file. The system uses those timestamps to map every recording to one common ceremony timeline.

The system divides the common timeline into ten-second analysis windows. It samples frames from every available camera and measures sharpness, brightness, local motion, global movement, and black-frame presence. It then calculates a technical quality score for every camera in each window. A rule-based recommendation engine selects camera angles while preventing one high-scoring camera from controlling the entire video.

The output of the recommendation engine is a draft Editing Decision List (EDL). The user reviews one segment at a time, compares camera thumbnails, changes unsuitable recommendations, adjusts cut boundaries by a small amount, and records any override reason. The system preserves both its original recommendation and the final human choice.

FFmpeg renders the approved EDL as a 60-180 second MP4. Camera switching affects the video stream only. One user-selected camera supplies a continuous master audio track, which avoids sudden changes in volume, echo, and background noise when the video angle changes.

The product does not identify children, interpret emotions, recognise ceremony events, or decide which participant is important. Its recommendations use technical image measurements and editing rules. Human review is compulsory before export.

## 2. Problem statement

Multi-camera editing requires matching moments, comparing angles, choosing clips, managing audio, adding text, and exporting. A manual EDL form would provide little assistance because the user would still make every camera decision. This product creates a complete first draft that the user reviews and corrects.

A score-only recommender may select one technically superior camera throughout the output. The system therefore separates technical scoring from camera variety rules. It changes cameras when acceptable alternatives exist, but never inserts unusable footage only to increase the switch count.

## 3. Product goals

The product shall:

- accept two to four MP4 camera recordings;
- synchronise recordings that started at different times;
- compare corresponding ceremony moments across all cameras;
- analyse technical video quality on a CPU-only computer;
- recommend one camera for each timeline segment;
- prevent excessive use of one camera when alternatives are acceptable;
- use at least two cameras and produce at least three switches when the footage permits;
- generate a readable JSON EDL connected directly to rendering;
- provide segment-by-segment human review and correction;
- use one continuous master audio source;
- render a playable MP4 between 60 and 180 seconds;
- work locally without cloud video processing;
- preserve analysis evidence, recommendation reasons, and human overrides.

## 4. Non-goals

The first version excludes identity, face, emotion, action, speech, and event recognition. It also excludes trained models, automatic audio synchronisation, cloud storage, accounts, a database, direct publishing, and detailed frame-level editing. The product cannot determine which participant or ceremony moment is important, and it does not replace a professional editor.

## 5. Users and stakeholders

The primary user is a teacher or student editor who needs a first edit without watching every camera continuously. Recorded participants and parents are affected by storage, processing, retention, and sharing. The prototype uses simulated footage unless written permission covers the work. The lecturer or reviewer needs evidence of synchronisation, recommendations, camera switching, EDL generation, continuous audio, human approval, testing, and rendering.

## 6. User flow

1. The user creates a project, uploads two to four labelled MP4 files, and enters the required title and credit text.
2. FFprobe inspects the files. The user enters a shared clap timestamp for each camera and selects a master audio source.
3. The system calculates the common timeline, samples frames, scores camera quality, and prepares recommendations.
4. Camera variety rules revise the sequence where one camera is used too long or too few switches exist.
5. The user reviews each segment, changes unsuitable camera choices, adjusts cut boundaries, and records approval.
6. The validator checks the EDL. FFmpeg renders the selected video angles with one continuous master audio track.

## 7. Functional requirements

### 7.1 Project setup and media inspection

The application shall accept two to four MP4 files. FFprobe shall return each file's duration, width, height, frame rate, video codec, and audio status. Unreadable files shall be excluded, and processing cannot continue with fewer than two readable cameras. Original files remain unchanged, while temporary and generated files remain inside the local project workspace.

### 7.2 Manual clap synchronisation

The user shall enter one valid clap timestamp per camera. The clap becomes time zero on the shared timeline. Source positions use:

```text
camera_file_time = shared_timeline_time + clap_time_seconds
```

The common usable duration equals the shortest post-clap camera duration. The requested output must fit inside that period. Settings shall be saved in `sync_config.json`.

### 7.3 Master audio strategy

The user shall select one camera with a readable audio stream as the master audio source. Camera switches affect video only. The renderer shall extract a continuous master track using the selected camera's clap offset, trim it to the final duration, and apply short beginning and ending fades.

A master source without audio shall block rendering. Silent export is permitted only after an explicit user choice. The configuration shall store the master camera and fade durations.

### 7.4 Timeline sampling and caching

The shared timeline shall use ten-second analysis windows, with a shorter final window when required. The system shall sample one frame per second from each available camera, process sample times chronologically, and resize analysis frames to 640 by 360. Rendering retains 1280 by 720 output.

Completed analysis shall be cached using file identity, clap timestamp, requested duration, and analysis settings. Changed inputs invalidate the affected cache. OpenCV seeking is the first method; FFmpeg proxy-frame extraction is a fallback if measured seeking performance is unacceptable.

### 7.6 Camera analysis

The analyzer shall calculate sharpness, brightness, local motion, global movement, and black-frame status.

Sharpness shall use the variance of the Laplacian on grayscale frames. Brightness shall use mean intensity and the proportion of very dark or very bright pixels. Black-frame detection shall identify windows where most samples fall below a configured darkness threshold.

Motion analysis shall divide each frame into a three-by-three grid. The system shall calculate frame differences for each region. Movement concentrated in a few regions may indicate subject activity. Strong movement across most regions may indicate camera movement or shake. The analyzer shall return a local motion score, global motion ratio, and shake penalty.

Raw measurements and normalised values shall both be retained. Thresholds shall remain configurable because suitable values depend on the test footage.

### 7.7 Technical camera scoring

The initial technical score shall be:

```text
technical_score =
    0.45 * sharpness_score
  + 0.30 * brightness_score
  + 0.25 * local_motion_score
  - shake_penalty
  - black_frame_penalty
```

Each positive component shall use a 0-100 scale. A mostly black window shall receive a penalty large enough to block normal selection. Strong global movement shall receive a configurable shake penalty.

Camera variety shall not be included in the technical score. Quality measurement belongs in `camera_scorer.py`; continuity and variety belong in `camera_recommender.py`. This separation keeps recommendation reasons understandable.

### 7.8 Camera recommendation and mandatory changes

The recommender shall remove cameras that are unavailable, unreadable, or mostly black. It shall select the highest technical score for the first video segment.

During normal operation, the current camera shall remain selected unless another camera scores at least ten points higher. This threshold prevents switches caused by small score changes.

The same camera may be selected for no more than two consecutive ten-second windows when an acceptable alternative exists. After twenty continuous seconds, the current camera shall be temporarily excluded. The highest scoring alternative may be selected when its score is at least 50.

If no alternative reaches the quality floor, the current camera remains selected and the EDL records the reason. The system shall never select black, unreadable, or unavailable footage merely to satisfy the assignment.

After generating the sequence, the recommender shall count distinct cameras and switches. The target is at least two cameras and three switches. If the sequence falls short, a repair pass shall find alternatives that score at least 50 and are no more than 15 points below the original choice. A repair must not create a shot shorter than the allowed minimum.

Each decision shall use one source value: `highest_score`, `quality_switch`, `continuity_rule`, `mandatory_variety`, `compliance_repair`, or `human_override`.

### 7.9 EDL generation and review

The system shall generate a JSON EDL containing ordered segments. Every segment shall store its analysis window, final timeline boundaries, recommended camera, selected camera, technical score, component scores, recommendation reason, decision source, transition, and review status.

The Streamlit review interface shall be paginated and display one segment at a time. It shall show synchronised thumbnails, recommendation details, a camera dropdown, transition control, override reason, and navigation controls. Widget identifiers shall use stable segment IDs rather than row positions.

The application shall keep the current project, synchronisation data, analysis results, EDL, current segment index, and unsaved state in `st.session_state`. Selecting **Save segment**, **Previous**, **Next**, or **Save review progress** shall save the EDL to disk.

JSON saving shall be atomic: write a temporary file, validate it, and replace the previous file. This reduces the chance of losing review progress during Streamlit reruns or interruption.

### 7.10 Adjustable cut boundaries

Automatic analysis shall continue to use fixed ten-second windows. During review, the user may move a shared cut boundary by up to two seconds in either direction, using 0.5-second steps. This allows awkward mid-action cuts to be corrected without adding scene detection.

Changing one boundary shall update the end of the previous segment and the start of the next segment together. The system shall prevent overlaps, gaps, out-of-range times, and video segments shorter than five seconds.

The EDL shall preserve both the original analysis times and adjusted final timeline times. It shall also record whether a boundary was changed and the adjustment amount.

### 7.11 Validation

Before export, the validator shall confirm:

- at least two readable source cameras exist;
- every camera has a valid clap timestamp;
- the selected master audio source contains audio, unless silent export was chosen;
- every segment has an available selected camera;
- timeline segments are ordered, continuous, and non-overlapping;
- adjusted boundaries remain within the permitted range;
- at least two camera angles and three switches exist;
- the final duration is between 60 and 180 seconds;
- an opening title, closing credit, text overlay, and transition exist;
- human approval has been recorded.

Errors shall identify the exact condition and affected segment. The export button shall remain disabled until validation passes.

### 7.12 Rendering

The renderer shall use the approved EDL as its source of editing decisions. For each segment, it shall translate shared timeline positions into source file positions, trim the selected video, resize and normalise it, add text where required, and apply cuts or the selected transition.

Video segments shall be assembled without their camera audio. The renderer shall then extract the continuous master audio track, trim it to the final duration, apply beginning and ending fades, and combine it with the completed video.

The final file shall use an MP4 container, H.264 video, AAC audio, 1280 by 720 resolution, 30 frames per second, and a compatible pixel format. FFmpeg output shall be stored in `render_log.txt`. A failed render shall not modify the approved EDL.

## 8. Non-functional requirements

All processing shall occur locally without cloud video services. Input footage, temporary frames, and output MP4 files shall be excluded from Git. The interface shall warn against processing real children's footage without written permission.

The prototype shall run on a CPU-only laptop. Reduced analysis resolution, low sampling frequency, chronological seeking, and caching shall limit processing. Original files remain read-only. Subprocess calls shall not construct unsafe shell commands from user input.

Every recommendation shall display scores and a plain reason. Mandatory variety choices shall not be presented as highest-score choices. Errors shall state the corrective action, and status shall not depend on colour alone.

## 9. Data outputs

The system shall create `analysis_config.json`, `sync_config.json`, `camera_analysis.json`, `edl.json`, `review_record.json`, `render_log.txt`, and `final_video.mp4`. JSON shall use relative paths where possible and shall not contain raw video. The review record shall include approval time, master audio source, silent-export status, override count, boundary-adjustment count, and validation result.

## 10. Testing and acceptance criteria

Unit tests shall cover metadata parsing, timestamp validation, shared timeline calculation, audio-source validation, file-time mapping, sharpness, brightness, regional motion, shake penalty, black-frame rejection, score calculation, switching thresholds, mandatory variety, repair logic, boundary adjustment, switch counting, atomic saving, and EDL validation.

Synthetic frames may test analysis behaviour. A clear image should score above its blurred copy. A normally exposed image should score above a dark copy. Local region movement and full-frame movement should produce different global movement values. A black sequence should be rejected.

Integration tests shall cover cameras with different start times, one camera ending early, one unreadable camera, a master camera without audio, one camera scoring highest throughout, insufficient acceptable alternatives, Streamlit reruns, adjusted cuts, and successful FFmpeg rendering.

Acceptance requires at least two simulated 720p recordings, a synchronised 60-180 second shared timeline, a reviewable EDL, continuous master audio, two camera angles, three acceptable switches when footage permits, retained human changes, and a playable MP4 containing the required title, text overlay, transition, and credits.

## 11. Ethics and professional controls

The prototype shall use simulated footage unless written permission has been obtained. Raw footage access should be limited to authorised team members and reviewers, and files should be deleted according to an agreed retention period.

The system shall not infer identity or importance from faces, voices, clothing, or camera position. Technical scoring and camera variety do not guarantee fair participant coverage. The reviewer remains responsible for checking the final edit.

Background music is outside the default render. Any later music addition requires a properly licensed file and retained licence evidence. The product shall be described as semi-automated and shall not claim guaranteed best-angle selection or full automation.

## 12. Implementation structure

The project shall separate media inspection, synchronisation, audio selection, frame sampling, analysis caching, camera measurements, scoring, recommendation, EDL management, validation, rendering, and the Streamlit interface.

Planned modules are `media_probe.py`, `sync_manager.py`, `audio_manager.py`, `frame_sampler.py`, `analysis_cache.py`, `camera_analyzer.py`, `camera_scorer.py`, `camera_recommender.py`, `edl_generator.py`, `edl_validator.py`, `state_manager.py`, `renderer.py`, and `app.py`.

Modules shall exchange documented data classes or typed dictionaries. Analysis, recommendation, review state, audio processing, and rendering shall be testable independently.

## 13. Delivery order

Implementation shall follow technical dependencies: repository and media inspection; clap synchronisation and master audio selection; frame sampling and caching; camera measurements and scoring; recommendation and mandatory changes; paginated EDL review; adjustable boundaries and validation; FFmpeg video and audio rendering; integration tests and evidence collection.

Each stage must pass its tests before later work depends on its output.

## 14. Risks and limits

A technically clear camera may show the wrong subject. Motion may come from camera shake or obstruction. Regional motion reduces this error but cannot remove it. Fixed analysis windows may divide meaningful actions, while manual cut adjustment only provides a small correction range.

Manual clap timestamps may contain errors. Separate cameras may drift during longer recordings. OpenCV seeking may be slow on some codecs. The prototype limits these risks through short footage, caching, a proxy-frame fallback, visible decisions, adjustable settings, and compulsory review.

Automatic audio matching, scene detection, variable analysis windows, advanced stabilisation, and semantic event recognition remain outside this PRD.

## 15. Definition of done

The product is done when a reviewer can start the local website, upload two to four simulated recordings, enter clap timestamps, select a master audio source, analyse synchronised footage, inspect scores, receive a complete recommendation sequence, review camera changes, adjust cut boundaries, approve the EDL, and render a valid MP4 with continuous audio.

The repository must contain setup instructions, configuration examples, source code, tests, a sample analysis file, a sample EDL, a review record, and evidence of meaningful team contributions. Raw children's footage, private consent records, temporary frames, and rendered MP4 files must not be committed to a public repository.
