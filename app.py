"""
Campaign Clipper - Gradio dashboard around ViralCutter.

Input : video URL or uploaded video + campaign guidelines (file and/or text)
Output: subtitled 9:16 clips shown in a gallery and saved under JOBS_DIR/<job_id>/clips

Run in Colab:  see colab_launcher.py
Everything marked  # ADAPTER  is an assumption about ViralCutter's internals
that CODEX_TASK.md asks Codex to verify against the real repo.
"""
import json, os, re, shutil, subprocess, sys, threading, time, uuid
from pathlib import Path

import gradio as gr
import requests

VC_DIR = Path(os.environ.get("VC_DIR", "/content/ViralCutter"))
JOBS_DIR = Path(os.environ.get("JOBS_DIR", "/content/drive/MyDrive/campaign_clipper_jobs"))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")  # free tier in Google AI Studio
JOBS_DIR.mkdir(parents=True, exist_ok=True)
RUN_LOCK = threading.Lock()  # free Colab has one GPU: one job at a time


# ---------------------------------------------------------------- guidelines
def read_guidelines(file_path, pasted_text):
    parts = []
    if pasted_text and pasted_text.strip():
        parts.append(pasted_text.strip())
    if file_path:
        p = Path(file_path)
        ext = p.suffix.lower()
        if ext == ".pdf":
            from pypdf import PdfReader
            parts.append("\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages))
        elif ext == ".docx":
            import docx
            parts.append("\n".join(par.text for par in docx.Document(str(p)).paragraphs))
        else:
            parts.append(p.read_text(errors="ignore"))
    return "\n\n".join(parts).strip()


RULES_PROMPT = """You convert a content-campaign brief into clip-selection rules for a short-form video clipper.
Return ONLY JSON with these keys:
- num_clips (int, default 5 if not stated)
- min_seconds, max_seconds (ints; default 20 and 60 if not stated)
- tone (string)
- must_include (list of strings: topics, product mentions, hashtags, CTAs the clip must contain or end with)
- must_avoid (list of strings: banned words, topics, competitors, claims)
- selection_prompt (string, max 150 words, imperative instructions telling an AI which moments of a transcript to pick so clips satisfy this brief and have a strong hook in the first 3 seconds)
- caption_text (string, suggested post caption incl. required hashtags, or "")
BRIEF:
"""


def guidelines_to_rules(text):
    key = os.environ.get("GEMINI_API_KEY", "")
    default = {"num_clips": 5, "min_seconds": 20, "max_seconds": 60, "tone": "", "must_include": [],
               "must_avoid": [], "selection_prompt": "", "caption_text": ""}
    if not text:
        return default
    if not key:
        raise gr.Error("GEMINI_API_KEY not set (free key: aistudio.google.com).")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = {"contents": [{"parts": [{"text": RULES_PROMPT + text[:20000]}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
    r = requests.post(url, params={"key": key}, json=body, timeout=90)
    r.raise_for_status()
    raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    default.update(json.loads(re.sub(r"^```(json)?|```$", "", raw.strip())))
    return default


# ---------------------------------------------------------------- ADAPTER
def build_command(source_type, url, video_path, rules):
    cmd = [sys.executable, "main_improved.py", "--segments", str(rules["num_clips"])]  # confirmed flag
    if source_type == "URL":
        cmd += ["--url", url]  # confirmed flag
    else:
        # ADAPTER: web UI passes uploaded videos to main_improved.py; exact flag/project layout
        # must be read from main_improved.py (`--project-path` exists). Codex: fix this branch.
        cmd += ["--project-path", prepare_upload_project(video_path)]
    # ADAPTER: add flags for min/max duration, subtitle style, whisper model if main_improved.py has them.
    return cmd


def prepare_upload_project(video_path):
    # ADAPTER: placeholder - Codex must mirror what webui/app.py does for "Upload Video".
    dest = VC_DIR / "VIRALS" / f"upload_{uuid.uuid4().hex[:6]}"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(video_path, dest / "input.mp4")
    return str(dest)


PROMPT_FILE = VC_DIR / "prompt.txt"
PROMPT_BACKUP = VC_DIR / "prompt.txt.orig"


def inject_rules(rules):
    """Append campaign rules to ViralCutter's LLM prompt (restored after the job)."""
    if not PROMPT_BACKUP.exists() and PROMPT_FILE.exists():
        shutil.copy(PROMPT_FILE, PROMPT_BACKUP)
    base = PROMPT_BACKUP.read_text(encoding="utf-8") if PROMPT_BACKUP.exists() else ""
    extra = (f"\n\nCAMPAIGN RULES (mandatory):\n{rules['selection_prompt']}\n"
             f"Clip length: {rules['min_seconds']}-{rules['max_seconds']} seconds.\n"
             f"Tone: {rules['tone']}\nMust include: {', '.join(rules['must_include'])}\n"
             f"Must avoid: {', '.join(rules['must_avoid'])}\n")
    PROMPT_FILE.write_text(base + extra, encoding="utf-8")


def restore_prompt():
    if PROMPT_BACKUP.exists():
        shutil.copy(PROMPT_BACKUP, PROMPT_FILE)


def collect_clips(started_at, dest):
    """Find mp4s written after job start; prefer subtitled renders. Layout-agnostic."""
    found = [p for p in VC_DIR.rglob("*.mp4") if p.stat().st_mtime >= started_at and JOBS_DIR not in p.parents]
    subtitled = [p for p in found if "subtitled" in p.name.lower()]
    chosen = subtitled or found
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(chosen):
        t = dest / p.name
        shutil.copy(p, t)
        out.append(str(t))
    return out


# ---------------------------------------------------------------- job runner
def run_job(job_id, cmd, rules, log):
    job_dir = JOBS_DIR / job_id
    started = time.time()
    with RUN_LOCK:
        try:
            inject_rules(rules)
            log.append("$ " + " ".join(cmd))
            proc = subprocess.Popen(cmd, cwd=VC_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, text=True, bufsize=1,
                                    env={**os.environ, "PYTHONUNBUFFERED": "1"})
            for line in proc.stdout:
                log.append(line.rstrip())
            code = proc.wait()
            clips = collect_clips(started, job_dir / "clips")
            status = "done" if code == 0 and clips else "failed"
            log.append(f"[exit {code}] {len(clips)} clip(s) collected")
        except Exception as e:  # noqa
            clips, status = [], "failed"
            log.append(f"ERROR: {e}")
        finally:
            restore_prompt()
    (job_dir).mkdir(parents=True, exist_ok=True)
    (job_dir / "job.json").write_text(json.dumps(
        {"id": job_id, "status": status, "rules": rules, "clips": clips, "log_tail": log[-200:]}, indent=2))
    log.append(f"STATUS:{status}")


def submit(source_type, url, upload, g_file, g_text):
    if source_type == "URL" and not (url or "").strip():
        raise gr.Error("Paste a video URL.")
    if source_type == "Upload" and not upload:
        raise gr.Error("Upload a video.")
    yield "Reading guidelines...", [], ""
    rules = guidelines_to_rules(read_guidelines(g_file, g_text))
    job_id = time.strftime("%Y%m%d-%H%M%S")
    log = []
    cmd = build_command(source_type, (url or "").strip(), upload, rules)
    t = threading.Thread(target=run_job, args=(job_id, cmd, rules, log), daemon=True)
    t.start()
    yield "Running... (leave this tab open or check the Jobs tab later)", [], json.dumps(rules, indent=2)
    shown = 0
    while t.is_alive():
        time.sleep(3)
        yield "\n".join(log[-40:]), [], json.dumps(rules, indent=2)
    meta = json.loads((JOBS_DIR / job_id / "job.json").read_text())
    yield "\n".join(log[-40:]), meta["clips"], json.dumps(rules, indent=2)


def list_jobs():
    rows = []
    for j in sorted(JOBS_DIR.glob("*/job.json"), reverse=True):
        m = json.loads(j.read_text())
        rows.append([m["id"], m["status"], len(m["clips"])])
    return rows


def load_job(job_id):
    f = JOBS_DIR / str(job_id).strip() / "job.json"
    return json.loads(f.read_text())["clips"] if f.exists() else []


with gr.Blocks(title="Campaign Clipper") as demo:
    gr.Markdown("# Campaign Clipper\nVideo + campaign guidelines in, subtitled vertical clips out.")
    with gr.Tab("New job"):
        with gr.Row():
            with gr.Column():
                src = gr.Radio(["URL", "Upload"], value="URL", label="Video source")
                url = gr.Textbox(label="Video URL (YouTube etc.)")
                up = gr.Video(label="...or upload video", sources=["upload"])
                gfile = gr.File(label="Campaign guidelines (PDF / DOCX / TXT)", type="filepath")
                gtext = gr.Textbox(label="...or paste guidelines", lines=6)
                go = gr.Button("Generate clips", variant="primary")
            with gr.Column():
                log = gr.Textbox(label="Progress", lines=14)
                rules_out = gr.Code(label="Rules extracted from guidelines", language="json")
        gallery = gr.File(label="Finished clips (download)", file_count="multiple")
        go.click(submit, [src, url, up, gfile, gtext], [log, gallery, rules_out])
    with gr.Tab("Jobs"):
        tbl = gr.Dataframe(headers=["job id", "status", "clips"], interactive=False)
        refresh = gr.Button("Refresh")
        jid = gr.Textbox(label="Job id to open")
        jfiles = gr.File(label="Clips", file_count="multiple")
        refresh.click(list_jobs, None, tbl)
        jid.submit(load_job, jid, jfiles)

if __name__ == "__main__":
    demo.queue().launch(share=True, debug=True)
