from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

MODEL_NAME = "beomi/beep-KcELECTRA-base-hate"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
model.eval()

labels = ["none", "offensive", "hate"]

# 강제 혐오 단어 리스트
# 최소 강제 혐오 단어 리스트 (모델이 잘 못 잡는 케이스만)
force_hate_words = {
    "병신", "ㅂㅅ", "ㅄ", "상병신", "병신같은", "병 쉰",  # '병신' 관련만 집중
    "ㅂ ㅅ",  # 초성으로 우회 표현
}
# 단일 문장 예측
def predict_label(text: str) -> dict:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=128
    ).to(device)

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=-1)

    pred = torch.argmax(probs, dim=1).item()
    result = {label: float(probs[0][i]) for i, label in enumerate(labels)}

    # 강제 혐오 단어 포함 시 무조건 hate
    if text.strip() in force_hate_words:
        result["predicted"] = "hate"
    else:
        result["predicted"] = labels[pred]
    
    return result

# 다수 문장/단어 배치 예측
def predict_label_batch(texts: list[str]) -> list[dict]:
    if not texts:
        return []

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    inputs = tokenizer(
        texts,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=128
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=-1)

    preds = torch.argmax(probs, dim=1)
    results = []
    for i, prob in enumerate(probs):
        result = {label: float(prob[j]) for j, label in enumerate(labels)}
        word = texts[i]
        # 강제 라벨링 적용
        if word in force_hate_words:
            result["predicted"] = "hate"
        else:
            result["predicted"] = labels[preds[i].item()]
        results.append(result)

    return results