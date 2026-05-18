import os
import re
import json
import torch
import nltk
import numpy as np
import torch.nn.functional as F
from huggingface_hub import hf_hub_download

from dotenv import load_dotenv
from kiwipiepy import Kiwi

from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    AutoModelForCausalLM,
)

# ==========================================
# ENV
# ==========================================

load_dotenv()

# ==========================================
# AI Detector
# ==========================================


class AITextDetector:
    def __init__(self, model_path="seongwoo02/ai_text_detector", token=None):
        print("개선된 Hybrid AI Detector 엔진을 가동합니다...\n")

        # ======================================
        # Device
        # ======================================

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        print(f"⚡ 현재 연산 장치: {self.device}")

        # ======================================
        # NLTK
        # ======================================

        nltk.download("punkt", quiet=True)
        nltk.download("punkt_tab", quiet=True)

        # ======================================
        # Kiwi
        # ======================================

        self.kiwi = Kiwi()

        # ======================================
        # HuggingFace Token
        # ======================================

        if token is None:
            token = os.getenv("HF_TOKEN")

        # ======================================
        # Threshold Load
        # ======================================

        try:
            threshold_path = hf_hub_download(
                repo_id="seongwoo02/ai_text_detector",
                filename="thresholds.json",
                token=token
                )

            with open(threshold_path, "r", encoding="utf-8") as f:
                thresholds = json.load(f)

            self.THRESH_BURST_KO = thresholds["THRESH_BURST_KO"]
            self.THRESH_BURST_EN = thresholds["THRESH_BURST_EN"]

            self.THRESH_KO_PPL = thresholds["THRESH_KO_PPL"]
            self.THRESH_EN_PPL = thresholds["THRESH_EN_PPL"]

            print("✅ thresholds.json 로드 완료")

        except Exception as e:
            print("⚠️ threshold 파일 없음 → 기본값 사용")

            self.THRESH_BURST_KO = 16.8
            self.THRESH_BURST_EN = 6.9

            self.THRESH_KO_PPL = 54.2
            self.THRESH_EN_PPL = 17.8

        # ======================================
        # Load XLM-R
        # ======================================

        print(f"\n🤖 XLM-RoBERTa 탐지 모델 로드 중... ({model_path})")

        try:
            self.roberta_tokenizer = AutoTokenizer.from_pretrained(
                model_path, token=token
            )

            self.roberta_model = AutoModelForSequenceClassification.from_pretrained(
                model_path, token=token
            ).to(self.device)

        except Exception as e:
            print(f"⚠️ 모델 로드 실패: {e}")
            print("💡 기본 xlm-roberta-base 모델 사용")

            self.roberta_tokenizer = AutoTokenizer.from_pretrained("xlm-roberta-base")

            self.roberta_model = AutoModelForSequenceClassification.from_pretrained(
                "xlm-roberta-base", num_labels=2
            ).to(self.device)

        self.roberta_model.eval()

        # ======================================
        # Load PPL Models
        # ======================================

        print("\n🇰🇷 KoGPT2 PPL 모델 로드 중...")

        self.ko_ppl_tokenizer = AutoTokenizer.from_pretrained("skt/kogpt2-base-v2")

        self.ko_ppl_model = (
            AutoModelForCausalLM.from_pretrained("skt/kogpt2-base-v2")
            .to(self.device)
            .eval()
        )

        print("🇺🇸 GPT2 PPL 모델 로드 중...")

        self.en_ppl_tokenizer = AutoTokenizer.from_pretrained("gpt2")

        self.en_ppl_model = (
            AutoModelForCausalLM.from_pretrained("gpt2").to(self.device).eval()
        )

        print("✅ 모든 모델 로드 완료!\n")

    # ==========================================
    # Utils
    # ==========================================

    def _detect_language_per_sentence(self, sentence):
        ko_count = len(re.findall(r"[가-힣]", sentence))
        en_count = len(re.findall(r"[a-zA-Z]", sentence))

        return "ko" if ko_count >= en_count else "en"

    def _split_sentences(self, text):
        try:
            sents = self.kiwi.split_into_sents(text)
            return [s.text.strip() for s in sents if len(s.text.strip()) > 0]

        except:
            try:
                return nltk.sent_tokenize(text)

            except:
                return [text]

    def _get_sentence_length(self, sentence, lang):
        try:
            if lang == "ko":
                tokens = self.kiwi.tokenize(sentence)

                return len(tokens)

            else:
                return len(sentence.split())

        except:
            return len(sentence.split())

    def _get_burstiness(self, sentences):
        if len(sentences) <= 1:
            return 0.0

        lengths = []

        for sentence in sentences:

            if len(sentence.strip()) == 0:
                continue

            lang = self._detect_language_per_sentence(sentence)

            sent_len = self._get_sentence_length(sentence, lang)

            lengths.append(sent_len)

        if len(lengths) <= 1:
            return 0.0

        return float(np.std(lengths))

    def _get_perplexity(self, text, model, tokenizer):
        try:
            inputs = tokenizer(
                text, return_tensors="pt", truncation=True, max_length=512
            )

            input_ids = inputs["input_ids"].to(self.device)

            if input_ids.shape[1] < 2:
                return 0.0

            with torch.no_grad():
                outputs = model(input_ids, labels=input_ids)
                loss = outputs.loss

            ppl = torch.exp(loss).item()

            if np.isnan(ppl):
                return 0.0

            if np.isinf(ppl):
                return 0.0

            return float(ppl)

        except:
            return 0.0

    def _normalize_score(self, value, threshold):
        if value <= 0:
            return 50.0

        ratio = value / threshold

        # threshold보다 낮으면 AI 가능성 ↑
        if ratio < 1.0:
            score = 100 - (ratio * 50)

        else:
            score = max(0, 50 - ((ratio - 1.0) * 50))

        return float(score)

    # ==========================================
    # Main Detector
    # ==========================================

    def detect(self, text):
        text = text.strip()

        if len(text) < 10:
            return {"error": "텍스트가 너무 짧습니다."}

        results = {}

        # ======================================
        # Sentence Split
        # ======================================

        sentences = self._split_sentences(text)

        # ======================================
        # Main Language
        # ======================================

        ko_count = 0
        en_count = 0

        for s in sentences:
            lang = self._detect_language_per_sentence(s)

            if lang == "ko":
                ko_count += 1
            else:
                en_count += 1

        main_lang = "ko" if ko_count >= en_count else "en"

        results["language"] = main_lang

        # ======================================
        # XLM-R
        # ======================================

        inputs = self.roberta_tokenizer(
            text, return_tensors="pt", truncation=True, max_length=256
        ).to(self.device)

        with torch.no_grad():
            outputs = self.roberta_model(**inputs)

            probs = F.softmax(outputs.logits, dim=-1).squeeze()

        ai_prob = float(probs[1].item() * 100)

        results["roberta_ai_prob"] = ai_prob

        # ======================================
        # EXTREME SHORTCUT ONLY
        # ======================================

        if ai_prob >= 99.5:
            results["final_ai_prob"] = ai_prob
            results["decision"] = "AI"

            return results

        if ai_prob <= 0.5:
            results["final_ai_prob"] = ai_prob
            results["decision"] = "Human"

            return results

        # ======================================
        # Burstiness
        # ======================================

        burstiness_score = self._get_burstiness(sentences)

        results["burstiness"] = burstiness_score

        # ======================================
        # Sentence-level PPL
        # ======================================

        ppl_scores = []

        for sentence in sentences:
            if len(sentence.strip()) < 5:
                continue

            lang = self._detect_language_per_sentence(sentence)

            if lang == "ko":
                ppl = self._get_perplexity(
                    sentence, self.ko_ppl_model, self.ko_ppl_tokenizer
                )

            else:
                ppl = self._get_perplexity(
                    sentence, self.en_ppl_model, self.en_ppl_tokenizer
                )

            if ppl > 0:
                ppl_scores.append(ppl)

        avg_ppl = float(np.mean(ppl_scores)) if len(ppl_scores) > 0 else 0.0

        results["perplexity"] = avg_ppl

        # ======================================
        # Threshold Selection
        # ======================================

        if main_lang == "ko":
            burst_threshold = self.THRESH_BURST_KO
            ppl_threshold = self.THRESH_KO_PPL

        else:
            burst_threshold = self.THRESH_BURST_EN
            ppl_threshold = self.THRESH_EN_PPL

        # ======================================
        # Statistical Scores
        # ======================================

        burst_score = self._normalize_score(burstiness_score, burst_threshold)

        ppl_score = self._normalize_score(avg_ppl, ppl_threshold)

        results["burst_score"] = burst_score
        results["ppl_score"] = ppl_score

        # ======================================
        # Ensemble Weighting
        # ======================================

        final_score = (ai_prob * 0.85) + (burst_score * 0.075) + (ppl_score * 0.075)

        final_score = max(min(final_score, 100.0), 0.0)

        results["final_ai_prob"] = final_score

        # ======================================
        # Final Decision
        # ======================================

        if final_score >= 70:
            decision = "AI"
        elif final_score <= 30:
            decision = "Human"
        else:
            decision = "Uncertain"

        results["decision"] = decision

        return results


