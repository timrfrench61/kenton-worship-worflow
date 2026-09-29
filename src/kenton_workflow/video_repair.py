"""Timestamp-driven HSWTL replacement and full-frame music slides using FFmpeg."""
from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

from .audio_repair import ROOT, digest, probe, run, save

WORK = ROOT / "work" / "video-repair"


def seconds(value, name: str) -> float:
    if isinstance(value, str) and ":" in value:
        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError(f"{name}: use seconds or HH:MM:SS.sss.")
        try:
            h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
        except ValueError as exc:
            raise ValueError(f"{name}: invalid timestamp {value!r}.") from exc
        if h < 0 or not 0 <= m < 60 or not 0 <= s < 60:
            raise ValueError(f"{name}: invalid timestamp {value!r}.")
        value = h * 3600 + m * 60 + s
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name}: supply an explicit timestamp.")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name}: supply seconds or HH:MM:SS.sss.") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name}: timestamp must be finite and nonnegative.")
    return result


def fields(value, allowed: set[str], required: set[str], name: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object.")
    if set(value) - allowed or required - set(value):
        raise ValueError(f"{name}: missing fields {sorted(required - set(value))}; unknown fields {sorted(set(value) - allowed)}.")


def local_file(value, base: Path, name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}: supply a local source filename.")
    path = Path(value)
    path = (path if path.is_absolute() else base / path).resolve()
    if not path.is_file():
        raise ValueError(f"{name}: file not found: {path}")
    return path


def stream_info(info: dict, track, name: str, need_audio: bool = True) -> tuple[dict, dict | None]:
    videos = [s for s in info["streams"] if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")]
    if len(videos) != 1:
        raise ValueError(f"{name}: expected one video stream; found {len(videos)}. Export a single-picture source first.")
    if videos[0].get("color_transfer") in ("smpte2084", "arib-std-b67"):
        raise ValueError(f"{name}: HDR needs a deliberate SDR conversion before this workflow.")
    audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if not need_audio:
        return videos[0], None
    if track is None and len(audio) == 1:
        track = 0
    if type(track) is not int or not 0 <= track < len(audio):
        raise ValueError(f"{name}: select audio_track explicitly (zero based); found {len(audio)} audio tracks.")
    return videos[0], audio[track]


def duration(info: dict, name: str) -> float:
    value = seconds(info.get("format", {}).get("duration"), name + " duration")
    if value <= 0:
        raise ValueError(f"{name}: duration is zero.")
    return value


def validate(plan_path: Path, ffprobe: str) -> dict:
    raw = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    fields(raw, {"schema", "source", "source_audio_track", "output", "edits", "notes"},
           {"schema", "source", "source_audio_track", "output", "edits"}, "plan")
    if type(raw["schema"]) is not int or raw["schema"] != 1:
        raise ValueError("Unsupported plan schema; expected 1.")
    settings = raw["output"]
    fields(settings, {"width", "height", "fps"}, {"width", "height", "fps"}, "output")
    for key in ("width", "height"):
        if type(settings[key]) is not int or not 16 <= settings[key] <= 7680 or settings[key] % 2:
            raise ValueError(f"output.{key}: use an even integer from 16 to 7680.")
    try:
        fps = Fraction(str(settings["fps"]))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("output.fps: use a number or rational such as 30000/1001.") from exc
    if not 1 <= fps <= 60:
        raise ValueError("output.fps must be between 1 and 60.")
    settings = dict(settings, fps=str(fps))
    source = local_file(raw["source"], plan_path.parent, "source")
    cache = {}
    def inspect(path: Path) -> dict:
        if str(path) not in cache:
            cache[str(path)] = probe(path, ffprobe)
        return cache[str(path)]
    info = inspect(source)
    sv, sa = stream_info(info, raw["source_audio_track"], "source")
    total = duration(info, "source")
    if not isinstance(raw["edits"], list) or not raw["edits"]:
        raise ValueError("Supply at least one timed edit; remove unused starter entries.")
    edits = []
    for index, item in enumerate(raw["edits"]):
        name = f"edits[{index}]"
        fields(item, {"type", "label", "start", "end", "file", "in", "out", "audio", "audio_track", "kind"},
               {"type", "start", "end", "file"}, name)
        start, end = seconds(item["start"], name + ".start"), seconds(item["end"], name + ".end")
        if not start < end <= total:
            raise ValueError(f"{name}: need 0 <= start < end <= original duration {total:.3f}.")
        asset = local_file(item["file"], plan_path.parent, name + ".file")
        asset_info = inspect(asset)
        label = item.get("label", item["type"])
        if not isinstance(label, str):
            raise ValueError(f"{name}.label must be text.")
        edit = {"type": item["type"], "label": label, "start": start, "end": end,
                "video": str(asset), "video_in": 0.0, "audio": str(source), "audio_in": start,
                "audio_stream": sa["index"], "duration": end - start}
        if item["type"] == "slide":
            fields(item, {"type", "label", "start", "end", "file", "kind"},
                   {"type", "start", "end", "file", "kind"}, name)
            if item["kind"] not in ("praise-band", "piano"):
                raise ValueError(f"{name}.kind must be praise-band or piano.")
            if asset.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                raise ValueError(f"{name}: export slides to individual PNG or JPEG files first.")
            av, _ = stream_info(asset_info, None, name, need_audio=False)
            edit.update(video_stream=av["index"], kind=item["kind"])
        elif item["type"] == "replace":
            fields(item, {"type", "label", "start", "end", "file", "in", "out", "audio", "audio_track"},
                   {"type", "start", "end", "file", "in", "out", "audio"}, name)
            if item["audio"] not in ("file", "original"):
                raise ValueError(f"{name}.audio must explicitly be file or original.")
            av, aa = stream_info(asset_info, item.get("audio_track"), name, need_audio=item["audio"] == "file")
            cut_in, cut_out = seconds(item["in"], name + ".in"), seconds(item["out"], name + ".out")
            if not cut_in < cut_out <= duration(asset_info, name):
                raise ValueError(f"{name}: replacement in/out must be within the supplied file.")
            replacement_duration = cut_out - cut_in
            if item["audio"] == "original" and abs(replacement_duration - (end - start)) > 0.000001:
                raise ValueError(f"{name}: retaining original audio requires equal source/replacement durations; no time stretching is inferred.")
            edit.update(video_stream=av["index"], video_in=cut_in, duration=replacement_duration)
            if aa is not None:
                edit.update(audio=str(asset), audio_in=cut_in, audio_stream=aa["index"])
        else:
            raise ValueError(f"{name}: type must be replace or slide.")
        edits.append(edit)
    edits.sort(key=lambda e: e["start"])
    segments = []
    position = 0.0
    def original(start, end):
        return {"type": "original", "label": "Retained service", "start": start, "end": end,
                "video": str(source), "video_in": start, "video_stream": sv["index"],
                "audio": str(source), "audio_in": start, "audio_stream": sa["index"], "duration": end - start}
    for edit in edits:
        if edit["start"] < position:
            raise ValueError("Edits overlap on the original timeline. Split or correct them; slide/replacement overlap is not inferred.")
        if edit["start"] > position:
            segments.append(original(position, edit["start"]))
        segments.append(edit)
        position = edit["end"]
    if position < total:
        segments.append(original(position, total))
    output_time = 0.0
    intended_time = 0.0
    previous_frame = 0
    for segment in segments:
        intended_time += segment["duration"]
        end_frame = round(intended_time * float(fps))
        frames = end_frame - previous_frame
        if frames < 1:
            raise ValueError("A segment is shorter than one output frame. Adjust adjacent edit timestamps.")
        rendered_duration = frames / float(fps)
        segment.update(frames=frames, rendered_duration=rendered_duration, output_start=output_time,
                       output_end=output_time + rendered_duration)
        output_time += rendered_duration
        previous_frame = end_frame
    return {"schema": 1, "source": str(source), "source_duration": total, "output_settings": settings,
            "segments": segments, "expected_duration": output_time, "inputs": list(cache), "plan": raw,
            "source_audio_stream": sa["index"],
            "continuous_original_audio": all(s["audio"] == str(source) and s["audio_in"] == s["start"]
                                             and abs(s["duration"] - (s["end"] - s["start"])) < 0.000001 for s in segments)}


def render(plan_path: Path, plan: dict, output_dir: Path, ffmpeg: str, ffprobe: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=False)
    report_path = output_dir / "video-repair.json"
    report = dict(plan, state="incomplete", created=datetime.now(timezone.utc).isoformat(),
                  plan_path=str(plan_path), input_sha256={p: digest(Path(p)) for p in plan["inputs"]})
    save(report_path, report)
    save(output_dir / "plan.json", plan["plan"])
    def note(message):
        print(message, flush=True)
        with (output_dir / "repair.log").open("a", encoding="utf-8") as stream:
            stream.write(message + "\n")
    settings = plan["output_settings"]
    fps = float(Fraction(settings["fps"]))
    width, height = settings["width"], settings["height"]
    try:
        part_paths = []
        for index, segment in enumerate(plan["segments"]):
            note(f"Segment {index + 1}/{len(plan['segments'])}: {segment['label']} | original {segment['start']:.3f}..{segment['end']:.3f} -> output {segment['output_start']:.3f}..{segment['output_end']:.3f}")
            length = segment["rendered_duration"]
            command = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-n"]
            if segment["type"] == "slide":
                command += ["-loop", "1", "-framerate", settings["fps"], "-i", segment["video"]]
            else:
                command += ["-ss", str(segment["video_in"]), "-i", segment["video"]]
            if not plan["continuous_original_audio"]:
                command += ["-ss", str(segment["audio_in"]), "-i", segment["audio"]]
            # H.264 intermediate picture + PCM sound avoids repeated AAC encoder
            # delay at every join. Encode AAC only once, after concatenation.
            video_filter = (f"trim=duration={segment['duration']},setpts=PTS-STARTPTS,"
                            f"scale=w=trunc(iw*sar/2)*2:h=ih,setsar=1,"
                            f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                            f"fps={settings['fps']},tpad=stop_mode=clone:stop_duration={1 / fps},"
                            f"trim=end_frame={segment['frames']},format=yuv420p")
            audio_filter = (f"atrim=duration={segment['duration']},asetpts=PTS-STARTPTS,"
                            f"aresample=48000,aformat=channel_layouts=stereo,"
                            f"apad=pad_dur={1 / fps},atrim=duration={length}")
            part = output_dir / f"segment-{index:04d}.mkv"
            command += ["-map", f"0:{segment['video_stream']}", "-vf", video_filter,
                        "-c:v", "libx264", "-crf", "18", "-preset", "medium"]
            if not plan["continuous_original_audio"]:
                command += ["-map", f"1:{segment['audio_stream']}", "-af", audio_filter, "-c:a", "pcm_s16le"]
            command += ["-t", str(length), str(part)]
            run(command)
            part_info = probe(part, ffprobe)
            if abs(duration(part_info, str(part)) - length) > max(0.05, 1 / fps):
                raise ValueError(f"Segment {index + 1} duration failed validation; inspect its source streams.")
            part_paths.append(part)
        concat = output_dir / "segments.txt"
        concat.write_text("".join(f"file '{p.name}'\n" for p in part_paths), encoding="utf-8")
        partial = output_dir / "repaired.partial.mp4"
        note("Joining picture segments and encoding final audio...")
        command = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-n", "-f", "concat", "-safe", "1", "-i", str(concat)]
        if plan["continuous_original_audio"]:
            # Keep one continuous service soundtrack, with no cuts at slide or
            # picture-replacement boundaries and no inserted-file audio.
            command += ["-i", plan["source"], "-map", "0:v:0", "-map", f"1:{plan['source_audio_stream']}"]
        else:
            command += ["-map", "0:v:0", "-map", "0:a:0"]
        command += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                    "-t", str(plan["expected_duration"]), "-movflags", "+faststart", str(partial)]
        run(command)
        final_info = probe(partial, ffprobe)
        fv, fa = stream_info(final_info, 0, "rendered output")
        actual = duration(final_info, "rendered output")
        tolerance = max(0.1, 2 / fps)
        checks = {"duration": abs(actual - plan["expected_duration"]) <= tolerance,
                  "video_duration": abs(float(fv.get("duration", 0)) - plan["expected_duration"]) <= tolerance,
                  "audio_duration": abs(float(fa.get("duration", 0)) - plan["expected_duration"]) <= tolerance,
                  "dimensions": (fv["width"], fv["height"]) == (width, height),
                  "audio": fa.get("sample_rate") == "48000" and fa.get("channels") == 2,
                  "inputs_unchanged": all(digest(Path(p)) == h for p, h in report["input_sha256"].items())}
        note("Decoding the complete MP4 to check for media errors...")
        run([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-xerror", "-i", str(partial), "-f", "null", "-"])
        checks["full_decode"] = True
        report.update(checks=checks, output_duration=actual)
        if not all(checks.values()):
            raise ValueError(f"Final checks failed: {checks}")
        output = output_dir / "repaired.mp4"
        partial.rename(output)
        report.update(state="complete", output=str(output), output_sha256=digest(output))
        save(report_path, report)
        note(f"Complete: {output}\nWatch and listen to every edit before audio repair or upload.")
        # Only intermediates from this successful, newly created job are removed.
        for part in part_paths:
            part.unlink()
    except Exception as exc:
        report.update(state="incomplete", error=str(exc))
        save(report_path, report)
        note(f"FAILED: {exc}")
        raise
    return report_path


def plan_main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inspect a source and create a starter plan with unset edit times.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=WORK / "plan.json")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args(argv)
    try:
        source = local_file(str(args.source.resolve()), Path.cwd(), "source")
        ffprobe = shutil.which(args.ffprobe)
        if not ffprobe:
            raise ValueError("Install ffprobe or provide --ffprobe with its full path.")
        if args.output.exists() or args.output.with_suffix(".source.json").exists():
            raise ValueError("Plan or source inventory already exists; choose a new --output path.")
        info = probe(source, ffprobe)
        audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
        stream_info(info, None, "source", need_audio=False)
        total = duration(info, "source")
        plan = {"schema": 1, "source": str(source), "source_audio_track": 0 if len(audio) == 1 else None,
                "output": {"width": 1920, "height": 1080, "fps": "30"},
                "notes": "Fill exact ORIGINAL recording times and asset paths; remove unused entries. Do not render placeholders.",
                "edits": [{"type": "replace", "label": "HSWTL", "start": None, "end": None,
                           "file": "", "in": None, "out": None, "audio": "original", "audio_track": None},
                          {"type": "slide", "label": "Praise Band", "kind": "praise-band", "start": None, "end": None, "file": ""},
                          {"type": "slide", "label": "Piano", "kind": "piano", "start": None, "end": None, "file": ""}]}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        save(args.output, plan)
        save(args.output.with_suffix(".source.json"), info)
        print(f"Source: {source}\nDuration: {total:.3f}s; {len(audio)} audio tracks.\nDraft plan: {args.output.resolve()}\nEdit times are deliberately unset.")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ATTENTION: {exc}")
        return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--check", action="store_true", help="Validate files and intervals and print the timeline without rendering")
    parser.add_argument("--output-dir", type=Path, help="New job directory; existing directories are protected")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args(argv)
    try:
        ffprobe = shutil.which(args.ffprobe)
        ffmpeg = shutil.which(args.ffmpeg)
        if not ffprobe or (not args.check and not ffmpeg):
            raise ValueError("Install FFmpeg/ffprobe or provide their full paths.")
        path = args.plan.resolve()
        plan = validate(path, ffprobe)
        for segment in plan["segments"]:
            print(f"{segment['type']:8} {segment['start']:.3f}..{segment['end']:.3f} -> {segment['output_start']:.3f}..{segment['output_end']:.3f} | {segment['label']}", flush=True)
        print(f"Output duration: {plan['expected_duration']:.3f}s (original {plan['source_duration']:.3f}s)", flush=True)
        if not args.check:
            output_dir = (args.output_dir or WORK / datetime.now().strftime("repair-%Y%m%d-%H%M%S-%f")).resolve()
            render(path, plan, output_dir, ffmpeg, ffprobe)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ATTENTION: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
