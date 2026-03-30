import os
import shutil


def get_ffmpeg_path():
    """Find ffmpeg - check PATH first, then common Windows locations, then download."""

    # 1. Check if ffmpeg is already in PATH
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    # 2. Check common Windows install locations
    common_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        os.path.join(os.path.expanduser("~"), "ffmpeg", "bin", "ffmpeg.exe"),
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path

    # 3. Check local ./ffmpeg/bin/ inside the backend folder
    local_ffmpeg = os.path.join(
        os.path.dirname(__file__), "ffmpeg", "bin", "ffmpeg.exe"
    )
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg

    # 4. Auto-download ffmpeg using imageio-ffmpeg (zero config)
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass

    raise RuntimeError(
        "FFmpeg not found. Run: pip install imageio-ffmpeg  "
        "OR download from https://ffmpeg.org/download.html and add to PATH."
    )


def get_ffprobe_path():
    """Find ffprobe similarly."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        return ffprobe

    common_paths = [
        r"C:\ffmpeg\bin\ffprobe.exe",
        r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
        os.path.join(os.path.expanduser("~"), "ffmpeg", "bin", "ffprobe.exe"),
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path

    local = os.path.join(os.path.dirname(__file__), "ffmpeg", "bin", "ffprobe.exe")
    if os.path.exists(local):
        return local

    try:
        import imageio_ffmpeg

        # ffprobe sits next to ffmpeg in imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")
        if os.path.exists(ffprobe_path):
            return ffprobe_path
    except ImportError:
        pass

    return None  # ffprobe optional, fall back to estimated duration


FFMPEG = get_ffmpeg_path()
FFPROBE = get_ffprobe_path()
