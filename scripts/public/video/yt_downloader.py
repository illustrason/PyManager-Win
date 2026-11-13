import glob
import os
import shutil
import subprocess
import time

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

# moviepy 2.x exposes the classes at the top level, moviepy 1.x in moviepy.editor
try:
    from moviepy import VideoFileClip, AudioFileClip  # moviepy >= 2.0
except ImportError:
    from moviepy.editor import VideoFileClip, AudioFileClip  # moviepy 1.x

# ---------------------------------------------------------------------------
# User parameters
# ---------------------------------------------------------------------------
url = "https://www.youtube.com/watch?v=VIDEO_ID"  # YouTube link @expose
tc_in = ""                # start timecode "HH:MM:SS" (empty = from the start) @expose
tc_out = ""               # end timecode "HH:MM:SS" (empty = until the end) @expose
format_type = "video"     # "video" (mp4) or "audio" (mp3) @expose
output_folder = "output"  # where the final file is saved @expose
# Cookies: YouTube often requires a signed-in account ("Sign in to confirm you're not a bot").
# Option A: read the cookies straight from a browser where you are signed in to YouTube.
#           "firefox" is the most reliable; "edge" and "brave" also work.
#           Avoid "chrome" on Windows (encrypted cookies that yt-dlp cannot read).
cookies_from_browser = "firefox"   # browser name, or "none" to disable @expose
# Option B: a cookies.txt file (Netscape format), exported from a private window.
cookies_file = None                # e.g. "cookies.txt" (takes priority over option A)
# Force the download even if the prerequisites (Deno/Node, yt-dlp version)
# are missing. Keep it False: without them YouTube returns 403 errors.
IGNORE_PREREQUISITES = False
# Install Deno automatically with winget if it cannot be found (Windows).
AUTO_INSTALL_DENO = True

os.makedirs(output_folder, exist_ok=True)


# Path of the JS runtime that was found (set by check_environment, passed to yt-dlp)
JS_RUNTIME = None   # ("deno" | "node", path to the executable)


def _registry_path_dirs():
    """PATH folders read from the Windows registry.

    A .bat started from a terminal opened BEFORE Deno was installed inherits a
    stale PATH; the registry is up to date immediately.
    """
    if os.name != "nt":
        return []
    import winreg
    dirs = []
    keys = [
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ]
    for root, sub in keys:
        try:
            with winreg.OpenKey(root, sub) as k:
                value, _ = winreg.QueryValueEx(k, "Path")
            dirs += [os.path.expandvars(d) for d in value.split(";") if d]
        except OSError:
            pass
    return dirs


def find_js_runtime():
    """Look for deno, then node: process PATH, registry PATH, usual install folders."""
    for name in ("deno", "node"):
        found = shutil.which(name)
        if found:
            return name, found
    exe = ".exe" if os.name == "nt" else ""
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = [os.path.join(d, "deno" + exe) for d in _registry_path_dirs()]
    candidates += [os.path.join(d, "node" + exe) for d in _registry_path_dirs()]
    candidates += [
        os.path.join(home, ".deno", "bin", "deno" + exe),
        os.path.join(local, "Microsoft", "WinGet", "Links", "deno" + exe),
        os.path.join(os.environ.get("ProgramFiles", ""), "nodejs", "node" + exe),
    ]
    candidates += glob.glob(
        os.path.join(local, "Microsoft", "WinGet", "Packages", "DenoLand.Deno*", "deno" + exe)
    )
    for c in candidates:
        if c and os.path.isfile(c):
            return os.path.splitext(os.path.basename(c))[0], c
    return None


def install_deno():
    """Install Deno with winget (Windows only). Returns True on success."""
    if os.name != "nt":
        return False
    print("-> Deno not found: installing it with winget...")
    try:
        r = subprocess.run(
            ["winget", "install", "--id", "DenoLand.Deno", "-e", "--silent",
             "--accept-source-agreements", "--accept-package-agreements"],
            check=False,
        )
        return r.returncode == 0
    except FileNotFoundError:
        print("   winget is not available on this machine.")
        return False


def check_environment():
    """Check (and repair when possible) the prerequisites before a YouTube download."""
    global JS_RUNTIME
    problems = []

    # JS runtime: required to decipher the signatures of the video formats
    JS_RUNTIME = find_js_runtime()
    if not JS_RUNTIME and AUTO_INSTALL_DENO and install_deno():
        JS_RUNTIME = find_js_runtime()
    if JS_RUNTIME:
        name, path = JS_RUNTIME
        print(f"JS runtime: {name} ({path})")
        # Make the executable visible to this process and its children (yt-dlp, ffmpeg...)
        os.environ["PATH"] = os.path.dirname(path) + os.pathsep + os.environ.get("PATH", "")
    else:
        problems.append(
            "No JavaScript runtime found (Deno or Node.js) and the automatic\n"
            "   installation failed.\n"
            "   -> PowerShell:  winget install DenoLand.Deno"
        )

    # yt-dlp version: YouTube regularly breaks old versions
    try:
        from yt_dlp.version import __version__ as ytdlp_version
        year = int(ytdlp_version.split(".")[0])
        if year < 2026:
            problems.append(
                f"yt-dlp {ytdlp_version} is too old.\n"
                "   -> pip install -U --pre \"yt-dlp[default]\""
            )
        else:
            print(f"yt-dlp {ytdlp_version}")
    except Exception:
        pass

    if problems:
        print("\nMissing prerequisites:")
        for p in problems:
            print(f" - {p}")
        print()
        if not IGNORE_PREREQUISITES:
            # Without a JS runtime, or with an outdated yt-dlp, YouTube only returns
            # HLS formats whose URLs answer 403: no point going any further.
            raise SystemExit(
                "Stopped: fix the prerequisites above, then run the script again.\n"
                "(Set IGNORE_PREREQUISITES = True to try anyway.)"
            )


