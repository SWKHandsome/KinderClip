# System architecture

## AI-assisted multi-camera graduation video editor

**Document version:** 2.0  
**Architecture style:** Local modular processing pipeline  
**Application type:** Streamlit web application  
**Runtime:** Python 3.11 on a CPU-only Windows computer

## 1. Architecture overview

The system is a local, semi-automated video editing application for two to four synchronised camera recordings. It separates media inspection, synchronisation, frame analysis, camera recommendation, human review, and rendering into independent Python modules. JSON files pass data between stages and preserve an audit record of automatic recommendations and human changes.

Streamlit provides the user interface. OpenCV samples and analyses video frames, FFprobe reads media properties, and FFmpeg creates the final MP4. Processing remains local, and the application does not upload footage or call cloud video services.

Version 1 uses synchronous, sequential execution. One camera is analysed at a time, and one video segment is rendered at a time. This policy limits memory use and disk contention on an 8 GB computer. Streamlit progress controls report the active camera, segment, and rendering stage.

```text
Streamlit interface
        |
        v
Project and state management
        |
        +----------------------+
        |                      |
        v                      v
Media inspection       Clap synchronisation
        |                      |
        +-----------+----------+
                    |
                    v
            Shared timeline
                    |
                    v
       Frame sampling and cache
                    |
                    v
      Technical camera analysis
                    |
                    v
       Camera recommendation
                    |
                    v
             draft_edl.json
                    |
                    v
        Paginated human review
                    |
                    v
          reviewed_edl.json
                    |
          +---------+---------+
          |                   |
          v                   v
 Sequential video       Master audio
 segment rendering      validation
          |                   |
          +---------+---------+
                    |
                    v
               Final MP4
```

## 2. Presentation and state management

`app.py` contains the Streamlit pages for project setup, synchronisation, analysis, EDL review, validation, and export. The review page shows one segment at a time. This avoids a large editable table and reduces unnecessary reruns.

`state_manager.py` separates temporary interface state from saved project state. `st.session_state` stores the current segment index, unsaved camera selection, override reason, cut adjustment, and review status. Heavy read results, including media metadata, analysis files, and thumbnails, use `st.cache_data` when their input identifiers have not changed.

Saved decisions are written to `reviewed_edl.json` using an atomic operation: write a temporary file, validate it, then replace the previous file. The renderer reads only `reviewed_edl.json`; unsaved widget values cannot affect the final output.

## 3. Media inspection, synchronisation, and audio

`media_probe.py` calls FFprobe through a subprocess argument list and returns duration, resolution, frame rate, codec, and audio availability. Processing stops when fewer than two readable cameras remain.

`sync_manager.py` stores one manually entered clap timestamp per camera. The clap defines time zero on the shared ceremony timeline:

```text
camera_file_time = shared_timeline_time + clap_time_seconds
```

The common usable duration is the shortest post-clap duration across the selected cameras. Users preview one moment near the beginning and another near the end to check visible drift. Automatic drift correction and multiple sync points are outside version 1 because the prototype uses short recordings.

`audio_manager.py` validates one user-selected master audio camera. Camera switches affect video only. The final output uses one continuous audio stream to avoid changes in volume, noise, and echo at every cut. Validation checks that the stream exists, covers the requested interval, and does not contain an excessive silent period. If validation fails, the user selects another source or explicitly approves silent export. Automatic audio-source switching is outside version 1.

## 4. Frame analysis and configuration

`frame_sampler.py` divides the shared timeline into ten-second windows and samples one frame per second. Frames are processed chronologically and resized to 640 by 360. `analysis_cache.py` creates a cache identifier from file identity, clap time, requested duration, and configuration. Matching results are loaded instead of recalculated.

`camera_analyzer.py` measures sharpness, brightness, local motion, global movement, and black-frame presence. Motion analysis divides each frame into a three-by-three grid. Movement in a few regions may indicate subject activity, while strong movement across most regions may indicate camera shake.

`camera_scorer.py` normalises measurements and calculates technical quality:

```text
technical_score =
    0.45 * sharpness_score
  + 0.30 * brightness_score
  + 0.25 * local_motion_score
  - shake_penalty
  - black_frame_penalty
```

No scoring value is embedded in Python recommendation code. `analysis_config.json` stores sampling settings, dimensions, scoring weights, brightness limits, motion thresholds, penalties, switching rules, minimum acceptable score, and review limits. Configuration validation checks ranges and confirms that positive weights total 1.0.

## 5. Camera recommendation and EDL review

`camera_recommender.py` removes unavailable, unreadable, and black cameras. It begins with the highest technical score. It keeps the current angle unless another camera scores at least the configured switching threshold higher.

One camera may appear for no more than two consecutive ten-second windows when an alternative meets the configured quality floor. A repair pass checks for at least two cameras and three switches. It may select a slightly lower-scoring alternative within the permitted score difference, but it never inserts unusable footage.

`edl_generator.py` writes recommendations to `draft_edl.json`. Each segment stores analysis times, final boundaries, scores, reasons, transitions, and decision source. During review, the user may change a camera and move a shared cut boundary by up to two seconds. `edl_validator.py` prevents gaps, overlaps, invalid source times, and shots shorter than five seconds.

## 6. Rendering architecture

`renderer.py` performs staged sequential rendering. It creates the opening title, each approved camera segment, and closing credits as separate temporary video files without source audio. A concat list joins the prepared visual segments. The master audio is extracted separately, trimmed, faded at the beginning and end, and combined with the video.

This staged method avoids oversized FFmpeg commands and permits completed segment files to be reused after a later failure. Temporary files remain until the final MP4 passes validation or the user runs cleanup. The baseline encoder is FFmpeg `libx264`; hardware encoding is outside version 1.

The final output uses H.264 video, AAC audio, 1280 by 720 resolution, 30 frames per second, and a compatible pixel format. FFmpeg diagnostics are saved in `render_log.txt`.

## 7. Reliability, privacy, and limits

The system preserves original files as read-only sources. Input footage, temporary frames, and rendered videos are excluded from Git. Subprocess calls use argument lists rather than shell command strings. Errors identify the affected camera, segment, configuration field, audio interval, or rendering stage.

The architecture measures technical quality rather than ceremony meaning. A clear camera may still show the wrong subject. Regional motion reduces false rewards for shake but cannot classify every movement. Manual synchronisation may contain small errors. These limits are controlled through short simulated footage, visible recommendation reasons, configurable settings, cached results, adjustable cuts, and compulsory human approval.
