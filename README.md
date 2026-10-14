# Project Riko

Project Riko is a anime focused LLM project by Just Rayen. She listens, and remembers your conversations. It combines OpenAI’s GPT, GPT-SoVITS voice synthesis, and Faster-Whisper ASR into a fully configurable conversational pipeline.

**tested with python 3.10 Windows >10 and Linux Ubuntu**
## ✨ Features

- 💬 **LLM-based dialogue** using OpenAI API (configurable system prompts)
- 🧠 **Conversation memory** to keep context during interactions
- 🔊 **Voice generation** via GPT-SoVITS API
- 🎧 **Speech recognition** using Faster-Whisper
- 📁 Clean YAML-based config for personality configuration


## ⚙️ Configuration

All prompts and parameters are stored in `character_config.yaml`.

```yaml
OPENAI_API_KEY: sk-YOURAPIKEY
history_file: chat_history.json
model: "gpt-4.1-mini"
presets:
  default:
    system_prompt: |
      You are a helpful assistant named Riko.
      You speak like a snarky anime girl.
      Always refer to the user as "senpai".

sovits_ping_config:
  text_lang: en
  prompt_lang : en
  ref_audio_path : character_files/main_sample.wav  # relative to the repo, or an absolute path
  prompt_text : This is a sample voice for you to just get started with because it sounds kind of cute but just make sure this doesn't have long silences.
  
````

You can define personalities by modiying the config file.


## 🛠️ Setup

### Install Dependencies

```bash
pip install uv 
uv pip install -r extra-req.txt
uv pip install -r requirements.txt
```

**If you want to use GPU support for Faster whisper** Make sure you also have:

* CUDA & cuDNN installed correctly (for Faster-Whisper GPU support)
* `ffmpeg` installed (for audio processing)


## 🧪 Usage

### 1. Launch the GPT-SoVITS API 

### 2. Start the web app:

```bash
python -m server.main_chat
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000), allow microphone access, and the page starts listening automatically (if the browser needs a tap, click **Start listening**). Say “Riko” followed by your request. The page records your microphone, detects when you speak, and uploads each utterance to the server. Faster-Whisper transcribes it locally (no browser speech API, so it works the same on iOS Safari, Chrome, and others); if it starts with “Riko” the request goes to the language model and GPT-SoVITS voice, and the reply plays in the browser. If you only say “Riko”, the next thing you say is treated as the request.

Microphone access is limited to secure origins; `localhost` is supported. The first request loads the Whisper model, so it may be slow.

### Using it from an iPhone/iPad over Tailscale

iOS Safari only allows microphone access over HTTPS, so expose the app with Tailscale Serve (enable MagicDNS and HTTPS certificates in your tailnet first). The app stays bound to `127.0.0.1`, and Tailscale proxies to it:

```bash
python -m server.main_chat
tailscale serve --bg 8000
```

Then open the `https://<machine>.<tailnet>.ts.net` URL shown by `tailscale serve status` in Safari on your device, tap **Start listening**, and allow the microphone. Audio plays on the phone. For an app-like experience, tap Share → **Add to Home Screen**. The screen stays on while listening, and the mic recovers when you switch back to the page; if iOS cuts the mic (a call, for example), tap **Start listening** again. Set `RIKO_HOST` / `RIKO_PORT` to change the bind address or port.


## 📌 TODO / Future Improvements

* [x] Web interface with wake-word listening
* [ ] Emotion or tone control in speech synthesis
* [ ] VRM model frontend


## 🧑‍🎤 Credits

* Voice synthesis powered by [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)
* ASR via [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper)
* Language model via [OpenAI GPT](https://platform.openai.com)


## 📜 License

MIT — feel free to clone, modify, and build your own waifu voice companion.