# ==========================================
# Report
# ==========================================


def print_report(text, report):

    if "error" in report:
        print(f"❌ 오류: {report['error']}")

        return

    print("=" * 60)
    print("📊 Hybrid AI Detector Report")
    print("=" * 60)

    print("\n[입력 문장]")
    print(text.strip())

    print("\n🌍 [언어 분석]")
    print(f"감지 언어: {report['language']}")

    print("\n🤖 [XLM-RoBERTa 딥러닝 판별]")
    print(f"AI 확률: " f"{report['roberta_ai_prob']:.2f}%")

    # ======================================
    # Burstiness
    # ======================================

    if "burstiness" in report:
        print("\n📝 [Burstiness 분석]")
        print(f"문장 길이 변동성: " f"{report['burstiness']:.4f}")
        print(f"정규화 점수: " f"{report['burst_score']:.2f}")

    else:

        print("\n📝 [Burstiness 분석]")
        print("Skipped (Extreme Shortcut)")

    # ======================================
    # PPL
    # ======================================

    if "perplexity" in report:
        print("\n📚 [Perplexity 분석]")
        print(f"PPL 점수: " f"{report['perplexity']:.4f}")
        print(f"정규화 점수: " f"{report['ppl_score']:.2f}")

    else:
        print("\n📚 [Perplexity 분석]")
        print("Skipped (Extreme Shortcut)")

    # ======================================
    # Final
    # ======================================

    final_prob = report["final_ai_prob"]

    print("\n" + "-" * 60)
    print(f"🎯 최종 AI 확률 : " f"{final_prob:.2f}%")

    if final_prob >= 85:
        verdict = "🚨 매우 높은 확률로 AI 생성 텍스트"
    elif final_prob >= 70:
        verdict = "⚠️ AI 생성 가능성이 높음"
    elif final_prob >= 55:
        verdict = "🟡 AI와 사람 특성이 혼합됨"
    elif final_prob >= 40:
        verdict = "🟢 사람 작성 가능성이 높음"
    else:
        verdict = "✅ 매우 높은 확률로 사람 작성 텍스트"

    print(f"📌 최종 판정 : {verdict}")

    # ======================================
    # Internal Log
    # ======================================

    print("\n🧠 [내부 점수 로그]")

    print(f"RoBERTa Base Score : " f"{report['roberta_ai_prob']:.2f}")

    if "burst_score" in report:
        print(f"Burstiness Score   : " f"{report['burst_score']:.2f}")
    else:
        print("Burstiness Score   : Skipped")
    if "ppl_score" in report:
        print(f"PPL Score          : " f"{report['ppl_score']:.2f}")
    else:
        print("PPL Score          : Skipped")

    print("=" * 60)


# ==========================================
# Run
# ==========================================

if __name__ == "__main__":
    detector = AITextDetector()
    
    test_text = """
    인공지능은 최근 다양한 산업 분야에서 빠르게 활용되고 있다.
    특히 자연어 처리와 생성형 AI 기술은 인간 수준의 텍스트 생성 능력을 보여주고 있다.
    """
    report = detector.detect(test_text)

    print_report(test_text, report)
