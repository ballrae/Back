from fastapi import FastAPI
from pydantic import BaseModel
import re
import time
import logging
from model import predict_label, predict_label_batch  # 배치 함수 포함된 model.py

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextInput(BaseModel):
    text: str

def mask_text(text: str, mask_token="*"):
    return re.sub(r"[^\s]", mask_token, text)

@app.post("/filter")
def filter(input_data: TextInput):
    start_time = time.time()
    text = input_data.text
    logger.info(f"[필터링 시작] 전체 문장 길이: {len(text)}")

    # 문장 단위 예측 먼저
    overall_result = predict_label(text)

    if overall_result['predicted'] != 'hate':
        elapsed = time.time() - start_time
        logger.info(f"[필터링 종료 - 비혐오] 처리 시간: {elapsed:.3f}s")
        return {"masked_text": text, "details": [], "predicted": overall_result['predicted']}

    # 혐오면 단어별 분석 (배치)
    words = text.split()
    word_results = predict_label_batch(words)

    masked_words = []
    details = []

    for word, result in zip(words, word_results):
        if result['predicted'] == 'hate':
            masked_words.append(mask_text(word))
            details.append({"word": word, "predicted": "hate"})
        else:
            masked_words.append(word)

    elapsed = time.time() - start_time
    logger.info(f"[필터링 종료 - 혐오 포함] 단어 수: {len(words)}, 처리 시간: {elapsed:.3f}s")

    return {
        "masked_text": ' '.join(masked_words),
        "details": details,
        "predicted": "hate"
    }