# YouTube clients tried in order. None = yt-dlp's default choice.
# If "The page needs to be reloaded" comes back, one specific client is usually
# broken: we switch to the next one.
PLAYER_CLIENTS = [
    None,
    ["web_safari", "web"],
    ["android_vr"],
    ["mweb"],
    ["tv_embedded"],
]


def time_to_seconds(tc):
    h, m, s = map(int, tc.split(":"))
    return h * 3600 + m * 60 + s


def build_opts(format_type, output_folder, player_client=None):
    if format_type == "video":
        opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
        }
    elif format_type == "audio":
        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
        }
    else:
        raise ValueError("Unknown format. Use 'video' or 'audio'.")

    opts.update({
        "outtmpl": os.path.join(output_folder, "%(title)s [%(id)s].%(ext)s"),
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 2,
        # One fragment answering 403 means the whole session is refused. Do not
        # "skip" fragments (that produced an empty mp4): raise an error and move
        # on to the next YouTube client.
        "skip_unavailable_fragments": False,
        "extractor_retries": 3,
        "overwrites": True,
    })
    if cookies_file:
        opts["cookiefile"] = cookies_file
    elif cookies_from_browser and cookies_from_browser.strip().lower() != "none":
        opts["cookiesfrombrowser"] = (cookies_from_browser.strip(),)
    if player_client:
        opts["extractor_args"] = {"youtube": {"player_client": player_client}}
    # Explicit path of the JS runtime: works even if the .bat's PATH is stale
    if JS_RUNTIME:
        name, path = JS_RUNTIME
        opts["js_runtimes"] = {name: {"path": path}}
    return opts


def download_youtube_video(url, format_type, output_folder):
    last_error = None
    for client in PLAYER_CLIENTS:
        label = "default" if client is None else ",".join(client)
        print(f"\n> Trying client: {label}")
        try:
            with YoutubeDL(build_opts(format_type, output_folder, client)) as ydl:
                info = ydl.extract_info(url, download=True)
            # Actual path of the final file (after merging, if any)
            reqs = info.get("requested_downloads") or []
            if reqs and reqs[0].get("filepath"):
                return reqs[0]["filepath"]
            return ydl.prepare_filename(info)
        except DownloadError as e:
            last_error = e
            print(f"x Failed with client {label}: {e}")
            time.sleep(2)

    raise RuntimeError(
        "Could not download the video with any of the clients tried.\n"
        "-> Update yt-dlp:  pip install -U --pre \"yt-dlp[default]\"\n"
        "-> Install Deno (https://deno.land) or Node.js: yt-dlp needs one of them "
        "to solve YouTube's JavaScript challenges.\n"
        "-> \"Sign in to confirm you're not a bot\" error: sign in to YouTube\n"
        "  in the browser set in cookies_from_browser, or export a cookies.txt.\n"
        f"Last error: {last_error}"
    )


def cut_media(input_path, tc_in, tc_out, format_type, output_folder):
    clip = VideoFileClip(input_path) if format_type == "video" else AudioFileClip(input_path)

    if tc_in or tc_out:
        tc_in_sec = time_to_seconds(tc_in) if tc_in else 0
        tc_out_sec = time_to_seconds(tc_out) if tc_out else clip.duration
        tc_out_sec = min(tc_out_sec, clip.duration)
        # moviepy 2.x: subclipped; moviepy 1.x: subclip
        sub = getattr(clip, "subclipped", None) or clip.subclip
        clip = sub(tc_in_sec, tc_out_sec)

    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_ext = ".mp4" if format_type == "video" else ".mp3"
    output_path = os.path.join(output_folder, f"{base_name}_cut{output_ext}")

    if format_type == "video":
        clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
    else:
        clip.write_audiofile(output_path, bitrate="320k")

    clip.close()
    os.remove(input_path)
    return output_path


if __name__ == "__main__":
    check_environment()
    downloaded_path = download_youtube_video(url, format_type, output_folder)
    print(f"\nDownloaded file: {downloaded_path}")
    final_path = cut_media(downloaded_path, tc_in, tc_out, format_type, output_folder)
    print(f"Done: {final_path}")
