# Paste these cells into a Colab notebook (Runtime > Change runtime type > T4 GPU)

# --- Cell 1: mount Drive (so clips survive session resets) and get the code
# from google.colab import drive; drive.mount('/content/drive')
# !git clone https://github.com/RafaelGodoyEbert/ViralCutter /content/ViralCutter
# !pip -q install -r /content/ViralCutter/requirements.txt gradio pypdf python-docx requests
# !apt-get -qq install -y ffmpeg

# --- Cell 2: free Gemini key from https://aistudio.google.com/apikey
# import os; os.environ["GEMINI_API_KEY"] = "PASTE_KEY"
# (also put it in /content/ViralCutter/api_config.json as ViralCutter expects - see CODEX_TASK.md)

# --- Cell 3: copy app.py to /content/app.py, then
# !python /content/app.py      # prints a public gradio.live link
