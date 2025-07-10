from fastapi import FastAPI
from pydantic import BaseModel
from model import predict_label
import re
import time
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class TextInput(BaseModel):
    text: str

def mask_text(text: str, mask_token="*"):
    return re.sub(r"[^\s]", mask_token, text)

@app.post("/predict")
def predict(input_data: TextInput):
    return predict_label(input_data.text)

@app.post("/filter")
def filter(input_data: TextInput):
    start_time = time.time()
    logger.info(f"[필터링 시작] 전체 문장 길이: {len(input_data.text)}")

    text = input_data.text
    overall_result = predict_label(text)

    if overall_result['predicted'] != 'hate':
        elapsed = time.time() - start_time
        logger.info(f"[필터링 종료 - 비혐오] 처리 시간: {elapsed:.3f}s")
        return {"masked_text": text, "details": [], "predicted": overall_result['predicted']}

    words = text.split()
    masked_words = []
    details = []

    for word in words:
        result = predict_label(word)
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