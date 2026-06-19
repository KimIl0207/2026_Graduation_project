from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TextRequest(BaseModel):
    text: str


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Error message from request handling.")


class RootResponse(BaseModel):
    message: str = Field(..., description="Server status message.")


class ModelProbs(BaseModel):
    sd: Optional[float] = Field(None, description="Stable Diffusion detector sigmoid probability.")
    mj: Optional[float] = Field(None, description="Midjourney detector sigmoid probability.")
    mj6: Optional[float] = Field(None, description="Midjourney v6 detector sigmoid probability.")
    bg: Optional[float] = Field(None, description="BigGAN detector sigmoid probability.")
    sd3: Optional[float] = Field(None, description="Stable Diffusion 3 detector sigmoid probability.")
    dalle3: Optional[float] = Field(None, description="DALL-E 3 detector sigmoid probability.")
    univfd: Optional[float] = Field(None, description="UnivFD CLIP linear-probe sigmoid probability.")


class PredictionSignals(BaseModel):
    model_fusion: float = Field(..., description="Final suspicious score.")
    fusion_model_scores: Optional[Dict[str, float]] = Field(None, description="Detector scores after per-model fusion calibration.")
    active_fusion_models: Optional[List[str]] = Field(None, description="Model keys used for final max fusion.")


class GradCamResponse(BaseModel):
    model: str = Field(..., description="Model used for Grad-CAM explanation.")
    image_base64: str = Field(..., description="Base64 PNG Grad-CAM overlay image.")
    note: str = Field(..., description="Grad-CAM explanation note.")


class ImagePredictionResponse(BaseModel):
    filename: str = Field(..., description="Uploaded source filename.")
    label: str = Field(..., description="Final prediction label.")
    suspicious_score: float = Field(..., description="AI-like suspicious score from 0 to 1.")
    confidence: str = Field(..., description="Prediction confidence display code.")
    model_probs: ModelProbs = Field(..., description="Raw detector probabilities.")
    signals: PredictionSignals = Field(..., description="Supporting prediction signals.")
    grad_cam: Optional[GradCamResponse] = Field(None, description="Optional Grad-CAM explanation.")


class VideoPredictionResponse(BaseModel):
    label: str = Field(..., description="Final video prediction label.")
    suspicious_score: float = Field(..., description="Average frame suspicious score.")
    frame_count: int = Field(..., description="Number of analyzed frames.")
    frame_predictions: Optional[List[float]] = Field(None, description="Frame-level suspicious scores.")


class TextHighlight(BaseModel):
    text: str = Field(..., description="Sentence or text span that was analyzed.")
    start: int = Field(..., description="Start character offset in the original text.")
    end: int = Field(..., description="End character offset in the original text.")
    language: str = Field(..., description="Detected language for this span.")
    ai_prob: float = Field(..., description="Final AI-like probability for this span, 0 to 100.")
    roberta_ai_prob: float = Field(..., description="RoBERTa AI probability for this span, 0 to 100.")
    perplexity: Optional[float] = Field(None, description="Perplexity for this span.")
    ppl_score: Optional[float] = Field(None, description="Normalized AI score from span perplexity.")
    is_ai_like: bool = Field(..., description="Whether this span is likely AI-like.")
    reason: str = Field(..., description="Short explanation for why this span was flagged.")


class TextDetectionResponse(BaseModel):
    language: Optional[str] = Field(None, description="Detected primary language.")
    roberta_ai_prob: Optional[float] = Field(None, description="XLM-RoBERTa AI probability, 0 to 100.")
    final_ai_prob: Optional[float] = Field(None, description="Final AI probability, 0 to 100.")
    decision: Optional[str] = Field(None, description="Final decision: AI, Human, or Uncertain.")
    burstiness: Optional[float] = Field(None, description="Sentence length variation score.")
    perplexity: Optional[float] = Field(None, description="Average language-model perplexity.")
    burst_score: Optional[float] = Field(None, description="Normalized AI score from burstiness.")
    ppl_score: Optional[float] = Field(None, description="Normalized AI score from perplexity.")
    sentence_highlights: Optional[List[TextHighlight]] = Field(None, description="Sentence-level AI-like spans.")


class SaveCorrectionResponse(BaseModel):
    success: bool = Field(..., description="Whether correction data was saved.")
    message: str = Field(..., description="Save result message.")
    saved_path: Optional[str] = Field(None, description="Saved file path.")
