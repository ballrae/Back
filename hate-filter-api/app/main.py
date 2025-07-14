from fastapi import FastAPI
from pydantic import BaseModel
import re
import time
import logging
from model import predict_label, predict_label_batch

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextInput(BaseModel):
    text: str

# 마스킹 함수 (공백 제외)
def mask_text(text: str, mask_token="*"):
    return re.sub(r"[^\s]", mask_token, text)

@app.post("/predict")
def predict(input_data: TextInput):
    text = input_data.text
    result = predict_label(text)
    return result

@app.post("/filter")
def filter_text(input_data: TextInput):
    start_time = time.time()
    text = input_data.text
    logger.info(f"[필터링 시작] 입력 길이: {len(text)}")

    # 전체 문장 먼저 예측
    overall_result = predict_label(text)
    if overall_result["predicted"] != "hate":
        elapsed = time.time() - start_time
        logger.info(f"[비혐오 판정] 처리 시간: {elapsed:.3f}s")
        return {
            "masked_text": text,
            "details": [],
            "predicted": overall_result["predicted"]
        }

    # 단어 단위로 분해 후 배치 예측
    words = text.split()
    word_results = predict_label_batch(words)

    masked_words = []
    details = []

    for word, result in zip(words, word_results):
        if result["predicted"] in ["hate", "offensive"]:
            masked_words.append(mask_text(word))
            details.append({
                "word": word,
                "predicted": result["predicted"]
            })
        else:
            masked_words.append(word)

    elapsed = time.time() - start_time
    logger.info(f"[혐오 포함] 단어 수: {len(words)}, 처리 시간: {elapsed:.3f}s")

    return {
        "masked_text": ' '.join(masked_words),
        "details": details,
        "predicted": "hate"
    }