# Task for Codex (you have terminal + Colab MCP)

Goal: make /content/app.py (Campaign Clipper) work end-to-end on a free Colab T4 with ViralCutter.

1. Via the Colab MCP: new notebook, T4 GPU, mount Drive, clone https://github.com/RafaelGodoyEbert/ViralCutter
   to /content/ViralCutter, install requirements (use the standard install, NOT the LocalLLM one; Colab
   has no Visual Studio step - skip the .bat files, run the pip equivalents). Install ffmpeg.
2. Read main_improved.py, scripts/create_viral_segments.py, webui/app.py. Then:
   - Run `python main_improved.py --help` and list every flag.
   - Find how Gemini is configured (api_config.json format) and write the user's key there.
   - Find how prompt.txt is consumed. If the LLM prompt is built elsewhere, change `inject_rules()` accordingly.
   - Fix every `# ADAPTER` item in app.py: upload handling, min/max clip duration flags, subtitle style flags,
     Whisper model (use a size that fits a 15GB T4; fall back to `medium` if large OOMs).
   - Make sure the CLI never blocks on `input()` (we pass stdin=DEVNULL); add flags or env as needed.
3. Test with one short (<10 min) public YouTube video and a 5-line fake brief. Confirm 9:16 clips with burned subtitles
   land in JOBS_DIR/<id>/clips. Fix `collect_clips()` if it picks up wrong files.
4. Launch `python /content/app.py` and report the gradio.live URL.
Do not change ViralCutter's own files except prompt.txt/api_config.json.
