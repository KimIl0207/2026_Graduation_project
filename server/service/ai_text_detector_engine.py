import torch
import numpy as np
import nltk
import re
import os
from transformers import AutoTokenizer, AutoModelForSequenceClassification, AutoModelForCausalLM
import torch.nn.functional as F
from dotenv import load_dotenv

# .env 파일이 있으면 환경 변수를 로드합니다.
load_dotenv()

class AITextDetector:
    def __init__(self, model_path="seongwoo02/ai_text_detector", token=None):
        """
        AI 텍스트 탐지기 엔진 초기화
        :param model_path: 학습된 모델 경로 (로컬 또는 허깅페이스)
        :param token: 허깅페이스 Private 모델 접근용 토큰 (None이면 환경 변수 HF_TOKEN 사용)
        """
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"⚡ 현재 연산 장치: {self.device}")

        nltk.download('punkt', quiet=True)
        nltk.download('punkt_tab', quiet=True)

        # 매개변수로 토큰이 없으면 환경 변수에서 시도
        if token is None:
            token = os.getenv("HF_TOKEN")

        # [1] 허깅페이스 또는 로컬에서 모델 로드
        print(f"📂 탐지 모델 로드 중... ({model_path})")
        try:
            self.roberta_tokenizer = AutoTokenizer.from_pretrained(model_path, token=token)
            self.roberta_model = AutoModelForSequenceClassification.from_pretrained(model_path, token=token).to(self.device)
        except Exception as e:
            print(f"⚠️ 모델 로드 실패: {e}")
            print("💡 기본 xlm-roberta-base 모델을 로드합니다.")
            self.roberta_tokenizer = AutoTokenizer.from_pretrained("xlm-roberta-base")
            self.roberta_model = AutoModelForSequenceClassification.from_pretrained("xlm-roberta-base", num_labels=2).to(self.device)
        
        self.roberta_model.eval()

        # [2] 통계 분석용 퍼플렉서티(PPL) 보조 모델 로드
        print("🇰🇷 한국어 PPL 보조 모델(KoGPT2) 로드 중...")
        self.ko_ppl_tokenizer = AutoTokenizer.from_pretrained("skt/kogpt2-base-v2")
        self.ko_ppl_model = AutoModelForCausalLM.from_pretrained("skt/kogpt2-base-v2").to(self.device).eval()

        print("🇺🇸 영어 PPL 보조 모델(GPT-2) 로드 중...")
        self.en_ppl_tokenizer = AutoTokenizer.from_pretrained("gpt2")
        self.en_ppl_model = AutoModelForCausalLM.from_pretrained("gpt2").to(self.device).eval()

        # 임계값(Threshold) 설정
        self.THRESH_BURST = 11.03
        self.THRESH_KO_PPL = 155.67
        self.THRESH_EN_PPL = 55.82

        print("✅ 모든 모델 및 설정 로드 완료!\n")

    def _detect_language_per_sentence(self, sentence):
        """문장 단위 언어 판별 (한국어 vs 영어)"""
        words = sentence.split()
        ko_word_count = 0
        en_word_count = 0

        for word in words:
            if re.search(r'[가-힣]', word):
                ko_word_count += 1
            elif re.search(r'[a-zA-Z]', word):
                en_word_count += 1

        return 'en' if en_word_count > ko_word_count else 'ko'

    def detect(self, text):
        """
        텍스트가 AI에 의해 작성되었는지 하이브리드 방식으로 탐지합니다.
        """
        if len(text.strip()) < 10:
            return {"error": "텍스트가 너무 짧아 정확한 분석이 어렵습니다."}

        results = {}

        # --- [검사 1] XLM-RoBERTa 딥러닝 문맥 분석 ---
        inputs = self.roberta_tokenizer(text, return_tensors="pt", truncation=True, max_length=256).to(self.device)
        with torch.no_grad():
            outputs = self.roberta_model(**inputs)
            probs = F.softmax(outputs.logits, dim=-1).squeeze().tolist()
        ai_prob = probs[1] * 100
        results['roberta_ai_prob'] = ai_prob

        # --- [검사 2] 문장 길이 변동성(Burstiness) ---
        sentences = nltk.sent_tokenize(text)
        if len(sentences) > 1:
            sentence_lengths = [len(nltk.word_tokenize(sentence)) for sentence in sentences]
            burstiness_score = np.std(sentence_lengths)
        else:
            burstiness_score = 0.0
        results['burstiness'] = burstiness_score

        # --- [검사 3] 문장별 당혹성(Perplexity, PPL) 계산 ---
        ko_ppl_scores = []
        en_ppl_scores = []

        for sentence in sentences:
            if len(sentence.strip()) < 3:
                continue

            lang = self._detect_language_per_sentence(sentence)

            if lang == 'ko':
                ppl_inputs = self.ko_ppl_tokenizer(sentence, return_tensors="pt")
                input_ids = ppl_inputs["input_ids"][:, :512].to(self.device)
                with torch.no_grad():
                    loss = self.ko_ppl_model(input_ids, labels=input_ids).loss
                ko_ppl_scores.append(torch.exp(loss).item())
            else:
                ppl_inputs = self.en_ppl_tokenizer(sentence, return_tensors="pt")
                input_ids = ppl_inputs["input_ids"][:, :512].to(self.device)
                with torch.no_grad():
                    loss = self.en_ppl_model(input_ids, labels=input_ids).loss
                en_ppl_scores.append(torch.exp(loss).item())

        avg_ko_ppl = np.mean(ko_ppl_scores) if ko_ppl_scores else 0.0
        avg_en_ppl = np.mean(en_ppl_scores) if en_ppl_scores else 0.0

        results['ko_perplexity'] = avg_ko_ppl
        results['en_perplexity'] = avg_en_ppl

        # --- [⚖️ 하이브리드 점수 조정 로직] ---
        final_score = ai_prob

        # 1. 변동성(Burstiness) 보정
        burst_adj = 0.0
        if burstiness_score < self.THRESH_BURST:
            gap_ratio = (self.THRESH_BURST - burstiness_score) / self.THRESH_BURST
            burst_adj = 10 + (25 * gap_ratio)
        else:
            bonus_ratio = min((burstiness_score - self.THRESH_BURST) / self.THRESH_BURST, 1.0)
            burst_adj = -(10 * bonus_ratio)
        
        final_score += burst_adj
        results['burst_adj'] = burst_adj

        # 2. 당혹성(Perplexity) 보정
        ppl_penalty = 0
        ko_ppl_adj = 0.0
        en_ppl_adj = 0.0
        evaluated_langs = 0

        if avg_ko_ppl > 0:
            if avg_ko_ppl < self.THRESH_KO_PPL:
                gap_ratio = (self.THRESH_KO_PPL - avg_ko_ppl) / self.THRESH_KO_PPL
                ko_ppl_adj = 10 + (25 * gap_ratio)
            else:
                bonus_ratio = min((avg_ko_ppl - self.THRESH_KO_PPL) / self.THRESH_KO_PPL, 1.0)
                ko_ppl_adj = -(10 * bonus_ratio)
            ppl_penalty += ko_ppl_adj
            evaluated_langs += 1

        if avg_en_ppl > 0:
            if avg_en_ppl < self.THRESH_EN_PPL:
                gap_ratio = (self.THRESH_EN_PPL - avg_en_ppl) / self.THRESH_EN_PPL
                en_ppl_adj = 10 + (25 * gap_ratio)
            else:
                bonus_ratio = min((avg_en_ppl - self.THRESH_EN_PPL) / self.THRESH_EN_PPL, 1.0)
                en_ppl_adj = -(10 * bonus_ratio)
            ppl_penalty += en_ppl_adj
            evaluated_langs += 1

        if evaluated_langs > 0:
            final_score += (ppl_penalty / evaluated_langs)

        results['ko_ppl_adj'] = ko_ppl_adj
        results['en_ppl_adj'] = en_ppl_adj
        results['final_ai_prob'] = max(min(final_score, 100.0), 0.0)

        detected_langs = []
        if avg_ko_ppl > 0: detected_langs.append("한국어")
        if avg_en_ppl > 0: detected_langs.append("영어")
        results['language'] = " + ".join(detected_langs)

        return results

