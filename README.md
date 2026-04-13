# AI Detection Project

Image AI detection, text AI detection, correction data collection, and frontend/mobile clients.

## Structure

```text
.
|-- front/                     # React web UI
|-- mobile/                    # Mobile client
|-- server/
|   |-- main.py                # Image detection FastAPI server
|   |-- textmain.py            # Text detection FastAPI server
|   |-- ai_text_detector_engine.py
|   |-- requirements.txt
|   |-- model/                 # Image model weights
|   |-- service/
|   |   |-- model_loader.py
|   |   `-- predict.py
|   |-- util/
|   |   |-- logger.py
|   |   `-- save_correction.py
|   `-- corrections/           # Ignored correction images/logs
`-- ngrok.exe                  # Local ngrok binary, ignored by git
```

## Backend

Run commands from the `server` directory.

```powershell
cd server
pip install -r requirements.txt
```

Image detection server:

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000
```

Text detection server:

```powershell
uvicorn textmain:app --host 0.0.0.0 --port 8001
```

Do not run both servers on the same port.

## Image API

`GET /`

```json
{"message": "Server is running"}
```

`POST /predict`

Form data:

```text
file=<image file>
```

Response:

```json
{
  "label": "AI Generated",
  "probability": 0.8123,
  "generator_model": "mj",
  "probs": {
    "sd": 0.1234,
    "mj": 0.8123,
    "bg": 0.2345
  }
}
```

If the max probability is lower than `0.5`, the result is:

```json
{
  "label": "Real Image",
  "generator_model": "Not an ai"
}
```

`POST /save-correction`

Form data:

```text
file=<image file>
correct_label=real|fake
predicted_label=<optional>
predicted_probability=<optional>
selected_generator_model=<optional>
sd_prob=<optional>
mj_prob=<optional>
bg_prob=<optional>
```

Behavior:

- Saves corrected images to `server/corrections/real` or `server/corrections/fake`
- Appends correction metadata to `server/corrections/logs.jsonl`
- Uses `server/util/save_correction.py` and `server/util/logger.py`

## Text API

`GET /`

```json
{"status": "online", "message": "AI Text Detector API is ready."}
```

`POST /detect`

Body:

```json
{
  "text": "text to analyze"
}
```

The text detector uses Hugging Face models. If the model is private, create `server/.env` from `server/.env.example`.

```powershell
cd server
Copy-Item .env.example .env
```

Then set:

```text
HF_TOKEN=your_huggingface_token
```

## Frontend

The frontend is a Create React App project.

```powershell
cd front
npm install
npm start
```

Default URL:

```text
http://localhost:3000
```

If port `3000` is already in use:

```powershell
$env:PORT="3001"
npm start
```

Set the backend URL in `front/.env` or in `front/src/App.js`, depending on the current local setup.

## ngrok

Expose the image server:

```powershell
.\ngrok.exe http 8000
```

Expose the frontend:

```powershell
.\ngrok.exe http 3000
```

If the frontend runs on `3001`:

```powershell
.\ngrok.exe http 3001
```

Update the frontend backend URL after ngrok gives a new backend URL.

## Model Files

Expected image model files:

```text
server/model/best_efficientnet_b0_Diffusion.pth
server/model/best_efficientnet_b0_Midjourney.pth
server/model/best_efficientnet_b0_BigGAN.pth
```

Image input is resized to `224x224` in `server/service/predict.py`.

## Notes

- `front/`, `server/corrections/`, `ngrok.exe`, and cache directories are ignored by git.
- Correction data is local training feedback data.
- Keep server imports relative to the `server` directory, for example `from service...` and `from util...`.
