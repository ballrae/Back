from fastapi import FastAPI
from pydantic import BaseModel
from model import predict_label
import re

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
    text = input_data.text
    overall_result = predict_label(text)

    # hate가 아니면 원문 그대로 반환
    if overall_result['predicted'] != 'hate':
        return {"masked_text": text, "details": [], "predicted": overall_result['predicted']}

    # hate면 단어 단위로 나눠서 다시 예측
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

    return {
        "masked_text": ' '.join(masked_words),
        "details": details,
        "predicted": "hate"
    }