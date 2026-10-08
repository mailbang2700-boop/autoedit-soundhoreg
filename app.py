import os
import uuid
import shutil
import subprocess
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE = Path("/tmp/autoedit")
BASE.mkdir(exist_ok=True)

app = FastAPI(title="AutoEdit Sound Horeg")

app.mount("/static", StaticFiles(directory="static"), name="static")


def run(cmd):
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )


def get_duration(path):
    result = run([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ])

    try:
        return float(result.stdout.strip())
    except:
        return 0


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.post("/api/render")
async def render_video(
    videos: list[UploadFile] = File(...),
    music: UploadFile | None = File(None),
    duration_sec: int = Form(60),
    ratio: str = Form("9:16")
):

    if not videos:
        raise HTTPException(400, "Minimal 1 video.")

    duration_sec = max(30, min(duration_sec, 180))

    if ratio not in ["9:16", "16:9"]:
        ratio = "9:16"

    job_id = uuid.uuid4().hex[:10]
    work = BASE / job_id
    work.mkdir()

    input_files = []

    for i, video in enumerate(videos):

        ext = Path(video.filename or ".mp4").suffix.lower()

        if ext not in [".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"]:
            ext = ".mp4"

        path = work / f"video_{i}{ext}"

        with open(path, "wb") as f:
            f.write(await video.read())

        input_files.append(path)

    music_path = None

    if music and music.filename:

        ext = Path(music.filename).suffix.lower() or ".mp3"

        music_path = work / f"music{ext}"

        with open(music_path, "wb") as f:
            f.write(await music.read())

    clips = []

    if ratio == "9:16":
        vf = (
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        )
    else:
        vf = (
            "scale=1920:1080:"
            "force_original_aspect_ratio=increase,"
            "crop=1920:1080"
        )

    # Potong setiap video menjadi klip pendek
    for i, source in enumerate(input_files):

        d = get_duration(source)

        if d <= 0:
            continue

        clip_length = min(4, d)

        output = work / f"clip_{i}.mp4"

        result = run([
            "ffmpeg",
            "-y",
            "-i", str(source),
            "-t", str(clip_length),
            "-vf", vf,
            "-r", "30",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output)
        ])

        if result.returncode == 0:
            clips.append(output)

    if not clips:
        raise HTTPException(
            500,
            "Video gagal diproses."
        )

    # Gabungkan semua klip
    concat_file = work / "concat.txt"

    with open(concat_file, "w") as f:
        for clip in clips:
            f.write(f"file '{clip}'\n")

    joined = work / "joined.mp4"

    result = run([
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-t", str(duration_sec),
        "-c", "copy",
        str(joined)
    ])

    if result.returncode != 0:
        raise HTTPException(
            500,
            "Gagal menggabungkan video."
        )

    final = work / "AutoEdit_SoundHoreg.mp4"

    # Tambahkan musik jika dipilih
    if music_path:

        result = run([
            "ffmpeg",
            "-y",
            "-i", str(joined),
            "-stream_loop", "-1",
            "-i", str(music_path),
            "-t", str(duration_sec),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "160k",
            "-shortest",
            str(final)
        ])

        if result.returncode != 0:
            raise HTTPException(
                500,
                "Gagal menambahkan musik."
            )

    else:
        shutil.copy2(joined, final)

    return FileResponse(
        final,
        media_type="video/mp4",
        filename="AutoEdit_SoundHoreg.mp4"
                 )