def print_report(text, report):
    """분석 결과를 깔끔하게 출력합니다."""
    if "error" in report:
        print(f"❌ 오류: {report['error']}")
        return

    print("==================================================")
    print("               📊 AI 탐지 분석 리포트              ")
    print("==================================================")
    print(f"\n[입력 텍스트 요약]\n{text[:150].strip()}...")
    print(f"\n🌍 감지된 언어 : {report['language']}")
    print(f"🤖 딥러닝 문맥 예측 확률 : {report['roberta_ai_prob']:.1f}%")
    
    print(f"📏 문장 길이 변동성(Burstiness): {report['burstiness']:.2f}")
    print(f"   보정치: {report['burst_adj']:+.1f}%p")

    if report['ko_perplexity'] > 0:
        print(f"🇰🇷 한국어 당혹성(PPL): {report['ko_perplexity']:.2f}")
        print(f"   보정치: {report['ko_ppl_adj']:+.1f}%p")

    if report['en_perplexity'] > 0:
        print(f"🇺🇸 영어 당혹성(PPL): {report['en_perplexity']:.2f}")
        print(f"   보정치: {report['en_ppl_adj']:+.1f}%p")
    
    print("--------------------------------------------------")
    if report['final_ai_prob'] > 60:
        print(f"🚨 판별 결과: AI가 작성했을 확률이 매우 높습니다! (확률: {report['final_ai_prob']:.1f}%)")
    else:
        print(f"✅ 판별 결과: 사람이 작성했을 가능성이 높습니다. (AI 확률: {report['final_ai_prob']:.1f}%)")
    print("==================================================\n")

if __name__ == "__main__":
    # 사용 예시 (기본적으로 허깅페이스 Private 모델을 로드합니다)
    detector = AITextDetector()
    
    test_text = """
    인공지능(AI)은 현대 사회의 다양한 분야에서 혁신을 일으키고 있습니다. 
    기계 학습과 딥러닝 기술의 발전으로 인해 AI는 이제 인간의 언어를 이해하고 생성하며, 
    복잡한 문제를 해결하는 데 있어 놀라운 능력을 보여주고 있습니다.
    """
    
    result = detector.detect(test_text)
    print_report(test_text, result)
